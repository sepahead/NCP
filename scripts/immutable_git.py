#!/usr/bin/env python3
"""Bounded literal Git-object reads for immutable B01 evidence cuts.

This module resolves only caller-supplied SHA-1 object IDs. It does not use a
branch, tag, replacement object, graft, shallow boundary, or alternate object
store as evidence authority.
"""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import NoReturn

HEX40 = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
MAX_COMMIT_BYTES = 4 * 1024 * 1024
MAX_TREE_BYTES = 16 * 1024 * 1024
MAX_TREE_ENTRIES = 100_000
MAX_TREE_DEPTH = 64
MAX_COMMIT_PARENTS = 64
MAX_ANCESTRY_COMMITS = 4_096
MAX_ANCESTRY_EDGES = 16_384
MAX_OPERATION_OBJECTS = 20_000
MAX_OPERATION_BYTES = 512 * 1024 * 1024
MAX_OPERATION_TREE_ENTRIES = 500_000
MAX_OPERATION_PROCESSES = MAX_OPERATION_OBJECTS + 16
MAX_OPERATION_SECONDS = 30
MAX_OBJECT_SECONDS = 15
MAX_STDERR_BYTES = 4_096
GIT_BINARY = "/usr/bin/git"
FIXED_PATH = "/usr/bin:/bin"


class ImmutableGitError(RuntimeError):
    """A literal Git source cannot be reopened within the fixed bounds."""


@dataclass(frozen=True)
class GitBlobSnapshot:
    """Exact bytes observed for one regular blob at one commit."""

    path: str
    sha256: str
    bytes: int
    raw: bytes

    def identity(self) -> dict[str, str | int]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes}


_DIRECTORY_IDENTITY_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_gid",
    "st_nlink",
)
_PARENT_IDENTITY_FIELDS = _DIRECTORY_IDENTITY_FIELDS[:-1]


def _directory_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return tuple(getattr(metadata, field) for field in _DIRECTORY_IDENTITY_FIELDS)


def _parent_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return tuple(getattr(metadata, field) for field in _PARENT_IDENTITY_FIELDS)


def _fail(message: str) -> NoReturn:
    raise ImmutableGitError(message)


def _add_exception_note(primary: BaseException, note: str) -> None:
    """Retain a fence detail without replacing the primary exception."""

    add_note = getattr(primary, "add_note", None)
    if callable(add_note):
        add_note(note)
        return
    notes = getattr(primary, "__notes__", None)
    if not isinstance(notes, list):
        notes = []
        setattr(primary, "__notes__", notes)
    notes.append(note)


def _checked_sha1(value: str, label: str) -> str:
    if not isinstance(value, str) or HEX40.fullmatch(value) is None:
        _fail(f"{label} must be a lowercase SHA-1 object ID")
    return value


def _checked_relative_path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a bounded repository-relative path")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ImmutableGitError(f"{label} is not valid UTF-8") from error
    if len(encoded) > 2_048:
        _fail(f"{label} must be a bounded repository-relative path")
    candidate = PurePosixPath(value)
    if (
        value.startswith("./")
        or "\\" in value
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or candidate.as_posix() != value
    ):
        _fail(f"{label} must be a canonical repository-relative path")
    return value


def git_environment() -> dict[str, str]:
    """Return the closed environment used for local Git reads."""

    environment = {
        "PATH": FIXED_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    if "SYSTEMROOT" in os.environ:
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return environment


def _git_binary() -> str:
    return GIT_BINARY


def _fixed_git_identity() -> tuple[int, ...]:
    try:
        metadata = os.lstat(GIT_BINARY)
    except OSError as error:
        raise ImmutableGitError("cannot inspect the fixed Git executable") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
        or metadata.st_mode & 0o111 == 0
    ):
        _fail(
            "the fixed Git executable must be root-owned, executable, "
            "non-writable by group or world, and one regular file"
        )
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_fixed_git_unchanged(expected: tuple[int, ...]) -> None:
    if _fixed_git_identity() != expected:
        _fail("the fixed Git executable changed during the immutable Git operation")


def _run_control(
    operation: _Operation,
    arguments: list[str],
    label: str,
    *,
    maximum: int = 4_096,
) -> bytes:
    if not 1 <= maximum <= 4 * 1024 * 1024:
        _fail(f"{label} has an invalid control-output bound")
    operation.consume_process(label)
    with _pinned_git_child(operation, label) as (child_cwd, pass_fds):
        try:
            process = subprocess.Popen(  # noqa: S603
                [_git_binary(), "--no-replace-objects", *arguments],
                cwd=child_cwd,
                env=git_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                pass_fds=pass_fds,
            )
        except OSError as error:
            raise ImmutableGitError(f"{label} did not complete") from error
        output, error_output, return_code = _collect(
            process,
            stdout_limit=maximum,
            label=label,
            deadline=operation.deadline,
        )
        if return_code != 0:
            detail = error_output.decode("utf-8", errors="replace")
            _fail(f"{label} failed: {detail.strip() or 'git returned nonzero'}")
        return output


def control_output(
    arguments: list[str],
    *,
    root: Path,
    maximum: int,
    label: str,
) -> bytes:
    """Run one bounded fixed-Git control query inside the shared operation."""

    if (
        not isinstance(arguments, list)
        or not arguments
        or any(not isinstance(argument, str) or not argument for argument in arguments)
    ):
        _fail(f"{label} has invalid Git control arguments")
    is_remote_query = arguments in (
        ["remote", "get-url", "--all", "origin"],
        ["remote", "get-url", "--push", "--all", "origin"],
    )
    is_branch_check = len(arguments) == 3 and arguments[:2] == [
        "check-ref-format",
        "--branch",
    ]
    is_type_query = (
        len(arguments) == 3
        and arguments[:2] == ["cat-file", "-t"]
        and HEX40.fullmatch(arguments[2]) is not None
    )
    allowed_revisions = {"HEAD^{commit}", "HEAD^1^{commit}"}
    is_revision_query = (
        len(arguments) in {2, 3}
        and arguments[0] == "rev-parse"
        and (len(arguments) == 2 or arguments[1] == "--verify")
        and (
            arguments[-1] in allowed_revisions
            or (
                arguments[-1].endswith("^{commit}")
                and HEX40.fullmatch(arguments[-1][:-9]) is not None
            )
        )
    )
    if not (is_remote_query or is_branch_check or is_type_query or is_revision_query):
        _fail(f"{label} is outside the closed read-only Git control profile")
    with shared_operation(root=root) as operation:
        return _run_control(
            operation,
            arguments,
            label,
            maximum=maximum,
        )


def _absolute_control_path(raw: bytes, label: str) -> Path:
    if not 1 <= len(raw) <= 4_096 or raw.count(b"\n") > 1:
        _fail(f"{label} output is malformed")
    try:
        rendered = raw.decode("utf-8", errors="strict").rstrip("\n")
    except UnicodeDecodeError as error:
        raise ImmutableGitError(f"{label} output is not UTF-8") from error
    path = Path(rendered)
    if not rendered or "\n" in rendered or "\x00" in rendered or not path.is_absolute():
        _fail(f"{label} did not return one absolute path")
    return path


def _forbidden_control_path(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise ImmutableGitError(f"cannot inspect {label}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail(f"{label} control path is not one regular file")
    _fail(f"{label} is forbidden for an immutable Git cut")


def _require_unmodified_git_history(operation: _Operation) -> None:
    if (
        _run_control(
            operation,
            ["rev-parse", "--show-object-format"],
            "Git object format",
        )
        != b"sha1\n"
    ):
        _fail("immutable Git tooling requires one exact SHA-1 object format")
    common = _absolute_control_path(
        _run_control(
            operation,
            ["rev-parse", "--path-format=absolute", "--git-common-dir"],
            "Git common directory",
        ),
        "Git common directory",
    )
    git_dir = _absolute_control_path(
        _run_control(
            operation,
            ["rev-parse", "--path-format=absolute", "--git-dir"],
            "Git directory",
        ),
        "Git directory",
    )
    for path, label in (
        (common / "info" / "grafts", "Git graft file"),
        (common / "objects" / "info" / "alternates", "Git object alternates"),
        (common / "shallow", "shallow Git boundary"),
        (git_dir / "shallow", "shallow Git worktree boundary"),
    ):
        _forbidden_control_path(path, label)
    replacements = _run_control(
        operation,
        ["for-each-ref", "--format=%(refname)", "refs/replace/"],
        "Git replacement refs",
    )
    if replacements.strip():
        _fail("Git replacement refs are forbidden for an immutable Git cut")


def require_unmodified_git_history(*, root: Path) -> None:
    """Reject local mechanisms that can replace or detach commit history."""

    with shared_operation(root=root) as operation:
        _require_unmodified_git_history(operation)


@dataclass(frozen=True)
class _RootAnchor:
    root_descriptor: int
    parent_descriptor: int
    leaf: str
    root_identity: tuple[int, ...]
    parent_identity: tuple[int, ...]
    child_cwd: str


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _open_root_anchor(root: Path) -> _RootAnchor:
    """Pin one repository directory and its immediate parent without symlinks."""

    if not root.is_absolute() or root.parent == root or not root.name:
        _fail("immutable Git root must be one non-root absolute directory")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor: int | None = None
    root_descriptor: int | None = None
    completed = False
    try:
        parent_descriptor = os.open(root.parent, flags)
        root_descriptor = os.open(root.name, flags, dir_fd=parent_descriptor)
        parent_metadata = os.fstat(parent_descriptor)
        root_metadata = os.fstat(root_descriptor)
        named_metadata = os.stat(
            root.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(parent_metadata.st_mode)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or _directory_identity(root_metadata) != _directory_identity(named_metadata)
        ):
            _fail("immutable Git root is not one stable no-follow directory")
        if sys.platform == "darwin":
            child_cwd = f"/.vol/{root_metadata.st_dev}/{root_metadata.st_ino}"
        elif Path("/proc/self/fd").is_dir():
            child_cwd = f"/proc/self/fd/{root_descriptor}"
        else:
            _fail("this host lacks a supported pinned-directory child path")
        pinned_metadata = os.stat(child_cwd, follow_symlinks=True)
        if _directory_identity(pinned_metadata) != _directory_identity(root_metadata):
            _fail("pinned immutable Git child path differs from the root descriptor")
        anchor = _RootAnchor(
            root_descriptor=root_descriptor,
            parent_descriptor=parent_descriptor,
            leaf=root.name,
            root_identity=_directory_identity(root_metadata),
            parent_identity=_parent_identity(parent_metadata),
            child_cwd=child_cwd,
        )
        completed = True
        return anchor
    except ImmutableGitError:
        raise
    except OSError as error:
        raise ImmutableGitError("cannot pin the immutable Git root") from error
    finally:
        if root_descriptor is not None and not completed:
            _close_descriptor(root_descriptor)
        if parent_descriptor is not None and not completed:
            _close_descriptor(parent_descriptor)


def _close_root_anchor(anchor: _RootAnchor) -> None:
    _close_descriptor(anchor.root_descriptor)
    _close_descriptor(anchor.parent_descriptor)


def _require_root_anchor(anchor: _RootAnchor, label: str) -> None:
    try:
        root_metadata = os.fstat(anchor.root_descriptor)
        parent_metadata = os.fstat(anchor.parent_descriptor)
        named_metadata = os.stat(
            anchor.leaf,
            dir_fd=anchor.parent_descriptor,
            follow_symlinks=False,
        )
        pinned_metadata = os.stat(anchor.child_cwd, follow_symlinks=True)
    except OSError as error:
        raise ImmutableGitError(f"{label} cannot rejoin the pinned Git root") from error
    if (
        _directory_identity(root_metadata) != anchor.root_identity
        or _parent_identity(parent_metadata) != anchor.parent_identity
        or _directory_identity(named_metadata) != anchor.root_identity
        or _directory_identity(pinned_metadata) != anchor.root_identity
    ):
        _fail(f"{label} detected an immutable Git root directory change")


@dataclass
class _Budget:
    """One aggregate resource budget shared by every nested repository cut."""

    deadline: float = field(
        default_factory=lambda: time.monotonic() + MAX_OPERATION_SECONDS
    )
    objects: int = 0
    bytes: int = 0
    tree_entries: int = 0
    processes: int = 0

    def remaining(self, label: str) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            _fail(f"{label} exceeds the immutable Git operation deadline")
        return remaining

    def consume(self, size: int, label: str) -> None:
        self.objects += 1
        self.bytes += size
        if self.objects > MAX_OPERATION_OBJECTS or self.bytes > MAX_OPERATION_BYTES:
            _fail(f"{label} exceeds the aggregate Git object-read budget")

    def consume_tree_entries(self, count: int, label: str) -> None:
        self.tree_entries += count
        if self.tree_entries > MAX_OPERATION_TREE_ENTRIES:
            _fail(f"{label} exceeds the aggregate Git tree-entry budget")

    def consume_process(self, label: str) -> None:
        self.remaining(label)
        self.processes += 1
        if self.processes > MAX_OPERATION_PROCESSES:
            _fail(f"{label} exceeds the aggregate Git subprocess budget")


@dataclass
class _Operation:
    """One repository-local cache and fence set backed by a shared budget."""

    root: Path
    anchor: _RootAnchor
    budget: _Budget = field(default_factory=_Budget)
    cache: dict[tuple[str, str], bytes] = field(default_factory=dict)

    @property
    def deadline(self) -> float:
        return self.budget.deadline

    @property
    def objects(self) -> int:
        return self.budget.objects

    @property
    def bytes(self) -> int:
        return self.budget.bytes

    @property
    def tree_entries(self) -> int:
        return self.budget.tree_entries

    @property
    def processes(self) -> int:
        return self.budget.processes

    def remaining(self, label: str) -> float:
        return self.budget.remaining(label)

    def consume(self, size: int, label: str) -> None:
        self.budget.consume(size, label)

    def consume_tree_entries(self, count: int, label: str) -> None:
        self.budget.consume_tree_entries(count, label)

    def consume_process(self, label: str) -> None:
        self.budget.consume_process(label)

    def duplicate_root_descriptor(self, label: str) -> int:
        """Return a caller-owned descriptor for no-follow repository traversal."""

        _require_root_anchor(self.anchor, label)
        try:
            return os.dup(self.anchor.root_descriptor)
        except OSError as error:
            raise ImmutableGitError(
                f"{label} cannot duplicate the pinned Git root descriptor"
            ) from error


@contextmanager
def _pinned_git_child(operation: _Operation, label: str):
    """Fence one Git child around the operation's pinned repository inode."""

    _require_root_anchor(operation.anchor, f"{label} pre-child root fence")
    try:
        yield operation.anchor.child_cwd, (operation.anchor.root_descriptor,)
    except BaseException as primary:
        try:
            _require_root_anchor(operation.anchor, f"{label} post-child root fence")
        except ImmutableGitError as fence_error:
            _add_exception_note(
                primary,
                f"immutable Git child root fence also failed: {fence_error}",
            )
        raise
    else:
        _require_root_anchor(operation.anchor, f"{label} post-child root fence")


_ACTIVE_OPERATION: ContextVar[_Operation | None] = ContextVar(
    "ncp_immutable_git_operation", default=None
)


@contextmanager
def shared_operation(*, root: Path):
    """Share one bounded literal-Git budget across one logical validation."""

    lexical_root = root.absolute()
    active = _ACTIVE_OPERATION.get()
    if active is not None and active.root.absolute() == lexical_root:
        _require_root_anchor(active.anchor, "nested immutable Git root fence")
        try:
            yield active
        except BaseException as primary:
            try:
                _require_root_anchor(
                    active.anchor,
                    "nested immutable Git root rejoin",
                )
            except ImmutableGitError as fence_error:
                _add_exception_note(
                    primary,
                    f"nested immutable Git root fence also failed: {fence_error}",
                )
            raise
        else:
            _require_root_anchor(active.anchor, "nested immutable Git root rejoin")
        return
    budget = active.budget if active is not None else _Budget()
    budget.remaining("immutable Git root admission")
    anchor = _open_root_anchor(lexical_root)
    try:
        git_identity = _fixed_git_identity()
        operation = _Operation(root=lexical_root, anchor=anchor, budget=budget)
        token = _ACTIVE_OPERATION.set(operation)
        try:
            _require_unmodified_git_history(operation)
            try:
                yield operation
            except BaseException as primary:
                fence_failures: list[str] = []
                try:
                    _require_unmodified_git_history(operation)
                except ImmutableGitError as fence_error:
                    fence_failures.append(str(fence_error))
                try:
                    _require_fixed_git_unchanged(git_identity)
                except ImmutableGitError as executable_error:
                    fence_failures.append(str(executable_error))
                try:
                    _require_root_anchor(anchor, "immutable Git final root fence")
                except ImmutableGitError as root_error:
                    fence_failures.append(str(root_error))
                if fence_failures:
                    _add_exception_note(
                        primary,
                        "immutable Git final fence also failed: "
                        + "; ".join(fence_failures),
                    )
                raise
            else:
                _require_unmodified_git_history(operation)
                _require_fixed_git_unchanged(git_identity)
                _require_root_anchor(anchor, "immutable Git final root fence")
        finally:
            _ACTIVE_OPERATION.reset(token)
    finally:
        _close_root_anchor(anchor)


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _collect(
    process: subprocess.Popen[bytes],
    *,
    stdout_limit: int,
    label: str,
    deadline: float,
) -> tuple[bytes, bytes, int]:
    if process.stdout is None or process.stderr is None:
        _terminate(process)
        _fail(f"cannot open bounded Git streams for {label}")
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": MAX_STDERR_BYTES}
    streams = {process.stdout.fileno(): "stdout", process.stderr.fileno(): "stderr"}
    for descriptor in streams:
        selector.register(descriptor, selectors.EVENT_READ)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate(process)
                _fail(f"{label} exceeds the Git object-read deadline")
            events = selector.select(remaining)
            if not events:
                _terminate(process)
                _fail(f"{label} exceeds the Git object-read deadline")
            for key, _mask in events:
                descriptor = key.fd
                name = streams[descriptor]
                allowance = limits[name] - len(buffers[name])
                chunk = os.read(descriptor, min(64 * 1024, allowance + 1))
                if not chunk:
                    selector.unregister(descriptor)
                    continue
                buffers[name].extend(chunk)
                if len(buffers[name]) > limits[name]:
                    _terminate(process)
                    _fail(f"{label} {name} exceeds its byte bound")
        remaining = max(0.001, deadline - time.monotonic())
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _terminate(process)
            _fail(f"{label} exceeds the Git object-read deadline")
        return bytes(buffers["stdout"]), bytes(buffers["stderr"]), return_code
    except OSError as error:
        _terminate(process)
        raise ImmutableGitError(
            f"cannot collect bounded Git bytes for {label}"
        ) from error
    finally:
        selector.close()


def _read_object(
    operation: _Operation,
    object_id: str,
    expected_type: str,
    *,
    maximum: int,
    label: str,
) -> bytes:
    checked = _checked_sha1(object_id, f"{label} object ID")
    if expected_type not in {"blob", "commit", "tree"}:
        _fail(f"{label} expected Git object type is unsupported")
    cached = operation.cache.get((checked, expected_type))
    if cached is not None:
        if len(cached) > maximum:
            _fail(f"{label} cached Git object exceeds its byte bound")
        return cached
    operation.consume_process(label)
    object_deadline = min(
        operation.deadline,
        time.monotonic() + min(MAX_OBJECT_SECONDS, operation.remaining(label)),
    )
    with _pinned_git_child(operation, label) as (child_cwd, pass_fds):
        try:
            process = subprocess.Popen(  # noqa: S603
                [_git_binary(), "--no-replace-objects", "cat-file", "--batch"],
                cwd=child_cwd,
                env=git_environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                pass_fds=pass_fds,
            )
        except OSError as error:
            raise ImmutableGitError(
                f"cannot start bounded Git reader for {label}"
            ) from error
        try:
            if process.stdin is None:
                _terminate(process)
                _fail(f"cannot open bounded Git object reader for {label}")
            process.stdin.write(f"{checked}\n".encode("ascii"))
            process.stdin.close()
            output, error_output, return_code = _collect(
                process,
                stdout_limit=maximum + 256,
                label=label,
                deadline=object_deadline,
            )
            header_end = output.find(b"\n")
            if not 1 <= header_end < 256:
                _fail(f"{label} Git batch header is missing or over-bound")
            match = re.fullmatch(
                rb"([0-9a-f]{40}) (blob|commit|tree) ([0-9]{1,12})\n",
                output[: header_end + 1],
            )
            if match is None:
                _fail(f"{label} does not resolve to one bounded raw Git object")
            observed_id = match.group(1).decode("ascii")
            observed_type = match.group(2).decode("ascii")
            size = int(match.group(3))
            if observed_id != checked or observed_type != expected_type:
                _fail(f"{label} resolves to the wrong Git identity or type")
            minimum = 1 if expected_type == "commit" else 0
            if not minimum <= size <= maximum:
                _fail(f"{label} Git object size is outside {minimum}..{maximum}")
            if len(output) != header_end + 1 + size + 1 or output[-1:] != b"\n":
                _fail(f"{label} Git object is truncated or has trailing output")
            if return_code != 0:
                detail = error_output.decode("utf-8", errors="replace").strip()
                _fail(f"{label} Git reader failed: {detail or 'nonzero exit'}")
            content = output[header_end + 1 : -1]
            object_header = f"{observed_type} {size}\0".encode("ascii")
            recomputed = hashlib.sha1(  # noqa: S324
                object_header + content, usedforsecurity=False
            ).hexdigest()
            if recomputed != checked:
                _fail(f"{label} raw bytes do not match their Git object ID")
            operation.consume(size, label)
            operation.cache[(checked, expected_type)] = content
            return content
        except (BrokenPipeError, OSError) as error:
            _terminate(process)
            raise ImmutableGitError(
                f"cannot read bounded Git object for {label}"
            ) from error


def _read_commit(
    operation: _Operation, commit: str, *, label: str
) -> tuple[str, list[str]]:
    content = _read_object(
        operation,
        commit,
        "commit",
        maximum=MAX_COMMIT_BYTES,
        label=label,
    )
    if b"\x00" in content:
        _fail(f"{label} raw commit contains NUL")
    header, separator, _message = content.partition(b"\n\n")
    if not separator or any(
        byte == 0x7F or (byte < 0x20 and byte not in {0x09, 0x0A}) for byte in header
    ):
        _fail(f"{label} raw commit lacks a canonical header boundary")
    lines = header.split(b"\n")
    if not lines or re.fullmatch(rb"tree ([0-9a-f]{40})", lines[0]) is None:
        _fail(f"{label} raw commit lacks one leading tree header")
    tree = lines[0][5:].decode("ascii")
    parents: list[str] = []
    index = 1
    while index < len(lines) and lines[index].startswith(b"parent "):
        if re.fullmatch(rb"parent ([0-9a-f]{40})", lines[index]) is None:
            _fail(f"{label} raw commit contains a malformed parent")
        parents.append(lines[index][7:].decode("ascii"))
        index += 1
    remaining = lines[index:]
    if (
        len(remaining) < 2
        or not remaining[0].startswith(b"author ")
        or len(remaining[0]) == len(b"author ")
        or not remaining[1].startswith(b"committer ")
        or len(remaining[1]) == len(b"committer ")
        or any(line.startswith((b"tree ", b"parent ")) for line in remaining)
    ):
        _fail(f"{label} raw commit headers are noncanonical")
    if len(parents) > MAX_COMMIT_PARENTS or len(parents) != len(set(parents)):
        _fail(f"{label} raw commit parent roster is invalid")
    return tree, parents


def _read_tree_entries(
    operation: _Operation, tree_id: str, *, label: str
) -> list[tuple[str, bytes, str]]:
    tree = _read_object(
        operation,
        tree_id,
        "tree",
        maximum=MAX_TREE_BYTES,
        label=label,
    )
    entries: list[tuple[str, bytes, str]] = []
    position = 0
    seen: set[bytes] = set()
    prior: bytes | None = None
    while position < len(tree):
        separator = tree.find(b" ", position)
        terminator = tree.find(b"\x00", separator + 1) if separator >= 0 else -1
        if separator <= position or terminator <= separator + 1:
            _fail(f"{label} contains a malformed raw tree entry")
        object_end = terminator + 21
        if object_end > len(tree):
            _fail(f"{label} contains a truncated raw tree object ID")
        mode_bytes = tree[position:separator]
        name = tree[separator + 1 : terminator]
        object_id = tree[terminator + 1 : object_end].hex()
        if mode_bytes not in {b"40000", b"100644", b"100755", b"120000", b"160000"}:
            _fail(f"{label} contains a noncanonical raw tree mode")
        if not name or b"/" in name or name in seen:
            _fail(f"{label} contains an invalid or duplicate raw tree name")
        seen.add(name)
        sort_key = name + (b"/" if mode_bytes == b"40000" else b"\x00")
        if prior is not None and sort_key <= prior:
            _fail(f"{label} contains noncanonical raw tree ordering")
        prior = sort_key
        entries.append((mode_bytes.decode("ascii"), name, object_id))
        if len(entries) > MAX_TREE_ENTRIES:
            _fail(f"{label} exceeds the raw tree-entry bound")
        position = object_end
    if position != len(tree):
        _fail(f"{label} raw tree has trailing bytes")
    operation.consume_tree_entries(len(entries), label)
    return entries


def read_object(
    object_id: str,
    expected_type: str,
    *,
    maximum: int,
    label: str,
    root: Path,
) -> bytes:
    with shared_operation(root=root) as operation:
        return _read_object(
            operation,
            object_id,
            expected_type,
            maximum=maximum,
            label=label,
        )


def read_commit(commit: str, *, label: str, root: Path) -> tuple[str, list[str]]:
    checked = _checked_sha1(commit, label)
    with shared_operation(root=root) as operation:
        return _read_commit(operation, checked, label=label)


def commit_tree(commit: str, *, root: Path) -> str:
    checked = _checked_sha1(commit, "Git commit")
    with shared_operation(root=root) as operation:
        tree, _parents = _read_commit(operation, checked, label="Git commit")
        _read_tree_entries(operation, tree, label="Git commit root tree")
        return tree


def require_ancestor(
    ancestor: str,
    descendant: str,
    *,
    root: Path,
    allow_equal: bool,
    label: str,
    commit_bound: int = MAX_ANCESTRY_COMMITS,
    edge_bound: int = MAX_ANCESTRY_EDGES,
) -> None:
    expected = _checked_sha1(ancestor, f"{label} ancestor")
    start = _checked_sha1(descendant, f"{label} descendant")
    if not 1 <= commit_bound <= MAX_ANCESTRY_COMMITS:
        _fail("raw Git ancestry commit bound is invalid")
    if not 0 <= edge_bound <= MAX_ANCESTRY_EDGES:
        _fail("raw Git ancestry edge bound is invalid")
    with shared_operation(root=root) as operation:
        _read_commit(operation, expected, label=f"{label} expected ancestor")
        if expected == start:
            if allow_equal:
                return
            _fail(f"{label} must be a strict ancestor")
        pending = [start]
        discovered = {start}
        visited: set[str] = set()
        edges = 0
        while pending:
            operation.remaining(label)
            current = pending.pop()
            if current == expected:
                return
            if current in visited:
                continue
            visited.add(current)
            if len(visited) > commit_bound:
                _fail(f"{label} exceeds the {commit_bound}-commit verification bound")
            _tree, parents = _read_commit(
                operation, current, label=f"{label} commit {current}"
            )
            for parent in reversed(parents):
                edges += 1
                if edges > edge_bound:
                    _fail(f"{label} exceeds the {edge_bound}-edge verification bound")
                if parent not in discovered:
                    discovered.add(parent)
                    if len(discovered) > commit_bound:
                        _fail(
                            f"{label} exceeds the {commit_bound}-commit "
                            "verification bound"
                        )
                    pending.append(parent)
        _fail(f"{label} does not establish the required ancestry")


def read_tree_entry(
    tree_id: str,
    component: bytes,
    *,
    label: str,
    root: Path,
) -> tuple[str, str]:
    checked = _checked_sha1(tree_id, f"{label} tree")
    if not isinstance(component, bytes) or not component or b"/" in component:
        _fail(f"{label} requested tree component is invalid")
    with shared_operation(root=root) as operation:
        matches = [
            (mode, object_id)
            for mode, name, object_id in _read_tree_entries(
                operation, checked, label=label
            )
            if name == component
        ]
        if len(matches) != 1:
            _fail(f"{label} does not contain one exact requested tree entry")
        return matches[0]


def blob_snapshot(
    commit: str,
    relative: str,
    *,
    maximum: int,
    root: Path,
) -> GitBlobSnapshot:
    checked_commit = _checked_sha1(commit, "Git blob commit")
    checked_path = _checked_relative_path(relative, "Git blob path")
    parts = PurePosixPath(checked_path).parts
    if not parts or len(parts) > MAX_TREE_DEPTH:
        _fail("Git blob path exceeds the literal tree-depth bound")
    with shared_operation(root=root) as operation:
        current, _parents = _read_commit(
            operation, checked_commit, label="Git blob commit"
        )
        mode = "40000"
        for index, part in enumerate(parts):
            try:
                component = part.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ImmutableGitError(
                    "Git blob path component is not UTF-8"
                ) from error
            matches = [
                (entry_mode, object_id)
                for entry_mode, name, object_id in _read_tree_entries(
                    operation,
                    current,
                    label=(
                        f"Git tree for {checked_commit}:{'/'.join(parts[: index + 1])}"
                    ),
                )
                if name == component
            ]
            if len(matches) != 1:
                _fail(f"Git blob path is absent or ambiguous: {checked_path}")
            mode, current = matches[0]
            if index < len(parts) - 1 and mode != "40000":
                _fail(f"Git blob path traverses a non-tree component: {checked_path}")
        if mode not in {"100644", "100755"}:
            _fail("Git blob path must resolve to one regular file")
        raw = _read_object(
            operation,
            current,
            "blob",
            maximum=maximum,
            label=f"Git blob {checked_commit}:{checked_path}",
        )
        return GitBlobSnapshot(
            path=checked_path,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            raw=raw,
        )
