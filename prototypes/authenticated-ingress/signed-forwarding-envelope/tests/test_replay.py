"""Crash, concurrency, restart, corruption, and recovery tests."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from dataclasses import asdict, replace
from pathlib import Path

from nacl.signing import SigningKey

from prototype.forwarding import verify_and_commit
from prototype.replay import (
    MAX_REPLAY_DATABASE_BYTES,
    MAX_REPLAY_SCOPES,
    PinnedReplayState,
    ReplayKey,
    ReplayStore,
    build_recovery_authorization,
)
from prototype.strict import PrototypeError, b64url_encode, sha256_hex
from tests.common import (
    AUDIENCE,
    NOW,
    initialize_store,
    material,
    resigned,
)

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "tests" / "replay_worker.py"


def replay_key(recovery_epoch: int = 1) -> ReplayKey:
    return ReplayKey(
        signer="controller-principal-1",
        receiver=AUDIENCE,
        route="ncp/plant/body-1/command",
        plane="control",
        message_class="command_frame",
        session_id="vec-open-1",
        session_generation="293279f3-d459-4bfd-aeeb-604799e96925",
        forwarding_epoch="30000000-0000-4000-8000-000000000003",
        key_epoch=1,
        recovery_epoch=recovery_epoch,
    )


def worker_request(
    path: Path,
    pinned: PinnedReplayState,
    *,
    sequence: int,
    failpoint: str | None = None,
    marker: Path | None = None,
) -> dict[str, object]:
    return {
        "consumer_marker": str(marker) if marker else None,
        "failpoint": failpoint,
        "key": asdict(replay_key(pinned.recovery_epoch)),
        "path": str(path),
        "recovery_epoch": pinned.recovery_epoch,
        "sequence": sequence,
        "store_id": pinned.store_id,
    }


def run_worker(request: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WORKER)],
        cwd=ROOT,
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )


class ReplayTests(unittest.TestCase):
    def test_runtime_pragmas_restart_and_equal_lower_replay(self) -> None:
        owner = SigningKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), owner)
            with ReplayStore.open(path, pinned) as store:
                self.assertEqual(
                    store.runtime_pragmas(),
                    {
                        "busy_timeout": 5_000,
                        "foreign_keys": 1,
                        "journal_mode": "wal",
                        "synchronous": 2,
                        "trusted_schema": 0,
                    },
                )
                store.commit_sequence(replay_key(), 7)
            with ReplayStore.open(path, pinned) as restarted:
                with self.assertRaisesRegex(PrototypeError, "equal or lower"):
                    restarted.commit_sequence(replay_key(), 7)
                with self.assertRaisesRegex(PrototypeError, "equal or lower"):
                    restarted.commit_sequence(replay_key(), 6)
                restarted.commit_sequence(replay_key(), 8)
                with self.assertRaisesRegex(PrototypeError, "bounded literal"):
                    restarted.commit_sequence(
                        replace(replay_key(), route="ncp/*"),
                        9,
                    )

    def test_missing_corrupt_mismatched_and_insecure_state_fail_closed(self) -> None:
        owner = SigningKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            os.chmod(directory, 0o700)
            pinned = PinnedReplayState(str(uuid.uuid4()), 1)
            with self.assertRaises(PrototypeError):
                ReplayStore.open(directory / "missing.sqlite3", pinned)

            path = directory / "corrupt.sqlite3"
            path.write_bytes(b"not sqlite")
            os.chmod(path, 0o600)
            corrupt_lock = Path(f"{path}.lock")
            corrupt_lock.touch(mode=0o600)
            with self.assertRaises(PrototypeError):
                ReplayStore.open(path, pinned)
            with self.assertRaisesRegex(PrototypeError, "absent replay database"):
                initialize_store(directory, owner, path=path)
            path.unlink()

            path, actual = initialize_store(directory, owner, path=path)
            with self.assertRaisesRegex(PrototypeError, "identity mismatch"):
                ReplayStore.open(path, PinnedReplayState(str(uuid.uuid4()), 1))

            os.chmod(path, 0o644)
            with self.assertRaisesRegex(PrototypeError, "group or other"):
                ReplayStore.open(path, actual)

            oversized = directory / "oversized.sqlite3"
            with oversized.open("wb") as stream:
                stream.truncate(MAX_REPLAY_DATABASE_BYTES + 1)
            os.chmod(oversized, 0o600)
            oversized_lock = Path(f"{oversized}.lock")
            oversized_lock.touch(mode=0o600)
            with self.assertRaisesRegex(PrototypeError, "byte bound"):
                ReplayStore.open(oversized, actual)

            sidecar = Path(f"{path}-wal")
            os.chmod(path, 0o600)
            with sidecar.open("wb") as stream:
                stream.truncate(MAX_REPLAY_DATABASE_BYTES + 1)
            os.chmod(sidecar, 0o600)
            with self.assertRaisesRegex(PrototypeError, "sidecar"):
                ReplayStore.open(path, actual)
            sidecar.unlink()

            schema_path, schema_pinned = initialize_store(
                directory,
                owner,
                path=directory / "schema.sqlite3",
            )
            connection = sqlite3.connect(schema_path)
            try:
                connection.execute("DROP TRIGGER high_water_capacity")
                connection.execute(
                    """
                    CREATE TRIGGER high_water_capacity
                    BEFORE INSERT ON high_water
                    BEGIN
                        SELECT 1;
                    END
                    """
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(PrototypeError, "schema SQL"):
                ReplayStore.open(schema_path, schema_pinned)

    def test_replay_scope_capacity_fails_closed_without_blocking_existing_scope(self) -> None:
        owner = SigningKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), owner)
            first: ReplayKey | None = None
            with ReplayStore.open(path, pinned) as store:
                for index in range(MAX_REPLAY_SCOPES):
                    key = replace(replay_key(), forwarding_epoch=str(uuid.uuid4()))
                    first = first or key
                    store.commit_sequence(key, 1)
                self.assertIsNotNone(first)
                store.commit_sequence(first, 2)
                with self.assertRaisesRegex(PrototypeError, "capacity exhausted"):
                    store.commit_sequence(
                        replace(replay_key(), forwarding_epoch=str(uuid.uuid4())),
                        1,
                    )

    def test_concurrent_duplicate_processes_commit_exactly_once(self) -> None:
        owner = SigningKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), owner)
            request = worker_request(path, pinned, sequence=11)
            processes = [
                subprocess.Popen(
                    [sys.executable, str(WORKER)],
                    cwd=ROOT,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]
            outputs = [
                process.communicate(json.dumps(request), timeout=10) for process in processes
            ]
            codes = [process.returncode for process in processes]
            self.assertCountEqual(codes, [0, 3], outputs)

    def test_crash_before_commit_allows_retry_after_commit_rejects_and_loses_handoff(self) -> None:
        owner = SigningKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, pinned = initialize_store(directory, owner)
            before = run_worker(
                worker_request(path, pinned, sequence=20, failpoint="before_commit")
            )
            self.assertEqual(before.returncode, 70, before.stderr)
            with ReplayStore.open(path, pinned) as store:
                store.commit_sequence(replay_key(), 20)

            marker = directory / "consumer-marker"
            after = run_worker(
                worker_request(
                    path,
                    pinned,
                    sequence=21,
                    failpoint="after_commit",
                    marker=marker,
                )
            )
            self.assertEqual(after.returncode, 71, after.stderr)
            self.assertFalse(marker.exists())
            with ReplayStore.open(path, pinned) as store:
                with self.assertRaisesRegex(PrototypeError, "equal or lower"):
                    store.commit_sequence(replay_key(), 21)

    def test_owner_recovery_epoch_is_signed_and_invalidates_every_old_envelope(self) -> None:
        value = material(recovery_epoch=1)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, pinned_one = initialize_store(directory, value.owner)
            with ReplayStore.open(path, pinned_one) as store:
                verify_and_commit(
                    value.envelope,
                    manifest=value.manifest,
                    profile=value.profile,
                    carrier=value.carrier,
                    replay_store=store,
                    now_utc_ms=NOW,
                )
                with self.assertRaisesRegex(PrototypeError, "active"):
                    initialize_store(
                        directory,
                        value.owner,
                        old=pinned_one,
                        new_epoch=2,
                        path=path,
                    )

            path, pinned_two = initialize_store(
                directory,
                value.owner,
                old=pinned_one,
                new_epoch=2,
                path=path,
            )
            profile_two = replace(value.profile, recovery_epoch=2)
            with ReplayStore.open(path, pinned_two) as store:
                with self.assertRaisesRegex(PrototypeError, "recovery_epoch"):
                    verify_and_commit(
                        value.envelope,
                        manifest=value.manifest,
                        profile=profile_two,
                        carrier=value.carrier,
                        replay_store=store,
                        now_utc_ms=NOW,
                    )
                context_two = copy.deepcopy(value.ncp_context)
                context_two["recovery_epoch"] = 2
                accepted = verify_and_commit(
                    resigned(value, context_two),
                    manifest=value.manifest,
                    profile=profile_two,
                    carrier=value.carrier,
                    replay_store=store,
                    now_utc_ms=NOW,
                )
                self.assertEqual(accepted.context.recovery_epoch, 2)

    def test_wrong_owner_stale_and_nonadvancing_recovery_authorizations_reject(self) -> None:
        owner = SigningKey.generate()
        attacker = SigningKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path, pinned = initialize_store(directory, owner)

            authorization, signature = build_recovery_authorization(
                attacker,
                action="recover",
                audience=AUDIENCE,
                old=pinned,
                new_store_id=str(uuid.uuid4()),
                new_recovery_epoch=2,
                issued_at_utc_ms=NOW,
                expires_at_utc_ms=NOW + 1_000,
            )
            with self.assertRaisesRegex(PrototypeError, "signature"):
                ReplayStore.provision(
                    path,
                    authorization,
                    signature,
                    owner_public_key=owner.verify_key.encode(),
                    owner_key_sha256=sha256_hex(owner.verify_key.encode()),
                    audience=AUDIENCE,
                    old=pinned,
                    now_utc_ms=NOW,
                )

            stale, stale_signature = build_recovery_authorization(
                owner,
                action="recover",
                audience=AUDIENCE,
                old=pinned,
                new_store_id=str(uuid.uuid4()),
                new_recovery_epoch=2,
                issued_at_utc_ms=NOW - 20_000,
                expires_at_utc_ms=NOW - 10_000,
            )
            with self.assertRaisesRegex(PrototypeError, "currently valid"):
                ReplayStore.provision(
                    path,
                    stale,
                    stale_signature,
                    owner_public_key=owner.verify_key.encode(),
                    owner_key_sha256=sha256_hex(owner.verify_key.encode()),
                    audience=AUDIENCE,
                    old=pinned,
                    now_utc_ms=NOW,
                )

            nonadvancing, nonadvancing_signature = build_recovery_authorization(
                owner,
                action="recover",
                audience=AUDIENCE,
                old=pinned,
                new_store_id=str(uuid.uuid4()),
                new_recovery_epoch=1,
                issued_at_utc_ms=NOW,
                expires_at_utc_ms=NOW + 1_000,
            )
            with self.assertRaisesRegex(PrototypeError, "advance"):
                ReplayStore.provision(
                    path,
                    nonadvancing,
                    nonadvancing_signature,
                    owner_public_key=owner.verify_key.encode(),
                    owner_key_sha256=sha256_hex(owner.verify_key.encode()),
                    audience=AUDIENCE,
                    old=pinned,
                    now_utc_ms=NOW,
                )

            reused, reused_signature = build_recovery_authorization(
                owner,
                action="recover",
                audience=AUDIENCE,
                old=pinned,
                new_store_id=pinned.store_id,
                new_recovery_epoch=2,
                issued_at_utc_ms=NOW,
                expires_at_utc_ms=NOW + 1_000,
            )
            with self.assertRaisesRegex(PrototypeError, "new pinned state"):
                ReplayStore.provision(
                    path,
                    reused,
                    reused_signature,
                    owner_public_key=owner.verify_key.encode(),
                    owner_key_sha256=sha256_hex(owner.verify_key.encode()),
                    audience=AUDIENCE,
                    old=pinned,
                    now_utc_ms=NOW,
                )

            oversized_authorization = b"x" * 8_193
            oversized_signature = b64url_encode(owner.sign(oversized_authorization).signature)
            with self.assertRaisesRegex(PrototypeError, "byte length"):
                ReplayStore.provision(
                    path,
                    oversized_authorization,
                    oversized_signature,
                    owner_public_key=owner.verify_key.encode(),
                    owner_key_sha256=sha256_hex(owner.verify_key.encode()),
                    audience=AUDIENCE,
                    old=pinned,
                    now_utc_ms=NOW,
                )

            fake_old = PinnedReplayState(str(uuid.uuid4()), pinned.recovery_epoch)
            mismatched, mismatched_signature = build_recovery_authorization(
                owner,
                action="recover",
                audience=AUDIENCE,
                old=fake_old,
                new_store_id=str(uuid.uuid4()),
                new_recovery_epoch=2,
                issued_at_utc_ms=NOW,
                expires_at_utc_ms=NOW + 1_000,
            )
            with self.assertRaisesRegex(PrototypeError, "existing valid store"):
                ReplayStore.provision(
                    path,
                    mismatched,
                    mismatched_signature,
                    owner_public_key=owner.verify_key.encode(),
                    owner_key_sha256=sha256_hex(owner.verify_key.encode()),
                    audience=AUDIENCE,
                    old=fake_old,
                    now_utc_ms=NOW,
                )


if __name__ == "__main__":
    unittest.main()
