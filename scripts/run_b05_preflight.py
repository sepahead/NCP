#!/usr/bin/env python3
"""Run the complete local gate for one non-authorizing B05 source cut."""

from __future__ import annotations

import hashlib
import io
import json
import os
import pwd
import re
import selectors
import signal
import stat
import subprocess
import time
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
GIT = "/usr/bin/git"
BASH = "/bin/bash"
RUNNER_PATH = "scripts/run_b05_preflight.py"
COMMAND = "scripts/check.sh"
RECEIPT_COMMAND = "python3 -I scripts/run_b05_preflight.py"
SCHEMA = "ncp.prototype-full-preflight.v1"
TERMINAL = "NCP LOCAL PREFLIGHT PASSED — EXTERNAL RELEASE GATES REMAIN NOT RUN"
CLAIM_BOUNDARY = (
    "LOCAL_NON_AUTHORIZING_PROTOTYPE_ONLY_NO_IMPLEMENTATION_TASK_DEFECT_"
    "QUALIFICATION_GOVERNANCE_RELEASE_RUNTIME_SAFETY_OR_SCIENTIFIC_CREDIT"
)
TRANSFORM = "NCP_B05_PORTABLE_LINE_REDACTION_V1"
ENVIRONMENT_POLICY = "NCP_B05_MINIMAL_CHILD_ENV_V1"
EXECUTION_MODE = "BASH_C_IMMUTABLE_GIT_BLOB_V1"
BASH_SELECTOR = "SYSTEM_BIN_BASH"
GIT_SELECTOR = "SYSTEM_USR_BIN_GIT"
MAX_LITERAL_CHARS = 2_048
TIMEOUT_SECONDS = 3_600
MAX_RAW_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
MAX_LINES = 100_000
MAX_PORTABLE_BYTES = 16 * 1024 * 1024
MAX_SCRIPT_BYTES = 4 * 1024 * 1024
MAX_GATE_SCRIPT_BYTES = 64 * 1024
MAX_SYSTEM_TOOL_BYTES = 16 * 1024 * 1024
MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_INDEX_ENTRIES = 100_000
GIT_TIMEOUT_SECONDS = 30
GIT_MAX_BYTES = 1024 * 1024
TERMINATION_GRACE_SECONDS = 1
KILL_GRACE_SECONDS = 2
ARG_MAX_MARGIN = 64 * 1024
STATUS_COMMAND = (
    "git[fixed-config] status --porcelain=v1 -z "
    "--untracked-files=all --ignore-submodules=none"
)
STATUS_ARGUMENTS = (
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
    "--ignore-submodules=none",
)
INDEX_STAGE_COMMAND = "git[fixed-config] ls-files --stage -z"
INDEX_TREE_COMMAND = "git[fixed-config] ls-tree -rz --full-tree SOURCE_COMMIT"
INDEX_TAG_COMMANDS = (
    "git[fixed-config] ls-files -t -z",
    "git[fixed-config] ls-files -v -z",
    "git[fixed-config+fsmonitor-view] ls-files -f -z",
)
GIT_FIXED_ARGUMENTS = (
    "--no-replace-objects",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.untrackedCache=false",
    "-c",
    "core.ignoreStat=false",
    "-c",
    "core.fileMode=true",
    "-c",
    "core.sparseCheckout=false",
    "-c",
    "core.sparseCheckoutCone=false",
)
ENVIRONMENT_KEYS = frozenset(
    {
        "ALL_PROXY",
        "CARGO_HOME",
        "CARGO_NET_OFFLINE",
        "CURL_CA_BUNDLE",
        "DEVELOPER_DIR",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "MACOSX_DEPLOYMENT_TARGET",
        "NCP_ADVISORY_DB_PATH",
        "NODE_EXTRA_CA_CERTS",
        "NO_COLOR",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "RUSTUP_HOME",
        "RUSTUP_TOOLCHAIN",
        "SDKROOT",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)
ENVIRONMENT_PREFIXES = ("CARGO_HTTP_", "CARGO_NET_", "CARGO_REGISTRIES_", "LC_")
LOADER_VARIABLES = frozenset({"LIBPATH", "SHLIB_PATH"})
LOADER_PREFIXES = ("LD_", "DYLD_", "_RLD_")
REMOVED_PREFIXES = ("GIT_", "PYTHON", "BASH_FUNC_")
REMOVED_KEYS = frozenset(
    {
        "BASHOPTS",
        "BASH_ENV",
        "CDPATH",
        "ENV",
        "GLOBIGNORE",
        "IFS",
        "NODE_OPTIONS",
        "POSIXLY_CORRECT",
        "PROMPT_COMMAND",
        "PS4",
        "RUSTC_WORKSPACE_WRAPPER",
        "RUSTC_WRAPPER",
        "RUSTFLAGS",
        "SHELLOPTS",
    }
)
LINE_BREAK = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
INDEX_STAGE_RECORD = re.compile(
    rb"(?P<mode>[0-7]{6}) (?P<object>[0-9a-f]{40}|[0-9a-f]{64}) "
    rb"(?P<stage>[0-3])\t(?P<path>.+)",
    re.DOTALL,
)
INDEX_TREE_RECORD = re.compile(
    rb"(?P<mode>[0-7]{6}) (?P<kind>blob|commit) "
    rb"(?P<object>[0-9a-f]{40}|[0-9a-f]{64})\t(?P<path>.+)",
    re.DOTALL,
)


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def trusted_user_tool_directory(path: Path, home: Path) -> bool:
    try:
        relative = path.relative_to(home)
    except ValueError:
        return False
    parts = relative.parts
    if parts in {
        (".cargo", "bin"),
        (".bun", "bin"),
        (".local", "bin"),
        (".volta", "bin"),
        (".asdf", "shims"),
        (".pyenv", "shims"),
        (".local", "share", "mise", "shims"),
        ("Library", "pnpm"),
    }:
        return True
    return (
        len(parts) == 5
        and parts[:3] == (".nvm", "versions", "node")
        and parts[-1] == "bin"
    )


def sanitized_path(home: Path) -> str:
    raw_path = os.environ.get("PATH")
    if not raw_path:
        fail("PATH is required for the bounded local toolchain")
    retained: list[str] = []
    seen: set[str] = set()
    fixed_user_roots = (Path("/opt/homebrew"),)
    for raw_entry in raw_path.split(os.pathsep):
        candidate = Path(raw_entry)
        if not raw_entry or not candidate.is_absolute():
            fail("PATH contains an empty or relative component")
        try:
            resolved = candidate.resolve(strict=True)
            metadata = resolved.stat()
        except OSError:
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            continue
        trusted = (
            metadata.st_uid == 0 and not metadata.st_mode & 0o022
        ) or trusted_user_tool_directory(resolved, home)
        if not trusted:
            for fixed_root in fixed_user_roots:
                try:
                    resolved.relative_to(fixed_root)
                except ValueError:
                    continue
                trusted = metadata.st_uid in {0, os.geteuid()} and not (
                    metadata.st_mode & 0o002
                )
                break
        canonical = str(resolved)
        if trusted and canonical not in seen:
            retained.append(canonical)
            seen.add(canonical)
    if not retained:
        fail("PATH contains no trusted absolute tool directories")
    return os.pathsep.join(retained)


def clean_environment() -> tuple[dict[str, str], dict[str, object]]:
    if os.name != "posix":
        fail("bounded preflight execution requires a POSIX host")
    loader_keys = sorted(
        key
        for key in os.environ
        if key in LOADER_VARIABLES or key.startswith(LOADER_PREFIXES)
    )
    if loader_keys:
        fail("entry environment contains a dynamic-loader injection variable")
    try:
        account = pwd.getpwuid(os.geteuid())
        home = Path(account.pw_dir).resolve(strict=True)
    except (KeyError, OSError) as error:
        raise SystemExit(
            f"cannot resolve the current POSIX account: {error}"
        ) from error
    environment: dict[str, str] = {
        "HOME": str(home),
        "LOGNAME": account.pw_name,
        "PATH": sanitized_path(home),
        "USER": account.pw_name,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    removed = 0
    for key, value in os.environ.items():
        if key in REMOVED_KEYS or key.startswith(REMOVED_PREFIXES):
            removed += 1
            continue
        if key in environment:
            continue
        if key not in ENVIRONMENT_KEYS and not key.startswith(ENVIRONMENT_PREFIXES):
            continue
        if len(key.encode("utf-8")) > 128 or len(value.encode("utf-8")) > 8_192:
            fail("retained environment value exceeds its byte bound")
        environment[key] = value
    retained_keys = sorted(environment)
    receipt: dict[str, object] = {
        "policy": ENVIRONMENT_POLICY,
        "retained_keys": retained_keys,
        "removed_control_key_count": removed,
        "loader_variable_count": 0,
        "path_sha256": hashlib.sha256(environment["PATH"].encode()).hexdigest(),
        "bash_launcher": BASH_SELECTOR,
        "git_launcher": GIT_SELECTOR,
    }
    return environment, receipt


COMMAND_ENVIRONMENT, ENVIRONMENT_RECEIPT = clean_environment()


def group_exists(process: subprocess.Popen[bytes]) -> bool:
    process.poll()
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as error:
        if process.poll() is not None:
            return False
        raise SystemExit("cannot inspect the bounded command process group") from error
    return True


def signal_group(
    process: subprocess.Popen[bytes], signal_number: signal.Signals
) -> None:
    try:
        os.killpg(process.pid, signal_number)
    except ProcessLookupError:
        return
    except PermissionError as error:
        try:
            process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            raise SystemExit(
                "cannot signal the bounded command process group"
            ) from error
        if not group_exists(process):
            return
        raise SystemExit("cannot signal the surviving bounded command group") from error


def wait_for_group_exit(process: subprocess.Popen[bytes], timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while group_exists(process):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    signal_group(process, signal.SIGTERM)
    if not wait_for_group_exit(process, TERMINATION_GRACE_SECONDS):
        signal_group(process, signal.SIGKILL)
        if not wait_for_group_exit(process, KILL_GRACE_SECONDS):
            fail("bounded command process group survived SIGKILL")
    try:
        process.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait(timeout=KILL_GRACE_SECONDS)
        raise SystemExit("bounded command leader survived group termination") from error


def run_bounded(
    arguments: list[str], *, timeout_seconds: int, maximum: int
) -> tuple[int, bytes]:
    if os.name != "posix":
        fail("bounded preflight execution requires a POSIX host")
    process = subprocess.Popen(  # noqa: S603
        arguments,
        cwd=ROOT,
        env=COMMAND_ENVIRONMENT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if process.stdout is None:
        terminate_process_group(process)
        fail("bounded command lacks its output pipe")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    chunks: list[bytes] = []
    total = 0
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_process_group(process)
                fail("bounded command exceeded its timeout")
            events = selector.select(timeout=min(remaining, 0.25))
            for key, _ in events:
                chunk = os.read(key.fd, CHUNK_BYTES)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > maximum:
                    terminate_process_group(process)
                    fail("bounded command exceeded its output byte limit")
                chunks.append(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminate_process_group(process)
            fail("bounded command exceeded its timeout")
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            terminate_process_group(process)
            raise SystemExit("bounded command exceeded its timeout") from error
    finally:
        selector.close()
        process.stdout.close()
    return return_code, b"".join(chunks)


def git_bytes(*arguments: str, maximum: int = GIT_MAX_BYTES) -> bytes:
    return_code, output = run_bounded(
        [GIT, *GIT_FIXED_ARGUMENTS, *arguments],
        timeout_seconds=GIT_TIMEOUT_SECONDS,
        maximum=maximum,
    )
    if return_code != 0:
        fail(f"git command failed with exit code {return_code}")
    return output


def git_text(*arguments: str) -> str:
    try:
        return git_bytes(*arguments, maximum=4096).decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise SystemExit(f"git identity output is not ASCII: {error}") from error


def regular_file_bytes(path: Path, *, maximum: int, label: str) -> bytes:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        fail("bounded preflight execution requires O_NOFOLLOW")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise SystemExit(f"{label} cannot be opened safely: {error}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            fail(f"{label} is not a regular file")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(CHUNK_BYTES, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                fail(f"{label} exceeds its byte bound")
    except OSError as error:
        raise SystemExit(f"{label} cannot be read safely: {error}") from error
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if not raw:
        fail(f"{label} is empty")
    return raw


def worktree_file_bytes(relative: str, *, maximum: int = MAX_SCRIPT_BYTES) -> bytes:
    path = ROOT / relative
    return regular_file_bytes(path, maximum=maximum, label=f"checked {relative}")


def identity(relative: str, raw: bytes) -> dict[str, str | int]:
    return {
        "path": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def system_identity(selector: str, path: str) -> dict[str, str | int]:
    raw = regular_file_bytes(
        Path(path), maximum=MAX_SYSTEM_TOOL_BYTES, label=f"{selector} executable"
    )
    return {
        "selector": selector,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def split_nul_records(raw: bytes, label: str) -> list[bytes]:
    if not raw or not raw.endswith(b"\x00"):
        fail(f"{label} is empty or lacks NUL termination")
    records = raw[:-1].split(b"\x00")
    if (
        not records
        or len(records) > MAX_INDEX_ENTRIES
        or any(not item for item in records)
    ):
        fail(f"{label} has an invalid bounded record roster")
    return records


def parse_index_stage(raw: bytes) -> dict[bytes, tuple[bytes, bytes]]:
    result: dict[bytes, tuple[bytes, bytes]] = {}
    for record in split_nul_records(raw, "Git index stage roster"):
        match = INDEX_STAGE_RECORD.fullmatch(record)
        if match is None or match.group("stage") != b"0":
            fail("Git index contains a malformed, staged, or unmerged entry")
        path = match.group("path")
        if path in result:
            fail("Git index contains a duplicate path")
        result[path] = (match.group("mode"), match.group("object"))
    return result


def parse_head_tree(raw: bytes) -> dict[bytes, tuple[bytes, bytes]]:
    result: dict[bytes, tuple[bytes, bytes]] = {}
    for record in split_nul_records(raw, "Git source tree roster"):
        match = INDEX_TREE_RECORD.fullmatch(record)
        if match is None:
            fail("Git source tree contains a malformed recursive entry")
        mode = match.group("mode")
        kind = match.group("kind")
        if (mode == b"160000") != (kind == b"commit"):
            fail("Git source tree entry has an invalid mode and object-kind pair")
        path = match.group("path")
        if path in result:
            fail("Git source tree contains a duplicate path")
        result[path] = (mode, match.group("object"))
    return result


def parse_normal_tags(raw: bytes, expected_paths: set[bytes], label: str) -> None:
    observed: set[bytes] = set()
    for record in split_nul_records(raw, label):
        if len(record) < 3 or record[:2] != b"H ":
            fail(f"{label} contains a hidden or non-normal index flag")
        path = record[2:]
        if path in observed:
            fail(f"{label} contains a duplicate path")
        observed.add(path)
    if observed != expected_paths:
        fail(f"{label} differs from the exact index path roster")


def index_snapshot(source_commit: str) -> dict[str, str | int]:
    index_raw = git_bytes("ls-files", "--stage", "-z", maximum=MAX_INDEX_BYTES)
    tree_raw = git_bytes(
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        source_commit,
        maximum=MAX_INDEX_BYTES,
    )
    index = parse_index_stage(index_raw)
    tree = parse_head_tree(tree_raw)
    if index != tree:
        fail("Git index differs from the immutable source tree")
    paths = set(index)
    tag_raw_values = [
        git_bytes("ls-files", "-t", "-z", maximum=MAX_INDEX_BYTES),
        git_bytes("ls-files", "-v", "-z", maximum=MAX_INDEX_BYTES),
        git_bytes(
            "-c",
            "core.fsmonitor=true",
            "ls-files",
            "-f",
            "-z",
            maximum=MAX_INDEX_BYTES,
        ),
    ]
    for raw, label in zip(
        tag_raw_values,
        (
            "Git skip-worktree tag roster",
            "Git assume-unchanged tag roster",
            "Git fsmonitor-valid tag roster",
        ),
        strict=True,
    ):
        parse_normal_tags(raw, paths, label)
    tag_digest = hashlib.sha256(b"ncp.b05.index-tags.v1\x00")
    for raw in tag_raw_values:
        tag_digest.update(len(raw).to_bytes(8, "big"))
        tag_digest.update(raw)
    return {
        "entries": len(index),
        "head_roster_sha256": hashlib.sha256(tree_raw).hexdigest(),
        "index_roster_sha256": hashlib.sha256(index_raw).hexdigest(),
        "tag_roster_sha256": tag_digest.hexdigest(),
    }


def immutable_gate_text(raw: bytes) -> str:
    if len(raw) > MAX_GATE_SCRIPT_BYTES or b"\x00" in raw:
        fail("immutable preflight script exceeds its executable-text contract")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise SystemExit(f"immutable preflight script is not UTF-8: {error}") from error
    if text.encode("utf-8") != raw:
        fail("immutable preflight script is not round-trippable UTF-8")
    return text


def argv_environment_bytes(arguments: list[str], environment: dict[str, str]) -> int:
    return sum(len(argument.encode()) + 1 for argument in arguments) + sum(
        len(key.encode()) + len(value.encode()) + 2
        for key, value in environment.items()
    )


def iter_text_lines(text: str):
    start = 0
    for match in LINE_BREAK.finditer(text):
        yield text[start : match.start()]
        start = match.end()
    if start < len(text):
        yield text[start:]


def portable_log(raw: bytes) -> tuple[str, int, int, str | None]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise SystemExit(f"preflight output is not UTF-8: {error}") from error
    portable_buffer = io.StringIO()
    portable_bytes = 0
    terminal_count = 0
    last_nonempty_line: str | None = None
    line_count = 0
    for index, line in enumerate(iter_text_lines(text)):
        line_count += 1
        if line_count > MAX_LINES:
            fail("preflight output is empty or exceeds its line-count bound")
        if line.strip():
            last_nonempty_line = line
            terminal_count += line == TERMINAL
        if line == TERMINAL:
            portable_line = line
        elif (
            len(line) > MAX_LITERAL_CHARS
            or (line and not line.isprintable())
            or any(marker in line for marker in ("/", "\\", "%"))
        ):
            encoded = line.encode("utf-8")
            portable_line = (
                f"NCP B05 REDACTED LINE {index:06d} BYTES {len(encoded)} "
                f"SHA256 {hashlib.sha256(encoded).hexdigest()}"
            )
        else:
            portable_line = line
        encoded_portable_line = (portable_line + "\n").encode("utf-8")
        portable_bytes += len(encoded_portable_line)
        if portable_bytes > MAX_PORTABLE_BYTES:
            fail("portable preflight output exceeds its byte limit")
        portable_buffer.write(portable_line)
        portable_buffer.write("\n")
    if line_count == 0:
        fail("preflight output is empty or exceeds its line-count bound")
    return (
        portable_buffer.getvalue(),
        line_count,
        terminal_count,
        last_nonempty_line,
    )


def main() -> None:
    source_commit = git_text("rev-parse", "--verify", "HEAD")
    source_tree = git_text("rev-parse", "--verify", "HEAD^{tree}")
    git_root = git_text("rev-parse", "--show-toplevel")
    if Path(git_root).resolve() != ROOT:
        fail("Git resolved a different repository root")
    status_before = git_bytes(*STATUS_ARGUMENTS)
    if status_before:
        fail("preflight requires a clean tracked and untracked-nonignored worktree")
    index_before = index_snapshot(source_commit)

    immutable_runner = git_bytes(
        "show", f"{source_commit}:{RUNNER_PATH}", maximum=MAX_SCRIPT_BYTES
    )
    immutable_preflight = git_bytes(
        "show", f"{source_commit}:{COMMAND}", maximum=MAX_GATE_SCRIPT_BYTES
    )
    if worktree_file_bytes(RUNNER_PATH) != immutable_runner:
        fail("preflight runner differs from its immutable source blob")
    if (
        worktree_file_bytes(COMMAND, maximum=MAX_GATE_SCRIPT_BYTES)
        != immutable_preflight
    ):
        fail("preflight script differs from its immutable source blob")
    gate_text = immutable_gate_text(immutable_preflight)
    bash_identity = system_identity(BASH_SELECTOR, BASH)
    git_identity = system_identity(GIT_SELECTOR, GIT)
    gate_arguments = [
        BASH,
        "--noprofile",
        "--norc",
        "-c",
        gate_text,
        COMMAND,
    ]
    try:
        arg_max = int(os.sysconf("SC_ARG_MAX"))
    except (OSError, TypeError, ValueError) as error:
        raise SystemExit(f"cannot read SC_ARG_MAX: {error}") from error
    invocation_bytes = argv_environment_bytes(gate_arguments, COMMAND_ENVIRONMENT)
    if arg_max <= ARG_MAX_MARGIN or invocation_bytes > arg_max - ARG_MAX_MARGIN:
        fail("immutable preflight invocation exceeds its ARG_MAX safety bound")

    process_exit_code, raw = run_bounded(
        gate_arguments,
        timeout_seconds=TIMEOUT_SECONDS,
        maximum=MAX_RAW_BYTES,
    )

    source_commit_after = git_text("rev-parse", "--verify", "HEAD")
    source_tree_after = git_text("rev-parse", "--verify", "HEAD^{tree}")
    status_after = git_bytes(*STATUS_ARGUMENTS)
    index_after = index_snapshot(source_commit)
    immutable_runner_after = git_bytes(
        "show", f"{source_commit}:{RUNNER_PATH}", maximum=MAX_SCRIPT_BYTES
    )
    immutable_preflight_after = git_bytes(
        "show", f"{source_commit}:{COMMAND}", maximum=MAX_GATE_SCRIPT_BYTES
    )
    if source_commit_after != source_commit or source_tree_after != source_tree:
        fail("preflight changed the checked source identity")
    if status_after:
        fail("preflight left tracked or untracked-nonignored worktree changes")
    if (
        immutable_runner_after != immutable_runner
        or worktree_file_bytes(RUNNER_PATH) != immutable_runner
    ):
        fail("preflight runner changed during execution")
    if (
        immutable_preflight_after != immutable_preflight
        or worktree_file_bytes(COMMAND, maximum=MAX_GATE_SCRIPT_BYTES)
        != immutable_preflight
    ):
        fail("preflight script changed during execution")
    if index_after != index_before:
        fail("preflight changed the checked Git index roster")
    if not raw:
        fail("preflight output is empty")

    portable_text, raw_line_count, terminal_count, last_nonempty_line = portable_log(
        raw
    )
    portable_raw = portable_text.encode("utf-8")
    passed = (
        process_exit_code == 0
        and last_nonempty_line == TERMINAL
        and terminal_count == 1
    )
    result = {
        "schema": SCHEMA,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "command": RECEIPT_COMMAND,
        "invoked_command": COMMAND,
        "process_exit_code": process_exit_code,
        "runner_script": identity(RUNNER_PATH, immutable_runner),
        "preflight_script": identity(COMMAND, immutable_preflight),
        "execution": {
            "mode": EXECUTION_MODE,
            "pathname_reopened": False,
            "argv_environment_bytes": invocation_bytes,
            "arg_max": arg_max,
            "arg_max_margin": ARG_MAX_MARGIN,
            "bash": bash_identity,
            "git": git_identity,
        },
        "environment": ENVIRONMENT_RECEIPT,
        "index": {
            "stage_command": INDEX_STAGE_COMMAND,
            "tree_command": INDEX_TREE_COMMAND,
            "tag_commands": INDEX_TAG_COMMANDS,
            "entries": index_before["entries"],
            "head_roster_sha256": index_before["head_roster_sha256"],
            "index_roster_sha256_before": index_before["index_roster_sha256"],
            "index_roster_sha256_after": index_after["index_roster_sha256"],
            "tag_roster_sha256_before": index_before["tag_roster_sha256"],
            "tag_roster_sha256_after": index_after["tag_roster_sha256"],
            "matches_head_before": True,
            "matches_head_after": True,
            "staged_or_unmerged_count": 0,
            "skip_or_sparse_count": 0,
            "assume_unchanged_count": 0,
            "fsmonitor_valid_count": 0,
            "nonignored_untracked_count": 0,
        },
        "worktree": {
            "status_command": STATUS_COMMAND,
            "clean_before": True,
            "clean_after": True,
            "head_unchanged": True,
            "tree_unchanged": True,
            "runner_unchanged": True,
            "script_unchanged": True,
        },
        "execution_bounds": {
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_raw_bytes": MAX_RAW_BYTES,
            "chunk_bytes": CHUNK_BYTES,
            "max_lines": MAX_LINES,
            "max_portable_bytes": MAX_PORTABLE_BYTES,
            "max_gate_script_bytes": MAX_GATE_SCRIPT_BYTES,
            "termination_grace_seconds": TERMINATION_GRACE_SECONDS,
            "kill_grace_seconds": KILL_GRACE_SECONDS,
        },
        "log": {
            "sha256": hashlib.sha256(portable_raw).hexdigest(),
            "bytes": len(portable_raw),
            "text": portable_text,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_bytes": len(raw),
            "raw_line_count": raw_line_count,
            "transform": TRANSFORM,
        },
        "counts": {
            "passed": 1 if passed else 0,
            "failed": 0 if passed else 1,
            "skipped": 0,
        },
        "terminal": TERMINAL,
        "terminal_count": terminal_count,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if passed else process_exit_code or 1)


if __name__ == "__main__":
    main()
