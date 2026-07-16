"""Durable atomic replay state and out-of-band owner-authorized recovery."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from .strict import (
    ErrorCode,
    JsonLimits,
    PrototypeError,
    b64url_decode,
    b64url_encode,
    exact_members,
    require_id,
    require_literal,
    require_safe_int,
    require_sha256,
    require_uuid_v4,
    sha256_hex,
    strict_json_loads,
)

REPLAY_SCHEMA = "ncp.prototype.forwarding-replay-store.v1"
RECOVERY_SCHEMA = "ncp.prototype.forwarding-replay-recovery.v1"
RECOVERY_CLOCK_POLICY = "unix-utc-ms-strict-v1"
DB_SCHEMA_VERSION = 1
MAX_REPLAY_SCOPES = 128
MAX_REPLAY_DATABASE_BYTES = 8_388_608
MAX_REPLAY_SIDECAR_BYTES = 8_388_608
RECOVERY_LIMITS = JsonLimits(
    max_bytes=8_192,
    max_depth=4,
    max_nodes=64,
    max_members=16,
    max_string_bytes=256,
)

_CREATE_METADATA = """
CREATE TABLE metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    store_id TEXT NOT NULL,
    recovery_epoch INTEGER NOT NULL
) STRICT
"""

_CREATE_HIGH_WATER = """
CREATE TABLE high_water (
    signer TEXT NOT NULL,
    receiver TEXT NOT NULL,
    route TEXT NOT NULL,
    plane TEXT NOT NULL,
    message_class TEXT NOT NULL,
    session_id TEXT NOT NULL,
    session_generation TEXT NOT NULL,
    forwarding_epoch TEXT NOT NULL,
    key_epoch INTEGER NOT NULL,
    recovery_epoch INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    PRIMARY KEY (
        signer,
        receiver,
        route,
        plane,
        message_class,
        session_id,
        session_generation,
        forwarding_epoch,
        key_epoch,
        recovery_epoch
    )
) STRICT, WITHOUT ROWID
"""

_CREATE_CAPACITY_TRIGGER = """
CREATE TRIGGER high_water_capacity
BEFORE INSERT ON high_water
WHEN
    (SELECT COUNT(*) FROM high_water) >= 128
    AND NOT EXISTS (
        SELECT 1
        FROM high_water
        WHERE signer = NEW.signer
          AND receiver = NEW.receiver
          AND route = NEW.route
          AND plane = NEW.plane
          AND message_class = NEW.message_class
          AND session_id = NEW.session_id
          AND session_generation = NEW.session_generation
          AND forwarding_epoch = NEW.forwarding_epoch
          AND key_epoch = NEW.key_epoch
          AND recovery_epoch = NEW.recovery_epoch
    )
BEGIN
    SELECT RAISE(ABORT, 'replay scope capacity exhausted');
END
"""

_UPSERT = """
INSERT INTO high_water (
    signer,
    receiver,
    route,
    plane,
    message_class,
    session_id,
    session_generation,
    forwarding_epoch,
    key_epoch,
    recovery_epoch,
    sequence
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (
    signer,
    receiver,
    route,
    plane,
    message_class,
    session_id,
    session_generation,
    forwarding_epoch,
    key_epoch,
    recovery_epoch
) DO UPDATE SET sequence = excluded.sequence
WHERE high_water.sequence < excluded.sequence
RETURNING sequence
"""


@dataclass(frozen=True, slots=True)
class PinnedReplayState:
    """Caller-pinned replay-store identity that is external to forwarding input."""

    store_id: str
    recovery_epoch: int
    schema_version: int = DB_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_uuid_v4(self.store_id, "pinned replay store_id")
        require_safe_int(self.recovery_epoch, "pinned recovery_epoch", positive=True)
        if self.schema_version != DB_SCHEMA_VERSION:
            raise PrototypeError(ErrorCode.RECOVERY, "pinned replay schema is unknown")


@dataclass(frozen=True, slots=True)
class ReplayKey:
    """Complete forwarding replay scope for one signer and receiver."""

    signer: str
    receiver: str
    route: str
    plane: str
    message_class: str
    session_id: str
    session_generation: str
    forwarding_epoch: str
    key_epoch: int
    recovery_epoch: int

    def values(self, sequence: int) -> tuple[Any, ...]:
        """Return the exact ordered SQLite parameter tuple."""

        return (
            self.signer,
            self.receiver,
            self.route,
            self.plane,
            self.message_class,
            self.session_id,
            self.session_generation,
            self.forwarding_epoch,
            self.key_epoch,
            self.recovery_epoch,
            sequence,
        )


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _recovery_document(
    *,
    action: str,
    audience: str,
    old: PinnedReplayState | None,
    new_store_id: str,
    new_recovery_epoch: int,
    issued_at_utc_ms: int,
    expires_at_utc_ms: int,
) -> dict[str, Any]:
    return {
        "action": action,
        "audience": audience,
        "clock_policy": RECOVERY_CLOCK_POLICY,
        "db_schema": REPLAY_SCHEMA,
        "db_schema_version": DB_SCHEMA_VERSION,
        "expires_at_utc_ms": expires_at_utc_ms,
        "issued_at_utc_ms": issued_at_utc_ms,
        "new_recovery_epoch": new_recovery_epoch,
        "new_store_id": new_store_id,
        "old_recovery_epoch": old.recovery_epoch if old else 0,
        "old_store_id": old.store_id if old else None,
        "schema": RECOVERY_SCHEMA,
    }


def build_recovery_authorization(
    signing_key: SigningKey,
    *,
    action: str,
    audience: str,
    old: PinnedReplayState | None,
    new_store_id: str,
    new_recovery_epoch: int,
    issued_at_utc_ms: int,
    expires_at_utc_ms: int,
) -> tuple[bytes, str]:
    """Create exact owner-signed out-of-band replay-store authorization bytes."""

    document = _recovery_document(
        action=action,
        audience=audience,
        old=old,
        new_store_id=new_store_id,
        new_recovery_epoch=new_recovery_epoch,
        issued_at_utc_ms=issued_at_utc_ms,
        expires_at_utc_ms=expires_at_utc_ms,
    )
    exact = _canonical_json(document)
    signature = signing_key.sign(exact).signature
    return exact, b64url_encode(signature)


def _verify_recovery_authorization(
    authorization: bytes,
    signature_b64: str,
    *,
    owner_public_key: bytes,
    owner_key_sha256: str,
    audience: str,
    old: PinnedReplayState | None,
    now_utc_ms: int,
    max_ttl_ms: int,
) -> PinnedReplayState:
    if not 1 <= len(authorization) <= RECOVERY_LIMITS.max_bytes:
        raise PrototypeError(
            ErrorCode.BOUNDS,
            "recovery authorization byte length is outside the profile bound",
        )
    if len(owner_public_key) != 32 or sha256_hex(owner_public_key) != owner_key_sha256:
        raise PrototypeError(ErrorCode.RECOVERY, "pinned recovery owner key does not match")
    signature = b64url_decode(signature_b64, maximum=64)
    if len(signature) != 64:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery signature is not 64 bytes")
    try:
        VerifyKey(owner_public_key).verify(authorization, signature)
    except (BadSignatureError, ValueError) as error:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery owner signature rejected") from error

    value = exact_members(
        strict_json_loads(authorization, RECOVERY_LIMITS),
        {
            "action",
            "audience",
            "clock_policy",
            "db_schema",
            "db_schema_version",
            "expires_at_utc_ms",
            "issued_at_utc_ms",
            "new_recovery_epoch",
            "new_store_id",
            "old_recovery_epoch",
            "old_store_id",
            "schema",
        },
        "recovery authorization",
    )
    if value["schema"] != RECOVERY_SCHEMA or value["db_schema"] != REPLAY_SCHEMA:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery schema is unknown")
    if value["clock_policy"] != RECOVERY_CLOCK_POLICY:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery clock policy is unknown")
    if value["db_schema_version"] != DB_SCHEMA_VERSION:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery database schema is unknown")
    if value["audience"] != audience:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery audience mismatch")
    issued = require_safe_int(value["issued_at_utc_ms"], "recovery issued_at")
    expires = require_safe_int(value["expires_at_utc_ms"], "recovery expires_at")
    if expires <= issued or expires - issued > max_ttl_ms:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery authorization TTL is invalid")
    if now_utc_ms < issued or now_utc_ms > expires:
        raise PrototypeError(ErrorCode.RECOVERY, "recovery authorization is not currently valid")

    if old is None:
        if (
            value["action"] != "initialize"
            or value["old_store_id"] is not None
            or value["old_recovery_epoch"] != 0
            or value["new_recovery_epoch"] != 1
        ):
            raise PrototypeError(ErrorCode.RECOVERY, "initialization authorization is invalid")
    else:
        if (
            value["action"] != "recover"
            or value["old_store_id"] != old.store_id
            or value["old_recovery_epoch"] != old.recovery_epoch
            or value["new_recovery_epoch"] != old.recovery_epoch + 1
            or value["new_store_id"] == old.store_id
        ):
            raise PrototypeError(
                ErrorCode.RECOVERY,
                "recovery authorization does not advance to a new pinned state",
            )
    return PinnedReplayState(
        require_uuid_v4(value["new_store_id"], "new replay store_id"),
        require_safe_int(
            value["new_recovery_epoch"],
            "new recovery_epoch",
            positive=True,
        ),
    )


def _check_directory(directory: Path) -> None:
    try:
        metadata = directory.lstat()
    except OSError as error:
        raise PrototypeError(
            ErrorCode.STORAGE,
            f"cannot inspect replay directory: {error}",
        ) from error
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise PrototypeError(ErrorCode.STORAGE, "replay directory is not owner-controlled")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PrototypeError(ErrorCode.STORAGE, "replay directory is accessible by group or other")


def _no_follow() -> int:
    flag = getattr(os, "O_NOFOLLOW", None)
    if flag is None:
        raise PrototypeError(ErrorCode.STORAGE, "O_NOFOLLOW is unavailable on this platform")
    return flag


def _check_open_file(
    file_descriptor: int,
    *,
    label: str,
    maximum_bytes: int,
) -> os.stat_result:
    metadata = os.fstat(file_descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise PrototypeError(ErrorCode.STORAGE, f"{label} is not an owner regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PrototypeError(ErrorCode.STORAGE, f"{label} is accessible by group or other")
    if metadata.st_size > maximum_bytes:
        raise PrototypeError(ErrorCode.STORAGE, f"{label} exceeds its byte bound")
    return metadata


def _check_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        try:
            metadata = sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise PrototypeError(
                ErrorCode.STORAGE,
                f"cannot inspect replay sidecar: {error}",
            ) from error
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or metadata.st_size > MAX_REPLAY_SIDECAR_BYTES
        ):
            raise PrototypeError(
                ErrorCode.STORAGE,
                "replay sidecar violates type, ownership, permission, or size bounds",
            )


def _remove_sidecars(path: Path) -> None:
    _check_sidecars(path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        try:
            sidecar.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            raise PrototypeError(
                ErrorCode.STORAGE,
                f"cannot remove replay sidecar: {error}",
            ) from error


def _acquire_lock(path: Path, *, create: bool, exclusive: bool) -> int:
    lock_path = Path(f"{path}.lock")
    flags = os.O_RDWR | _no_follow()
    if create:
        flags |= os.O_CREAT
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise PrototypeError(
            ErrorCode.STORAGE,
            f"cannot open replay coordination lock: {error}",
        ) from error
    try:
        opened = _check_open_file(
            descriptor,
            label="replay coordination lock",
            maximum_bytes=0,
        )
        try:
            current = lock_path.lstat()
        except OSError as error:
            raise PrototypeError(
                ErrorCode.STORAGE,
                f"cannot re-inspect replay coordination lock: {error}",
            ) from error
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_dev != opened.st_dev
            or current.st_ino != opened.st_ino
        ):
            raise PrototypeError(ErrorCode.STORAGE, "replay coordination lock changed during open")
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PrototypeError(
                ErrorCode.STORAGE,
                "replay store is active in another cooperating process",
            ) from error
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _connect_checked(path: Path) -> sqlite3.Connection:
    _check_sidecars(path)
    flags = os.O_RDWR | _no_follow()
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PrototypeError(
            ErrorCode.STORAGE,
            f"cannot open pinned replay database: {error}",
        ) from error
    try:
        opened = _check_open_file(
            descriptor,
            label="replay database",
            maximum_bytes=MAX_REPLAY_DATABASE_BYTES,
        )
        encoded_path = quote(path.as_posix(), safe="/")
        try:
            connection = sqlite3.connect(
                f"file:{encoded_path}?mode=rw",
                uri=True,
                isolation_level=None,
                timeout=5.0,
            )
        except sqlite3.Error as error:
            raise PrototypeError(
                ErrorCode.STORAGE,
                f"SQLite cannot open the pinned replay database: {error}",
            ) from error
        try:
            current = os.stat(path, follow_symlinks=False)
        except OSError as error:
            connection.close()
            raise PrototypeError(
                ErrorCode.STORAGE,
                f"cannot re-inspect replay database: {error}",
            ) from error
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_dev != opened.st_dev
            or current.st_ino != opened.st_ino
        ):
            connection.close()
            raise PrototypeError(ErrorCode.STORAGE, "replay database changed during open")
        return connection
    finally:
        os.close(descriptor)


def _configure(connection: sqlite3.Connection) -> None:
    journal = connection.execute("PRAGMA journal_mode=WAL").fetchone()
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA wal_autocheckpoint=1000")
    synchronous = connection.execute("PRAGMA synchronous").fetchone()
    trusted = connection.execute("PRAGMA trusted_schema").fetchone()
    foreign = connection.execute("PRAGMA foreign_keys").fetchone()
    if (
        journal is None
        or str(journal[0]).lower() != "wal"
        or synchronous != (2,)
        or trusted != (0,)
        or foreign != (1,)
    ):
        raise PrototypeError(ErrorCode.STORAGE, "SQLite fail-closed pragmas are not active")
    integrity = connection.execute("PRAGMA integrity_check").fetchall()
    if integrity != [("ok",)]:
        raise PrototypeError(ErrorCode.STORAGE, "SQLite integrity_check failed")


def _validate_schema(connection: sqlite3.Connection) -> None:
    objects = {
        (row[0], row[1]): " ".join(str(row[2]).split())
        for row in connection.execute(
            "SELECT type, name, sql FROM sqlite_schema WHERE type IN ('table', 'trigger')"
        ).fetchall()
    }
    expected = {
        ("table", "metadata"): " ".join(_CREATE_METADATA.split()),
        ("table", "high_water"): " ".join(_CREATE_HIGH_WATER.split()),
        ("trigger", "high_water_capacity"): " ".join(_CREATE_CAPACITY_TRIGGER.split()),
    }
    if objects != expected:
        raise PrototypeError(ErrorCode.STORAGE, "replay database schema SQL is unknown")
    metadata_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(metadata)").fetchall()
    ]
    high_water_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(high_water)").fetchall()
    ]
    if metadata_columns != [
        "singleton",
        "schema",
        "schema_version",
        "store_id",
        "recovery_epoch",
    ] or high_water_columns != [
        "signer",
        "receiver",
        "route",
        "plane",
        "message_class",
        "session_id",
        "session_generation",
        "forwarding_epoch",
        "key_epoch",
        "recovery_epoch",
        "sequence",
    ]:
        raise PrototypeError(ErrorCode.STORAGE, "replay database column set is unknown")


def _open_validated_connection(
    path: Path,
    pinned: PinnedReplayState,
) -> sqlite3.Connection:
    connection = _connect_checked(path)
    try:
        try:
            _configure(connection)
            _check_sidecars(path)
            _validate_schema(connection)
            row = connection.execute(
                """
                SELECT schema, schema_version, store_id, recovery_epoch
                FROM metadata
                WHERE singleton = 1
                """
            ).fetchone()
        except sqlite3.Error as error:
            raise PrototypeError(
                ErrorCode.STORAGE,
                f"replay database validation failed: {error}",
            ) from error
        if row != (
            REPLAY_SCHEMA,
            pinned.schema_version,
            pinned.store_id,
            pinned.recovery_epoch,
        ):
            raise PrototypeError(ErrorCode.STORAGE, "replay store identity mismatch")
        return connection
    except Exception:
        connection.close()
        raise


def _directory_open_flags() -> int:
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if directory_flag is None:
        raise PrototypeError(ErrorCode.STORAGE, "O_DIRECTORY is unavailable on this platform")
    return os.O_RDONLY | directory_flag | _no_follow()


def _database_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _reject_existing_initialization(path: Path) -> None:
    if _database_exists(path):
        raise PrototypeError(
            ErrorCode.RECOVERY,
            "initialization requires an absent replay database path",
        )


def _validate_prior_store(path: Path, old: PinnedReplayState) -> None:
    if not path.exists() or path.is_symlink():
        return
    try:
        connection = _open_validated_connection(path, old)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()
    except PrototypeError as error:
        if error.detail == "replay store identity mismatch":
            raise PrototypeError(
                ErrorCode.RECOVERY,
                "recovery prior state does not match the existing valid store",
            ) from error
        # Missing or corrupt replay bytes are the exact fail-closed states
        # for which an externally pinned owner authorization is required.


def _initialize_database(path: Path, pinned: PinnedReplayState) -> None:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(_CREATE_METADATA)
        connection.execute(_CREATE_HIGH_WATER)
        connection.execute(_CREATE_CAPACITY_TRIGGER)
        connection.execute(
            """
            INSERT INTO metadata (
                singleton,
                schema,
                schema_version,
                store_id,
                recovery_epoch
            ) VALUES (1, ?, ?, ?, ?)
            """,
            (
                REPLAY_SCHEMA,
                DB_SCHEMA_VERSION,
                pinned.store_id,
                pinned.recovery_epoch,
            ),
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def _replace_database(path: Path, pinned: PinnedReplayState) -> None:
    directory = path.parent
    _check_directory(directory)
    if path.is_symlink():
        raise PrototypeError(ErrorCode.STORAGE, "replay database path is a symlink")
    temporary = directory / f".{path.name}.{secrets.token_hex(16)}.tmp"
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | _no_follow()
    try:
        descriptor = os.open(temporary, flags, 0o600)
    except OSError as error:
        raise PrototypeError(
            ErrorCode.STORAGE,
            f"cannot create temporary replay database: {error}",
        ) from error
    os.close(descriptor)
    try:
        _initialize_database(temporary, pinned)
        descriptor = os.open(temporary, os.O_RDONLY | _no_follow())
        try:
            _check_open_file(
                descriptor,
                label="temporary replay database",
                maximum_bytes=MAX_REPLAY_DATABASE_BYTES,
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _remove_sidecars(path)
        os.replace(temporary, path)
        directory_descriptor = os.open(directory, _directory_open_flags())
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except (OSError, sqlite3.Error) as error:
        temporary.unlink(missing_ok=True)
        raise PrototypeError(
            ErrorCode.STORAGE,
            f"atomic replay database replacement failed: {error}",
        ) from error
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class ReplayStore:
    """One owner-only SQLite high-water store with commit-before-handoff semantics."""

    def __init__(
        self,
        path: Path,
        pinned: PinnedReplayState,
        connection: sqlite3.Connection,
        lock_descriptor: int,
    ) -> None:
        self.path = path
        self.pinned = pinned
        self._connection = connection
        self._lock_descriptor = lock_descriptor

    @classmethod
    def provision(
        cls,
        path: Path,
        authorization: bytes,
        signature_b64: str,
        *,
        owner_public_key: bytes,
        owner_key_sha256: str,
        audience: str,
        old: PinnedReplayState | None,
        now_utc_ms: int,
        max_ttl_ms: int = 60_000,
    ) -> PinnedReplayState:
        """Initialize or replace a store only under exact owner-signed authorization."""

        pinned = _verify_recovery_authorization(
            authorization,
            signature_b64,
            owner_public_key=owner_public_key,
            owner_key_sha256=require_sha256(owner_key_sha256, "owner_key_sha256"),
            audience=require_id(audience, "recovery audience"),
            old=old,
            now_utc_ms=require_safe_int(now_utc_ms, "recovery current time"),
            max_ttl_ms=require_safe_int(max_ttl_ms, "recovery maximum TTL", positive=True),
        )
        _check_directory(path.parent)
        lock_descriptor = _acquire_lock(path, create=True, exclusive=True)
        try:
            if old is None:
                _reject_existing_initialization(path)
            else:
                _validate_prior_store(path, old)
            _replace_database(path, pinned)
            return pinned
        finally:
            os.close(lock_descriptor)

    @classmethod
    def open(cls, path: Path, pinned: PinnedReplayState) -> ReplayStore:
        """Open an existing exact pinned store; absence or mismatch fails closed."""

        _check_directory(path.parent)
        lock_descriptor = _acquire_lock(path, create=False, exclusive=False)
        try:
            connection = _open_validated_connection(path, pinned)
            return cls(path, pinned, connection, lock_descriptor)
        except Exception:
            os.close(lock_descriptor)
            raise

    def close(self) -> None:
        """Close the SQLite connection without changing pinned state."""

        try:
            self._connection.close()
        finally:
            if self._lock_descriptor >= 0:
                os.close(self._lock_descriptor)
                self._lock_descriptor = -1

    def __enter__(self) -> ReplayStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def runtime_pragmas(self) -> dict[str, int | str]:
        """Return the exact active SQLite settings used by the claim."""

        return {
            "journal_mode": str(
                self._connection.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower(),
            "synchronous": int(self._connection.execute("PRAGMA synchronous").fetchone()[0]),
            "foreign_keys": int(self._connection.execute("PRAGMA foreign_keys").fetchone()[0]),
            "trusted_schema": int(self._connection.execute("PRAGMA trusted_schema").fetchone()[0]),
            "busy_timeout": int(self._connection.execute("PRAGMA busy_timeout").fetchone()[0]),
        }

    def commit_sequence(self, key: ReplayKey, sequence: int) -> None:
        """Atomically accept a strictly higher sequence before any consumer handoff."""

        self._commit_sequence(key, sequence, failpoint=None)

    def _commit_sequence(
        self,
        key: ReplayKey,
        sequence: int,
        *,
        failpoint: str | None,
    ) -> None:
        key = validate_replay_key(key)
        sequence = require_safe_int(sequence, "forwarding sequence", positive=True)
        if key.recovery_epoch != self.pinned.recovery_epoch:
            raise PrototypeError(ErrorCode.REPLAY, "forwarding recovery epoch is stale")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            accepted = self._connection.execute(_UPSERT, key.values(sequence)).fetchone()
            if accepted != (sequence,):
                self._connection.execute("ROLLBACK")
                raise PrototypeError(ErrorCode.REPLAY, "equal or lower forwarding sequence")
            if failpoint == "before_commit":
                os._exit(70)
            self._connection.execute("COMMIT")
            if failpoint == "after_commit":
                os._exit(71)
        except PrototypeError:
            raise
        except sqlite3.Error as error:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise PrototypeError(
                ErrorCode.STORAGE,
                f"SQLite replay commit failed: {error}",
            ) from error


def validate_replay_key(key: ReplayKey) -> ReplayKey:
    """Validate the complete replay scope independently of envelope parsing."""

    require_id(key.signer, "replay signer")
    require_id(key.receiver, "replay receiver")
    require_literal(key.route, "replay route", 256)
    if key.plane not in {"control", "perception", "action", "observation"}:
        raise PrototypeError(ErrorCode.REPLAY, "replay plane is unknown")
    require_literal(key.message_class, "replay message class", 64)
    require_id(key.session_id, "replay session_id")
    require_uuid_v4(key.session_generation, "replay session_generation")
    require_uuid_v4(key.forwarding_epoch, "replay forwarding_epoch")
    require_safe_int(key.key_epoch, "replay key_epoch", positive=True)
    require_safe_int(key.recovery_epoch, "replay recovery_epoch", positive=True)
    return key
