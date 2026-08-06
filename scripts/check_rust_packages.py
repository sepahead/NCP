#!/usr/bin/env -S python3 -I
"""Build and exercise the candidate Rust crate archives.

All five packageable workspace crates are packaged and inspected. The three
crates with package-sensitive test fixtures are tested from their extracted
archives; the Python binding is type-checked and the gateway is type-checked plus
executed for its exact identity receipt. Temporary Cargo patches point exact
unpublished NCP dependencies at the corresponding extracted archives, leaving the
normalized/published manifests untouched.

The normalized ``ncp-zenoh`` and ``ncp-gateway`` archives cannot propagate the
workspace root's Zenoh transport patch. Their generated locks therefore select
the vulnerable published ``lz4_flex 0.10.0`` graph. This checker first resolves
and records that fallback without compiling it, then supplies the exact immutable
transport backport at the consuming test root, regenerates and verifies the
conditioned lock and metadata, and only then compiles offline. That is conditional
package-consumption evidence, not self-contained distribution or release
authorization.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator

import tomllib

ROOT = Path(__file__).resolve().parents[1]
CRATES = ("ncp-core", "ncp-zenoh", "ncp-cpp", "ncp-python", "ncp-gateway")
ARCHIVE_IDENTITY_CONTROLS = {
    "ncp-core": {
        "Cargo.toml",
        "Cargo.toml.orig",
        "src/contract_identity.rs",
        "src/lib.rs",
    },
    "ncp-zenoh": {"Cargo.lock", "Cargo.toml", "Cargo.toml.orig", "src/lib.rs"},
    "ncp-cpp": {"Cargo.toml", "Cargo.toml.orig", "include/ncp.h", "src/lib.rs"},
    "ncp-python": {"Cargo.toml", "Cargo.toml.orig", "pyproject.toml", "src/lib.rs"},
    "ncp-gateway": {"Cargo.lock", "Cargo.toml", "Cargo.toml.orig", "src/main.rs"},
}
TEST_CRATES = ("ncp-core", "ncp-zenoh", "ncp-cpp")
CHECK_CRATES = ("ncp-python", "ncp-gateway")
LOCAL_DEPENDENCIES = {
    "ncp-core": (),
    "ncp-zenoh": ("ncp-core",),
    "ncp-cpp": ("ncp-core",),
    "ncp-python": ("ncp-core",),
    "ncp-gateway": ("ncp-core", "ncp-zenoh"),
}
SOURCE_REVISION = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
TARGET_TRIPLE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
ZENOH_CONDITIONAL_CRATES = ("ncp-zenoh", "ncp-gateway")
CRATES_IO_SOURCE = "registry+https://github.com/rust-lang/crates.io-index"
ZENOH_TRANSPORT_VERSION = "1.9.0"
ZENOH_TRANSPORT_REGISTRY_CHECKSUM = (
    "80800c4adc26dbe81418735068541cf39820a95ec988114f04dd014775ba7c97"
)
VULNERABLE_LZ4_VERSION = "0.10.0"
VULNERABLE_LZ4_CHECKSUM = (
    "8b8c72594ac26bfd34f2d99dfced2edfaddfe8a476e3ff2ca0eb293d925c4f83"
)
FALLBACK_TWOX_VERSION = "1.6.3"
FALLBACK_TWOX_CHECKSUM = (
    "97fee6b57c6a41524a810daee9286c02d7752c4253064d0b05472833a438f675"
)
ZENOH_BACKPORT_GIT = "https://github.com/sepahead/zenoh-transport-lz4-backport"
ZENOH_BACKPORT_REVISION = "9045545b72a77602a87f40203cb614b48157b4bc"
ZENOH_BACKPORT_SOURCE = (
    f"git+{ZENOH_BACKPORT_GIT}?rev={ZENOH_BACKPORT_REVISION}#{ZENOH_BACKPORT_REVISION}"
)
FIXED_LZ4_VERSION = "0.11.6"
FIXED_LZ4_CHECKSUM = "373f5eceeeab7925e0c1098212f2fbc4d416adec9d35051a6ab251e824c1854a"
CONDITIONED_TWOX_VERSION = "2.1.3"
CONDITIONED_TWOX_CHECKSUM = (
    "8464ec13c3691491391d9fce00f6416c9a48e46972f72d7865688be2080192c9"
)
ZENOH_BACKPORT_CONFIG = {
    "patch.crates-io.zenoh-transport.git": ZENOH_BACKPORT_GIT,
    "patch.crates-io.zenoh-transport.rev": ZENOH_BACKPORT_REVISION,
}
RUST_PACKAGE_RECEIPT_SCHEMA = "ncp.rust-package-receipt.v3"
RUST_RECEIPT_VERIFICATION_BOUNDARY = {
    "artifact_derived": [
        "EXACT_RETAINED_TREE_AND_FILE_HASHES",
        "CRATE_MEMBER_MANIFESTS_PACKAGE_IDENTITIES_AND_EMBEDDED_BUILD_IDENTITY",
        "ARCHIVE_FALLBACK_AND_EXACT_CONDITIONED_LOCK_DELTAS",
        "REGISTRY_CRATE_SOURCE_MANIFESTS",
    ],
    "local_process_attestations": [
        "REPRODUCIBILITY_COMPARISON",
        "QUALIFICATION_ENVIRONMENT_AND_TOOLCHAIN_POINT_OBSERVATIONS",
        "RESOLUTION_PROJECTIONS_AND_COMPILE_STEP_RESULTS",
        "POINT_IN_TIME_PRE_POST_SOURCE_COMPARISONS",
        "POINT_IN_TIME_PINNED_FORK_SOURCE_AND_UPSTREAM_DELTA_VERIFICATION",
    ],
    "pinned_fork_source_bytes": "NOT_RETAINED",
    "source_revision_binding": "CALLER_ATTESTED_REQUIRES_ENCLOSING_DOSSIER",
    "command_transcript": "NOT_RETAINED",
    "independent_reexecution": False,
    "release_authorized": False,
}
REVIEWED_SOURCE_SCHEMA = "ncp.reviewed-git-source.v1"
ZENOH_BACKPORT_TREE = "cce05e8b1b99424475cd32ec679ef7a218f13e26"
ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256 = (
    "739857b74061bc7cca79e662565a97e9a2b325e87afe1c502c2bb112a4c9217b"
)
ZENOH_BACKPORT_CONTROL = (
    ROOT / "security" / "backports" / "zenoh-transport-lz4-backport.v1.json"
)
ZENOH_BACKPORT_CONTROL_SHA256 = (
    "03dd10e87f291f5de6cedf5cc290390fd68194055595f352bcaf2702765df761"
)
ZENOH_UPSTREAM_TRACKED_MANIFEST_SHA256 = (
    "9256cd203e9fca44871e9001b2949d4b875dbbadb2bf5196e68936fa4295caed"
)
RETAINED_CONDITIONED_LOCKS = {
    "ncp-zenoh": "qualification/ncp-zenoh.conditioned.Cargo.lock",
    "ncp-gateway": "qualification/ncp-gateway.conditioned.Cargo.lock",
}
RETAINED_LZ4_CRATE = "qualification/lz4_flex-0.11.6.crate"
RETAINED_TWOX_CRATE = "qualification/twox-hash-2.1.3.crate"
RETAINED_UPSTREAM_TRANSPORT_CRATE = "qualification/zenoh-transport-1.9.0.crate"
REGISTRY_CARGO_OK = b'{"v":1}'
MAX_CRATE_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_CRATE_MEMBERS = 10_000
MAX_CRATE_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_CRATE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_CRATE_TAR_BYTES = 320 * 1024 * 1024
MAX_CRATE_TAR_METADATA_ENTRY_BYTES = 64 * 1024
MAX_CRATE_TAR_METADATA_BYTES = 1024 * 1024
CRATE_STREAM_CHUNK_BYTES = 64 * 1024
TAR_RECORD_BYTES = 512
TAR_END_RECORDS = 2
TAR_TERMINATOR_BYTES = TAR_RECORD_BYTES * TAR_END_RECORDS
MAX_RETAINED_CONTROL_BYTES = 8 * 1024 * 1024
MAX_JSON_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_TOML_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_SOURCE_FILES = 10_000
MAX_SOURCE_FILE_BYTES = 64 * 1024 * 1024
SECURE_CARGO_CONFIG = (
    "net.git-fetch-with-cli=false",
    "net.retry=3",
    "http.timeout=120",
    "http.low-speed-limit=1",
)


@dataclass(frozen=True)
class Qualification:
    """One isolated, config-free Cargo qualification boundary."""

    env: dict[str, str]
    cargo: str
    rustc: str
    rustdoc: str
    git: str
    python: str
    cargo_home: Path
    work: Path
    toolchain_receipt: dict[str, object]


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        stdin=subprocess.DEVNULL,
    )


def run_capture(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> bytes:
    print("+", " ".join(command), flush=True)
    process = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
    )
    return process.stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _resolved_tool(name: str, environment: dict[str, str]) -> str:
    candidate = shutil.which(name, path=environment.get("PATH"))
    if candidate is None:
        raise RuntimeError(f"required qualification tool is unavailable: {name}")
    path = Path(candidate)
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as error:
        raise RuntimeError(
            f"cannot resolve qualification tool {name}: {error}"
        ) from error
    if not stat.S_ISREG(mode):
        raise RuntimeError(f"qualification tool is not a regular file: {name}")
    return str(path.absolute())


def _private_empty_directory(path: Path) -> None:
    """Create one new 0700 directory, rejecting aliases and occupied paths."""

    try:
        path.mkdir(mode=0o700)
    except FileExistsError as error:
        raise RuntimeError(
            f"qualification directory already exists: {path.name}"
        ) from error
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise RuntimeError(f"qualification path is not a plain directory: {path.name}")
    path.chmod(0o700)
    if any(path.iterdir()):
        raise RuntimeError(f"qualification directory is not empty: {path.name}")


def assert_no_cargo_config_ancestors(path: Path) -> None:
    """Reject hierarchical Cargo configuration above the qualification cwd."""

    resolved = path.resolve(strict=True)
    for parent in (resolved, *resolved.parents):
        for relative in (Path(".cargo/config"), Path(".cargo/config.toml")):
            candidate = parent / relative
            try:
                mode = candidate.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode) or stat.S_ISREG(mode) or stat.S_ISDIR(mode):
                raise RuntimeError(
                    f"qualification cwd inherits Cargo configuration: {candidate}"
                )
            raise RuntimeError(
                f"qualification cwd inherits special Cargo configuration: {candidate}"
            )


def _tool_output_exact(
    command: list[str], environment: dict[str, str], *, maximum: int = 65_536
) -> str:
    try:
        process = subprocess.run(
            command,
            env=environment,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise RuntimeError(f"cannot execute {command[0]}: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"{' '.join(command)} failed: {detail}")
    if len(process.stdout) > maximum:
        raise RuntimeError(f"{' '.join(command)} output exceeds its bound")
    try:
        return process.stdout.decode("utf-8", "strict").strip()
    except UnicodeError as error:
        raise RuntimeError(f"{' '.join(command)} output is not UTF-8") from error


def _rust_tool_binary_sha256(
    name: str, invocation: str, environment: dict[str, str]
) -> str:
    """Hash the selected Cargo/rustc binary behind an optional rustup shim."""

    invocation_resolved = Path(invocation).resolve(strict=True)
    rustup = (
        str(invocation_resolved)
        if invocation_resolved.name == "rustup"
        else shutil.which("rustup", path=environment.get("PATH"))
    )
    if rustup is None or Path(rustup).resolve(strict=True) != invocation_resolved:
        return sha256(invocation_resolved)
    selected = Path(_tool_output_exact([rustup, "which", name], environment))
    if not selected.is_absolute():
        raise RuntimeError(f"rustup returned a relative {name} path")
    try:
        selected = selected.resolve(strict=True)
        mode = selected.stat().st_mode
    except OSError as error:
        raise RuntimeError(f"cannot resolve rustup-selected {name}: {error}") from error
    if not stat.S_ISREG(mode):
        raise RuntimeError(f"rustup-selected {name} is not a regular file")
    rustup_home = environment.get("RUSTUP_HOME")
    if rustup_home is None:
        raise RuntimeError("rustup selection has no explicit RUSTUP_HOME")
    try:
        selected.relative_to(Path(rustup_home).resolve(strict=True))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"rustup-selected {name} escaped RUSTUP_HOME") from error
    return sha256(selected)


def _capture_toolchain_identity(
    *,
    cargo: str,
    rustc: str,
    rustdoc: str,
    git: str,
    python: str,
    environment: dict[str, str],
) -> dict[str, str]:
    return {
        "cargo_version": _tool_output_exact(
            [cargo, "--version", "--verbose"], environment
        ),
        "cargo_invocation_sha256": sha256(Path(cargo).resolve(strict=True)),
        "cargo_binary_sha256": _rust_tool_binary_sha256("cargo", cargo, environment),
        "rustc_verbose": _tool_output_exact([rustc, "-vV"], environment),
        "rustc_invocation_sha256": sha256(Path(rustc).resolve(strict=True)),
        "rustc_binary_sha256": _rust_tool_binary_sha256("rustc", rustc, environment),
        "rustdoc_version": _tool_output_exact(
            [rustdoc, "--version", "--verbose"], environment
        ),
        "rustdoc_invocation_sha256": sha256(Path(rustdoc).resolve(strict=True)),
        "rustdoc_binary_sha256": _rust_tool_binary_sha256(
            "rustdoc", rustdoc, environment
        ),
        "git_version": _tool_output_exact([git, "--version"], environment),
        "git_binary_sha256": sha256(Path(git).resolve(strict=True)),
        "python_version": _tool_output_exact([python, "--version"], environment),
        "python_binary_sha256": sha256(Path(python).resolve(strict=True)),
    }


def verify_toolchain_point_match(qualification: Qualification) -> None:
    """Require the selected tool identities to match at the final observation."""

    observed = _capture_toolchain_identity(
        cargo=qualification.cargo,
        rustc=qualification.rustc,
        rustdoc=qualification.rustdoc,
        git=qualification.git,
        python=qualification.python,
        environment=qualification.env,
    )
    if observed != qualification.toolchain_receipt.get("toolchain"):
        raise RuntimeError("qualification tool identity changed during execution")
    qualification.toolchain_receipt["toolchain_pre_post_point_match"] = True


def create_qualification(
    root: Path,
    inherited: dict[str, str],
    *,
    expected_identity: str,
) -> Qualification:
    """Create a credential-free Cargo home and a minimal, bound environment."""

    cargo = _resolved_tool("cargo", inherited)
    rustc = _resolved_tool("rustc", inherited)
    rustdoc = _resolved_tool("rustdoc", inherited)
    git = _resolved_tool("git", inherited)
    python_path = Path(sys.executable)
    try:
        python_resolved = python_path.resolve(strict=True)
        python_mode = python_resolved.stat().st_mode
    except OSError as error:
        raise RuntimeError(f"cannot resolve qualification Python: {error}") from error
    if not python_path.is_absolute() or not stat.S_ISREG(python_mode):
        raise RuntimeError("qualification Python is not an absolute regular file")
    python = str(python_path)
    home = root / "qualification-home"
    cargo_home = root / "qualification-cargo-home"
    target = root / "qualification-target"
    work = root / "qualification-work"
    temporary = root / "qualification-tmp"
    for path in (home, cargo_home, target, work, temporary):
        _private_empty_directory(path)
    assert_no_cargo_config_ancestors(work)

    system_tool_directories = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
    safe_path = os.pathsep.join(
        item for item in system_tool_directories if Path(item).is_dir()
    )
    environment = {
        "PATH": safe_path,
        "HOME": str(home),
        "CARGO_HOME": str(cargo_home),
        "CARGO_TARGET_DIR": str(target),
        "CARGO_INCREMENTAL": "0",
        "CARGO_TERM_COLOR": "never",
        "RUSTC": rustc,
        "RUSTDOC": rustdoc,
        "PYO3_PYTHON": python,
        "TMPDIR": str(temporary),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "GCM_INTERACTIVE": "never",
        "GIT_ALLOW_PROTOCOL": "https",
        "NCP_EXPECTED_BUILD_IDENTITY": expected_identity,
    }
    old_home = Path(inherited.get("HOME", str(Path.home())))
    rustup_home = inherited.get("RUSTUP_HOME", str(old_home / ".rustup"))
    if Path(rustup_home).is_absolute() and Path(rustup_home).is_dir():
        environment["RUSTUP_HOME"] = rustup_home
    source_date_epoch = inherited.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is not None:
        if re.fullmatch(r"[0-9]{1,20}", source_date_epoch) is None:
            raise RuntimeError("SOURCE_DATE_EPOCH is malformed")
        environment["SOURCE_DATE_EPOCH"] = source_date_epoch

    retained_environment: dict[str, str] = {}
    path_markers = {
        "PATH": "SYSTEM_TOOL_DIRECTORIES_ONLY",
        "HOME": "FRESH_PRIVATE_EMPTY",
        "CARGO_HOME": "FRESH_PRIVATE_EMPTY",
        "CARGO_TARGET_DIR": "FRESH_PRIVATE_EMPTY",
        "RUSTC": "REVIEWED_INVOCATION",
        "RUSTDOC": "REVIEWED_INVOCATION",
        "PYO3_PYTHON": "REVIEWED_PYTHON_INVOCATION",
        "TMPDIR": "FRESH_PRIVATE_EMPTY",
        "RUSTUP_HOME": "EXISTING_TOOLCHAIN_ONLY",
        "GIT_CONFIG_GLOBAL": "DISABLED_NULL_DEVICE",
        "GIT_CONFIG_SYSTEM": "DISABLED_NULL_DEVICE",
        "GIT_ASKPASS": "NONINTERACTIVE_FALSE_PROGRAM",
    }
    for key, value in sorted(environment.items()):
        retained_environment[key] = path_markers.get(key, value)

    toolchain = _capture_toolchain_identity(
        cargo=cargo,
        rustc=rustc,
        rustdoc=rustdoc,
        git=git,
        python=python,
        environment=environment,
    )
    receipt: dict[str, object] = {
        "policy": "FRESH_HOME_CACHE_AND_CALLER_ENV_STRIPPED",
        "fresh_home": True,
        "fresh_cargo_home": True,
        "fresh_target_dir": True,
        "fresh_work_dir": True,
        "fresh_tmp_dir": True,
        "inherited_source_cache": False,
        "network_phase": "PACKAGE_RESOLUTION_AND_EXACT_PATCH_LOCKED_FETCH",
        "compile_phase": "CARGO_DEPENDENCY_ACCESS_OFFLINE_DURING_COMPILE_TEST",
        "host_network_isolation": "NOT_CLAIMED",
        "child_process_network_isolation": "NOT_CLAIMED",
        "host_filesystem_isolation": "NOT_CLAIMED",
        "system_executable_isolation": "NOT_CLAIMED",
        "credential_access_isolation": "NOT_CLAIMED",
        "caller_credential_environment": "STRIPPED_FOR_CARGO_AND_GIT",
        "cargo_config": list(SECURE_CARGO_CONFIG),
        "environment": retained_environment,
        "environment_allowlist": sorted(
            key
            for key in environment
            if key
            not in {
                "HOME",
                "CARGO_HOME",
                "CARGO_TARGET_DIR",
                "TMPDIR",
                "RUSTC",
                "RUSTDOC",
                "PYO3_PYTHON",
                "RUSTUP_HOME",
            }
        ),
        "stripped_injection_classes": [
            "CARGO_CONFIG_AND_ALIAS",
            "CARGO_CREDENTIAL_AND_REGISTRY",
            "CARGO_ENCODED_RUSTFLAGS",
            "CALLER_COMPILER_AND_LINKER_ENV",
            "GIT_CONFIG_CREDENTIAL_PROXY_AND_REPLACE",
            "RUSTC_AND_RUSTDOC_FLAGS",
            "RUSTC_WRAPPERS",
        ],
        "toolchain": toolchain,
        "toolchain_pre_post_point_match": False,
    }
    return Qualification(
        env=environment,
        cargo=cargo,
        rustc=rustc,
        rustdoc=rustdoc,
        git=git,
        python=python,
        cargo_home=cargo_home,
        work=work,
        toolchain_receipt=receipt,
    )


def cargo_security_args() -> list[str]:
    args: list[str] = []
    for value in SECURE_CARGO_CONFIG:
        args.extend(("--config", value))
    return args


def cargo_command(qualification: Qualification, *arguments: str) -> list[str]:
    """Build one Cargo invocation with the reviewed executable and config."""

    return [qualification.cargo, *cargo_security_args(), *arguments]


def fetch_locked_archive(
    manifest_path: Path,
    patch_args: list[str],
    *,
    target: str,
    qualification: Qualification,
) -> None:
    """Fetch one exact archive graph before offline metadata or compilation."""

    run(
        cargo_command(
            qualification,
            "fetch",
            "--manifest-path",
            str(manifest_path),
            "--locked",
            "--target",
            target,
            *patch_args,
        ),
        env=qualification.env,
        cwd=qualification.work,
    )


def parse_rustc_host(output: bytes) -> str:
    if len(output) > 65_536:
        raise RuntimeError("rustc version output exceeds its bound")
    try:
        text = output.decode("utf-8", "strict")
    except UnicodeError as error:
        raise RuntimeError("rustc version output is not UTF-8") from error
    hosts = [
        line.removeprefix("host: ")
        for line in text.splitlines()
        if line.startswith("host: ")
    ]
    if len(hosts) != 1 or TARGET_TRIPLE.fullmatch(hosts[0]) is None:
        raise RuntimeError("rustc version output has no exact host target")
    return hosts[0]


def rustc_host(env: dict[str, str], rustc: str = "rustc") -> str:
    try:
        process = subprocess.run(
            [rustc, "-vV"],
            env=env,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise RuntimeError(f"cannot execute rustc: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"rustc -vV failed: {detail}")
    return parse_rustc_host(process.stdout)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError(f"cannot hash {path}: {error}") from error
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise RuntimeError(f"cannot hash non-regular file: {path}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def copy_regular_tree(source: Path, destination: Path) -> None:
    """Copy one plain tree without following links or accepting special files."""

    destination.mkdir()
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        relative = root_path.relative_to(source)
        output_root = destination / relative
        output_root.mkdir(exist_ok=True)
        directories.sort()
        files.sort()
        for name in directories:
            path = root_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise RuntimeError(
                    f"package source contains a linked/special directory: {path}"
                )
            (output_root / name).mkdir(exist_ok=True)
        for name in files:
            path = root_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise RuntimeError(
                    f"package source contains a link or special file: {path}"
                )
            shutil.copyfile(path, output_root / name)


def inject_packaged_source_identity(source: Path, revision: str) -> None:
    """Replace the generated non-certifying sentinel in a staged package tree."""

    identity = source / "ncp-core" / "src" / "contract_identity.rs"
    text = identity.read_text(encoding="utf-8")
    sentinel = '    None => "unreleased-worktree",'
    replacement = f'    None => "{revision}",'
    if text.count(sentinel) != 1 or revision in text:
        raise RuntimeError(
            "generated Rust build-identity sentinel is missing, duplicated, or pre-injected"
        )
    identity.write_text(text.replace(sentinel, replacement), encoding="utf-8")


def tree_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    records: dict[str, tuple[int, int, str]] = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = directory_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise RuntimeError(
                    f"package source contains a link or special entry: {path}"
                )
        for name in files:
            path = directory_path / name
            if path.stat().st_nlink != 1:
                raise RuntimeError(f"package source contains a hardlinked file: {path}")
            records[path.relative_to(root).as_posix()] = (
                path.lstat().st_mode & 0o777,
                path.stat().st_size,
                sha256(path),
            )
    return records


def cargo_patch_args(
    dependencies: tuple[str, ...], paths: dict[str, Path]
) -> list[str]:
    args: list[str] = []
    for dependency in dependencies:
        try:
            path = paths[dependency].resolve(strict=True)
        except (KeyError, OSError, RuntimeError) as error:
            raise RuntimeError(
                f"cannot resolve local Cargo patch path for {dependency}"
            ) from error
        if not path.is_dir():
            raise RuntimeError(f"local Cargo patch path is not a directory: {path}")
        # JSON string syntax is valid Cargo config TOML and handles spaces safely.
        # Resolve filesystem aliases before Cargo compares the patch source with
        # its canonical package identity (notably /var versus /private/var on macOS).
        value = f"patch.crates-io.{dependency}.path={json.dumps(str(path))}"
        args.extend(("--config", value))
    return args


def zenoh_backport_patch_args() -> list[str]:
    """Return and validate the exact consuming-root security patch arguments."""

    args: list[str] = []
    for key, value in ZENOH_BACKPORT_CONFIG.items():
        args.extend(("--config", f"{key}={json.dumps(value)}"))
    validate_zenoh_backport_patch_args(args)
    return args


def validate_zenoh_backport_patch_args(args: list[str]) -> None:
    if len(args) != 2 * len(ZENOH_BACKPORT_CONFIG):
        raise RuntimeError("Zenoh backport Cargo patch is absent or incomplete")
    decoded: dict[str, str] = {}
    for index in range(0, len(args), 2):
        if args[index] != "--config" or "=" not in args[index + 1]:
            raise RuntimeError("Zenoh backport Cargo patch argument is malformed")
        key, encoded = args[index + 1].split("=", 1)
        if key in decoded:
            raise RuntimeError("Zenoh backport Cargo patch repeats a key")
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Zenoh backport Cargo patch value is not TOML JSON"
            ) from error
        if not isinstance(value, str):
            raise RuntimeError("Zenoh backport Cargo patch value is not a string")
        decoded[key] = value
    if decoded != ZENOH_BACKPORT_CONFIG:
        raise RuntimeError("Zenoh backport Cargo patch identity drifted")


def one_lock_package(
    lock: dict[str, object], name: str, version: str
) -> dict[str, object]:
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise RuntimeError("Cargo.lock package array is malformed")
    matches = [
        package
        for package in packages
        if isinstance(package, dict)
        and package.get("name") == name
        and package.get("version") == version
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Cargo.lock does not contain one exact {name} {version} package"
        )
    return matches[0]


def load_toml(path: Path) -> dict[str, object]:
    try:
        raw = _bounded_regular_bytes(
            path, maximum=MAX_TOML_DOCUMENT_BYTES, context="TOML document"
        )
        value = tomllib.loads(raw.decode("utf-8", "strict"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} is not a TOML table")
    return value


def load_toml_bytes(value: bytes, context: str) -> dict[str, object]:
    if len(value) > MAX_TOML_DOCUMENT_BYTES:
        raise RuntimeError(f"cannot load {context}: document exceeds its size bound")
    try:
        decoded = value.decode("utf-8", "strict")
        parsed = tomllib.loads(decoded)
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"cannot load {context}: {error}") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{context} is not a TOML table")
    return parsed


def _bounded_regular_bytes(path: Path, *, maximum: int, context: str) -> bytes:
    """Read one bounded plain file without following a final symlink."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError(f"cannot open {context} {path}: {error}") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size < 0
            or before.st_size > maximum
        ):
            raise RuntimeError(f"{context} is linked, special, or oversized: {path}")
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > maximum:
                raise RuntimeError(f"{context} exceeds its size bound: {path}")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ) or observed != before.st_size:
            raise RuntimeError(f"{context} changed while it was read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def strict_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError(f"{path} contains duplicate JSON key {key!r}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise RuntimeError(f"{path} contains non-finite JSON constant {value}")

    try:
        raw = _bounded_regular_bytes(
            path, maximum=MAX_JSON_DOCUMENT_BYTES, context="JSON document"
        ).decode("utf-8", "strict")
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} is not a JSON object")
    return value


def assert_no_local_absolute_paths(value: object, *, context: str) -> None:
    if isinstance(value, str):
        if (
            Path(value).is_absolute()
            or value.startswith("\\")
            or value.casefold().startswith("file:")
            or re.match(r"^[A-Za-z]:[\\/]", value)
        ):
            raise RuntimeError(f"{context} contains a local absolute path")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert_no_local_absolute_paths(key, context=context)
            assert_no_local_absolute_paths(item, context=context)
        return
    if isinstance(value, list):
        for item in value:
            assert_no_local_absolute_paths(item, context=context)


def _safe_manifest_path(value: object, *, context: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 512
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RuntimeError(f"{context} contains an unsafe path")
    path = Path(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise RuntimeError(f"{context} contains a non-canonical path")
    if path.as_posix() != value:
        raise RuntimeError(f"{context} contains a non-portable path")
    return value


def reviewed_backport_source() -> dict[str, Any]:
    if sha256(ZENOH_BACKPORT_CONTROL) != ZENOH_BACKPORT_CONTROL_SHA256:
        raise RuntimeError("reviewed Zenoh backport control bytes drifted")
    control = strict_json(ZENOH_BACKPORT_CONTROL)
    if set(control) != {
        "schema",
        "repository",
        "revision",
        "tree",
        "tracked_file_manifest_sha256",
        "tracked_files",
        "upstream_crate",
    }:
        raise RuntimeError("reviewed Zenoh backport source control shape drifted")
    if (
        control.get("schema") != REVIEWED_SOURCE_SCHEMA
        or control.get("repository") != ZENOH_BACKPORT_GIT
        or control.get("revision") != ZENOH_BACKPORT_REVISION
        or control.get("tree") != ZENOH_BACKPORT_TREE
        or control.get("tracked_file_manifest_sha256")
        != ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256
    ):
        raise RuntimeError("reviewed Zenoh backport source identity drifted")
    files = control.get("tracked_files")
    if not isinstance(files, list) or not files or len(files) > MAX_SOURCE_FILES:
        raise RuntimeError("reviewed Zenoh backport file manifest is malformed")
    paths: list[str] = []
    for record in files:
        if not isinstance(record, dict) or set(record) != {
            "path",
            "git_mode",
            "size_bytes",
            "sha256",
        }:
            raise RuntimeError("reviewed Zenoh backport file record is malformed")
        path = _safe_manifest_path(record.get("path"), context="reviewed source")
        if record.get("git_mode") not in {"100644", "100755"}:
            raise RuntimeError("reviewed Zenoh backport file mode is malformed")
        size = record.get("size_bytes")
        digest = record.get("sha256")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_SOURCE_FILE_BYTES
            or not isinstance(digest, str)
            or HEX_SHA256.fullmatch(digest) is None
        ):
            raise RuntimeError("reviewed Zenoh backport file identity is malformed")
        paths.append(path)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise RuntimeError("reviewed Zenoh backport file paths are not exact")
    if canonical_json_sha256(files) != ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256:
        raise RuntimeError("reviewed Zenoh backport file manifest digest drifted")

    upstream = control.get("upstream_crate")
    if not isinstance(upstream, dict) or set(upstream) != {
        "package",
        "version",
        "source",
        "sha256",
        "tracked_file_manifest_sha256",
        "allowed_delta",
    }:
        raise RuntimeError("reviewed upstream crate control shape drifted")
    if upstream != {
        "package": "zenoh-transport",
        "version": ZENOH_TRANSPORT_VERSION,
        "source": CRATES_IO_SOURCE,
        "sha256": ZENOH_TRANSPORT_REGISTRY_CHECKSUM,
        "tracked_file_manifest_sha256": ZENOH_UPSTREAM_TRACKED_MANIFEST_SHA256,
        "allowed_delta": upstream.get("allowed_delta"),
    }:
        raise RuntimeError("reviewed upstream crate identity drifted")
    delta = upstream.get("allowed_delta")
    if not isinstance(delta, dict) or set(delta) != {
        "added",
        "modified",
        "removed",
        "unchanged_file_count",
    }:
        raise RuntimeError("reviewed upstream delta shape drifted")
    return control


def _plain_file_records(
    root: Path,
    expected: list[dict[str, object]],
    *,
    marker_name: str,
    marker_bytes: bytes,
    mode_key: str,
) -> list[dict[str, object]]:
    """Verify an exact source tree without following links or accepting hardlinks."""

    expected_by_path = {
        str(record["path"]): record
        for record in expected
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    if len(expected_by_path) != len(expected):
        raise RuntimeError("expected source manifest contains duplicate paths")
    expected_directories: set[str] = set()
    for path in expected_by_path:
        parent = Path(path).parent
        while parent != Path("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent

    actual_files: dict[str, Path] = {}
    actual_directories: set[str] = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(root)
        directories.sort()
        files.sort()
        if relative_directory == Path(".") and ".git" in directories:
            git_entry = directory_path / ".git"
            git_mode = git_entry.lstat().st_mode
            if stat.S_ISLNK(git_mode) or not stat.S_ISDIR(git_mode):
                raise RuntimeError("Cargo Git administration path is not a directory")
            directories.remove(".git")
        for name in directories:
            path = directory_path / name
            entry_mode = path.lstat().st_mode
            if stat.S_ISLNK(entry_mode) or not stat.S_ISDIR(entry_mode):
                raise RuntimeError(
                    f"source tree contains linked/special directory: {path}"
                )
            actual_directories.add(path.relative_to(root).as_posix())
        for name in files:
            path = directory_path / name
            entry_mode = path.lstat().st_mode
            if stat.S_ISLNK(entry_mode) or not stat.S_ISREG(entry_mode):
                raise RuntimeError(f"source tree contains linked/special file: {path}")
            if path.stat().st_nlink != 1:
                raise RuntimeError(f"source tree contains a hardlinked file: {path}")
            actual_files[path.relative_to(root).as_posix()] = path

    if actual_directories != expected_directories:
        raise RuntimeError("source tree directory set differs from its manifest")
    expected_names = {*expected_by_path, marker_name}
    if set(actual_files) != expected_names:
        raise RuntimeError("source tree file set differs from its manifest")
    marker = actual_files[marker_name]
    if marker.read_bytes() != marker_bytes:
        raise RuntimeError(
            f"source marker {marker_name} differs from its reviewed value"
        )

    actual_records: list[dict[str, object]] = []
    for path_value in sorted(expected_by_path):
        expected_record = expected_by_path[path_value]
        path = actual_files[path_value]
        size = path.stat().st_size
        digest = sha256(path)
        expected_mode = expected_record.get(mode_key)
        if mode_key == "git_mode":
            mode = f"100{path.stat().st_mode & 0o777:03o}"
        else:
            mode = f"{path.stat().st_mode & 0o777:04o}"
        if (
            mode != expected_mode
            or size != expected_record.get("size_bytes")
            or digest != expected_record.get("sha256")
        ):
            raise RuntimeError(f"source file differs from its manifest: {path_value}")
        actual_records.append(
            {
                "path": path_value,
                mode_key: mode,
                "size_bytes": size,
                "sha256": digest,
            }
        )
    return actual_records


def _git_base(git: str, checkout: Path) -> list[str]:
    return [
        git,
        "--no-replace-objects",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.attributesFile=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "submodule.recurse=false",
        f"--git-dir={checkout / '.git'}",
        f"--work-tree={checkout}",
    ]


def backport_checkout_path(
    metadata: dict[str, object], qualification: Qualification
) -> Path:
    transport = one_metadata_package(
        metadata, "zenoh-transport", ZENOH_TRANSPORT_VERSION
    )
    manifest_value = transport.get("manifest_path")
    if not isinstance(manifest_value, str):
        raise RuntimeError("cargo metadata transport manifest path is unavailable")
    manifest = Path(manifest_value)
    if not manifest.is_absolute() or manifest.name != "Cargo.toml":
        raise RuntimeError("cargo metadata transport manifest path is malformed")
    try:
        checkout = manifest.parent.resolve(strict=True)
        relative = checkout.relative_to(qualification.cargo_home.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "Zenoh backport checkout escaped the fresh Cargo home"
        ) from error
    if relative.parts[:2] != ("git", "checkouts") or len(relative.parts) < 4:
        raise RuntimeError("Zenoh backport checkout is outside Cargo Git checkouts")
    current = qualification.cargo_home
    for part in relative.parts:
        current = current / part
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise RuntimeError("Zenoh backport checkout contains a directory alias")
    manifest_mode = manifest.lstat().st_mode
    if stat.S_ISLNK(manifest_mode) or not stat.S_ISREG(manifest_mode):
        raise RuntimeError("Zenoh backport Cargo.toml is linked or special")
    return checkout


def verify_backport_checkout(
    metadata: dict[str, object], qualification: Qualification
) -> dict[str, object]:
    checkout = backport_checkout_path(metadata, qualification)

    control = reviewed_backport_source()
    files = control["tracked_files"]
    if not isinstance(files, list):
        raise RuntimeError("reviewed source file manifest is unavailable")
    actual_files = _plain_file_records(
        checkout,
        files,
        marker_name=".cargo-ok",
        marker_bytes=b"",
        mode_key="git_mode",
    )
    base = _git_base(qualification.git, checkout)
    head = (
        run_capture(
            [*base, "rev-parse", "--verify", "HEAD"],
            env=qualification.env,
            cwd=qualification.work,
        )
        .decode("ascii", "strict")
        .strip()
    )
    tree = (
        run_capture(
            [*base, "rev-parse", "--verify", "HEAD^{tree}"],
            env=qualification.env,
            cwd=qualification.work,
        )
        .decode("ascii", "strict")
        .strip()
    )
    if head != ZENOH_BACKPORT_REVISION or tree != ZENOH_BACKPORT_TREE:
        raise RuntimeError("Zenoh backport checkout Git identity drifted")
    run(
        [*base, "fsck", "--strict", "--no-reflogs", "--no-dangling"],
        env=qualification.env,
        cwd=qualification.work,
    )
    run(
        [*base, "diff", "--no-ext-diff", "--quiet", "HEAD", "--"],
        env=qualification.env,
        cwd=qualification.work,
    )
    run(
        [*base, "diff", "--cached", "--no-ext-diff", "--quiet", "HEAD", "--"],
        env=qualification.env,
        cwd=qualification.work,
    )
    status = run_capture(
        [*base, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        env=qualification.env,
        cwd=qualification.work,
    )
    if status != b"?? .cargo-ok\0":
        raise RuntimeError("Zenoh backport checkout has unexpected untracked content")
    if canonical_json_sha256(actual_files) != ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256:
        raise RuntimeError("Zenoh backport checkout source manifest drifted")
    return {
        "repository": ZENOH_BACKPORT_GIT,
        "revision": ZENOH_BACKPORT_REVISION,
        "tree": ZENOH_BACKPORT_TREE,
        "tracked_file_manifest_sha256": ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256,
        "tracked_files": actual_files,
        "cargo_marker": {
            "path": ".cargo-ok",
            "size_bytes": 0,
            "sha256": sha256_bytes(b""),
        },
    }


def _stage_bounded_gzip(
    source: BinaryIO,
    destination: BinaryIO,
    *,
    maximum_expanded_bytes: int,
) -> int:
    """Decompress exactly one gzip member without crossing the expansion cap."""

    if maximum_expanded_bytes < 0:
        raise ValueError("gzip expansion limit must be non-negative")
    expanded = 0
    decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    try:
        while not decoder.eof:
            encoded = source.read(CRATE_STREAM_CHUNK_BYTES)
            if type(encoded) is not bytes:
                raise RuntimeError("crate gzip source returned an invalid chunk")
            if not encoded:
                break
            pending = encoded
            while pending and not decoder.eof:
                remaining = maximum_expanded_bytes - expanded
                before = len(pending)
                chunk = decoder.decompress(
                    pending,
                    min(CRATE_STREAM_CHUNK_BYTES, remaining + 1),
                )
                pending = decoder.unconsumed_tail
                if decoder.unused_data:
                    raise RuntimeError(
                        "crate archive contains trailing data or multiple gzip members"
                    )
                if len(chunk) > remaining:
                    raise RuntimeError(
                        "crate gzip stream exceeds its expanded-tar limit"
                    )
                if chunk and destination.write(chunk) != len(chunk):
                    raise RuntimeError("crate gzip staging write was incomplete")
                expanded += len(chunk)
                if not chunk and len(pending) >= before:
                    raise RuntimeError("crate gzip decoder made no bounded progress")
        if not decoder.eof:
            raise RuntimeError("crate archive is not a complete gzip stream")
        if decoder.unused_data or source.read(1):
            raise RuntimeError(
                "crate archive contains trailing data or multiple gzip members"
            )
    except RuntimeError:
        raise
    except (EOFError, OSError, zlib.error) as error:
        raise RuntimeError("crate archive is not a complete gzip stream") from error
    return expanded


class _BoundedTarReader:
    """Reject parser reads large enough to allocate unbounded extension metadata."""

    def __init__(
        self,
        stream: BinaryIO,
        *,
        maximum_read_bytes: int = MAX_CRATE_TAR_METADATA_ENTRY_BYTES,
    ) -> None:
        self._stream = stream
        self._maximum_read_bytes = maximum_read_bytes

    def read(self, size: int = -1) -> bytes:
        if size < 0 or size > self._maximum_read_bytes:
            raise RuntimeError("crate tar parser requested an oversized metadata read")
        return self._stream.read(size)

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        return self._stream.tell()


class _BoundedCrateTarInfo(tarfile.TarInfo):
    """Account for GNU/PAX extension bodies before ``tarfile`` parses them."""

    _EXTENSION_TYPES = frozenset(
        {
            tarfile.GNUTYPE_LONGNAME,
            tarfile.GNUTYPE_LONGLINK,
            tarfile.XHDTYPE,
            tarfile.XGLTYPE,
            tarfile.SOLARIS_XHDTYPE,
        }
    )

    def _proc_member(self, package: tarfile.TarFile) -> tarfile.TarInfo:
        if self.type == tarfile.GNUTYPE_SPARSE:
            raise RuntimeError("crate archive contains GNU sparse metadata")
        if self.type == tarfile.XGLTYPE:
            raise RuntimeError("crate archive contains amplifying global PAX metadata")
        if self.type in self._EXTENSION_TYPES:
            if self.size < 0 or self.size > MAX_CRATE_TAR_METADATA_ENTRY_BYTES:
                raise RuntimeError(
                    "crate tar extension metadata exceeds its entry limit"
                )
            consumed = int(getattr(package, "_ncp_extension_metadata_bytes", 0))
            consumed += self._block(self.size)
            if consumed > MAX_CRATE_TAR_METADATA_BYTES:
                raise RuntimeError(
                    "crate tar extension metadata exceeds its total limit"
                )
            package._ncp_extension_metadata_bytes = consumed
        result = super()._proc_member(package)
        if getattr(result, "sparse", None):
            raise RuntimeError("crate archive contains sparse file metadata")
        return result

    def _proc_pax(self, package: tarfile.TarFile) -> tarfile.TarInfo:
        position = package.fileobj.tell()
        payload = package.fileobj.read(self._block(self.size))
        package.fileobj.seek(position)
        if b"GNU.sparse" in payload:
            raise RuntimeError("crate archive contains PAX sparse metadata")
        return super()._proc_pax(package)


def _assert_complete_single_tar(package: tarfile.TarFile) -> None:
    """Require one tar payload with exactly two terminal zero records."""

    end = package.offset
    parser_position = package.fileobj.tell()
    package.fileobj.seek(0, os.SEEK_END)
    total = package.fileobj.tell()
    if (
        type(end) is not int
        or end < 0
        or end % TAR_RECORD_BYTES != 0
        or type(parser_position) is not int
        or parser_position != end + TAR_RECORD_BYTES
    ):
        raise RuntimeError("crate tar parser stopped at an inconsistent boundary")
    if total != end + TAR_TERMINATOR_BYTES:
        raise RuntimeError(
            "crate tar stream has an incomplete terminator or trailing records"
        )
    package.fileobj.seek(end)
    terminator = package.fileobj.read(TAR_TERMINATOR_BYTES)
    if terminator != b"\0" * TAR_TERMINATOR_BYTES:
        raise RuntimeError("crate tar stream lacks its exact terminal zero records")


@contextmanager
def _open_bounded_crate_tar(archive: Path) -> Iterator[tarfile.TarFile]:
    """Stage one bounded gzip member and expose one complete tar payload."""

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(archive, flags)
    except OSError as error:
        raise RuntimeError(f"cannot open crate archive {archive}: {error}") from error

    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > MAX_CRATE_ARCHIVE_BYTES
        ):
            raise RuntimeError(
                f"crate archive is linked, special, or oversized: {archive}"
            )
        fingerprint = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        with tempfile.TemporaryFile(prefix="ncp-crate-tar-") as staged:
            _stage_bounded_gzip(
                source,
                staged,
                maximum_expanded_bytes=MAX_CRATE_TAR_BYTES,
            )
            after = os.fstat(source.fileno())
            if fingerprint != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise RuntimeError("crate archive changed while it was decompressed")
            staged.flush()
            staged.seek(0)
            guarded = _BoundedTarReader(staged)
            try:
                with tarfile.open(
                    fileobj=guarded,
                    mode="r:",
                    tarinfo=_BoundedCrateTarInfo,
                ) as package:
                    yield package
                    _assert_complete_single_tar(package)
            except tarfile.TarError as error:
                raise RuntimeError(
                    f"crate tar stream is malformed: {archive.name}"
                ) from error


def _iter_bounded_tar_member(
    package: tarfile.TarFile, member: tarfile.TarInfo
) -> Iterator[bytes]:
    """Read one validated regular member without ``ExFileObject`` read-ahead.

    ``tarfile.ExFileObject`` is a buffered wrapper. A bounded caller read can make
    that wrapper request the member's larger remaining extent from the underlying
    tar stream. That implementation detail must not weaken the extension-metadata
    read cap or make a valid crate depend on one Python buffering strategy. Sparse
    and non-regular members are rejected before this helper is called.
    """

    if not member.isfile() or getattr(member, "sparse", None):
        raise RuntimeError("crate member stream is not a plain regular file")
    offset = member.offset_data
    if (
        type(offset) is not int
        or offset < 0
        or member.size < 0
        or member.size > MAX_CRATE_MEMBER_BYTES
        or offset > MAX_CRATE_TAR_BYTES
        or member.size > MAX_CRATE_TAR_BYTES - offset
    ):
        raise RuntimeError("crate member extent exceeds its staged-tar bound")

    package.fileobj.seek(offset)
    remaining = member.size
    while remaining:
        requested = min(CRATE_STREAM_CHUNK_BYTES, remaining)
        chunk = package.fileobj.read(requested)
        if type(chunk) is not bytes or not chunk or len(chunk) > requested:
            raise RuntimeError("crate member stream returned an invalid chunk")
        remaining -= len(chunk)
        yield chunk


def _streamed_crate_manifest(
    archive: Path, expected_prefix: str, *, retain: set[str] | None = None
) -> tuple[list[dict[str, object]], dict[str, bytes]]:
    retain = retain or set()
    try:
        archive_mode = archive.lstat().st_mode
        archive_size = archive.stat().st_size
    except OSError as error:
        raise RuntimeError(
            f"cannot inspect crate archive {archive}: {error}"
        ) from error
    if (
        stat.S_ISLNK(archive_mode)
        or not stat.S_ISREG(archive_mode)
        or archive.stat().st_nlink != 1
        or archive_size > MAX_CRATE_ARCHIVE_BYTES
    ):
        raise RuntimeError(f"crate archive is linked, special, or oversized: {archive}")

    records: list[dict[str, object]] = []
    retained: dict[str, bytes] = {}
    seen: set[str] = set()
    expanded = 0
    members = 0
    with _open_bounded_crate_tar(archive) as package:
        for member in package:
            members += 1
            if members > MAX_CRATE_MEMBERS:
                raise RuntimeError(
                    f"crate archive has too many members: {archive.name}"
                )
            path = Path(member.name)
            if (
                path.is_absolute()
                or not path.parts
                or path.parts[0] != expected_prefix
                or "." in path.parts
                or ".." in path.parts
                or "\\" in member.name
                or path.as_posix() != member.name.rstrip("/")
                or len(member.name.encode("utf-8")) > 512
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in member.name
                )
            ):
                raise RuntimeError(f"unsafe path in {archive.name}: {member.name}")
            canonical = path.as_posix()
            if canonical in seen:
                raise RuntimeError(f"duplicate path in {archive.name}: {member.name}")
            seen.add(canonical)
            if member.issym() or member.islnk():
                raise RuntimeError(f"link in {archive.name}: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(
                    f"special archive entry in {archive.name}: {member.name}"
                )
            if member.isdir():
                continue
            if member.size < 0 or member.size > MAX_CRATE_MEMBER_BYTES:
                raise RuntimeError(f"oversized member in {archive.name}: {member.name}")
            expanded += member.size
            if expanded > MAX_CRATE_EXPANDED_BYTES:
                raise RuntimeError(f"expanded crate exceeds its bound: {archive.name}")
            digest = hashlib.sha256()
            body = (
                bytearray()
                if path.relative_to(expected_prefix).as_posix() in retain
                else None
            )
            observed = 0
            for chunk in _iter_bounded_tar_member(package, member):
                observed += len(chunk)
                if observed > member.size:
                    raise RuntimeError(
                        f"member size overflow in {archive.name}: {member.name}"
                    )
                digest.update(chunk)
                if body is not None:
                    body.extend(chunk)
            if observed != member.size:
                raise RuntimeError(
                    f"member size mismatch in {archive.name}: {member.name}"
                )
            relative = path.relative_to(expected_prefix).as_posix()
            if not relative or relative == ".":
                raise RuntimeError(f"root file is malformed in {archive.name}")
            if relative in retain and member.size > MAX_RETAINED_CONTROL_BYTES:
                raise RuntimeError(
                    f"retained control exceeds its bound in {archive.name}: {relative}"
                )
            record = {
                "path": relative,
                "mode": f"{member.mode & 0o777:04o}",
                "size_bytes": member.size,
                "sha256": digest.hexdigest(),
            }
            records.append(record)
            if body is not None:
                retained[relative] = bytes(body)
    records.sort(key=lambda item: str(item["path"]))
    if len(records) != len({str(item["path"]) for item in records}):
        raise RuntimeError(f"crate file paths are duplicated: {archive.name}")
    if set(retained) != retain:
        raise RuntimeError(f"crate archive lacks retained controls: {archive.name}")
    return records, retained


def _registry_crate_archive(
    qualification: Qualification, *, package: str, version: str
) -> Path:
    cache_root = qualification.cargo_home / "registry" / "cache"
    candidates = sorted(cache_root.glob(f"*/{package}-{version}.crate"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"fresh Cargo home does not contain one exact {package} {version} crate"
        )
    return candidates[0]


def verify_registry_crate_source(
    metadata: dict[str, object],
    qualification: Qualification,
    *,
    package_name: str,
    version: str,
    checksum: str,
    retained_crate: str,
) -> dict[str, object]:
    package = one_metadata_package(metadata, package_name, version)
    manifest_value = package.get("manifest_path")
    if not isinstance(manifest_value, str):
        raise RuntimeError(
            f"cargo metadata {package_name} manifest path is unavailable"
        )
    manifest = Path(manifest_value)
    try:
        source = manifest.parent.resolve(strict=True)
        relative = source.relative_to(qualification.cargo_home.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise RuntimeError(
            f"{package_name} registry source escaped the fresh Cargo home"
        ) from error
    if (
        relative.parts[:2] != ("registry", "src")
        or source.name != f"{package_name}-{version}"
    ):
        raise RuntimeError(f"{package_name} registry source path is malformed")
    if manifest.resolve(strict=True) != source / "Cargo.toml":
        raise RuntimeError(f"{package_name} registry Cargo.toml is aliased")

    archive = _registry_crate_archive(
        qualification, package=package_name, version=version
    )
    if sha256(archive) != checksum:
        raise RuntimeError(
            f"fresh {package_name} crate archive checksum differs from Cargo.lock"
        )
    records, _ = _streamed_crate_manifest(archive, f"{package_name}-{version}")
    actual = _plain_file_records(
        source,
        records,
        marker_name=".cargo-ok",
        marker_bytes=REGISTRY_CARGO_OK,
        mode_key="mode",
    )
    if actual != records:
        raise RuntimeError(
            f"Cargo {package_name} extraction differs from its checksum-bound crate"
        )
    return {
        "package": package_name,
        "version": version,
        "source": CRATES_IO_SOURCE,
        "crate_sha256": checksum,
        "retained_crate": {
            "path": retained_crate,
            "size_bytes": archive.stat().st_size,
            "sha256": checksum,
        },
        "tracked_file_manifest_sha256": canonical_json_sha256(records),
        "tracked_files": records,
        "cargo_marker": {
            "path": ".cargo-ok",
            "size_bytes": len(REGISTRY_CARGO_OK),
            "sha256": sha256_bytes(REGISTRY_CARGO_OK),
        },
    }


def _normalized_source_records(
    records: object, *, mode_key: str
) -> dict[str, dict[str, object]]:
    if not isinstance(records, list):
        raise RuntimeError("source-delta file manifest is unavailable")
    normalized: dict[str, dict[str, object]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError("source-delta file record is malformed")
        path = _safe_manifest_path(record.get("path"), context="source delta")
        mode_value = record.get(mode_key)
        if mode_key == "git_mode":
            if mode_value not in {"100644", "100755"}:
                raise RuntimeError("source-delta Git mode is malformed")
            mode = f"0{str(mode_value)[-3:]}"
        else:
            if (
                not isinstance(mode_value, str)
                or re.fullmatch(r"0[0-7]{3}", mode_value) is None
            ):
                raise RuntimeError("source-delta crate mode is malformed")
            mode = mode_value
        normalized_record = {
            "path": path,
            "mode": mode,
            "size_bytes": record.get("size_bytes"),
            "sha256": record.get("sha256"),
        }
        if path in normalized:
            raise RuntimeError("source-delta file path is duplicated")
        normalized[path] = normalized_record
    return normalized


def verify_backport_upstream_delta(
    upstream_source: dict[str, object], backport_source: dict[str, object]
) -> dict[str, object]:
    """Prove the pinned fork differs from the checksum-bound crate only as reviewed."""

    control = reviewed_backport_source()
    upstream_control = control["upstream_crate"]
    if not isinstance(upstream_control, dict):
        raise RuntimeError("reviewed upstream crate control is unavailable")
    if (
        upstream_source.get("crate_sha256") != ZENOH_TRANSPORT_REGISTRY_CHECKSUM
        or upstream_source.get("tracked_file_manifest_sha256")
        != ZENOH_UPSTREAM_TRACKED_MANIFEST_SHA256
    ):
        raise RuntimeError("checksum-bound upstream transport source drifted")
    upstream = _normalized_source_records(
        upstream_source.get("tracked_files"), mode_key="mode"
    )
    backport = _normalized_source_records(
        backport_source.get("tracked_files"), mode_key="git_mode"
    )
    added_paths = sorted(backport.keys() - upstream.keys())
    removed_paths = sorted(upstream.keys() - backport.keys())
    shared_paths = sorted(upstream.keys() & backport.keys())
    modified_paths = [path for path in shared_paths if upstream[path] != backport[path]]
    delta = {
        "added": [
            {"path": path, "sha256": backport[path]["sha256"]} for path in added_paths
        ],
        "modified": [
            {
                "path": path,
                "upstream_sha256": upstream[path]["sha256"],
                "backport_sha256": backport[path]["sha256"],
            }
            for path in modified_paths
        ],
        "removed": [
            {"path": path, "sha256": upstream[path]["sha256"]} for path in removed_paths
        ],
        "unchanged_file_count": len(shared_paths) - len(modified_paths),
    }
    if delta != upstream_control.get("allowed_delta"):
        raise RuntimeError(
            "Zenoh backport differs from upstream outside the reviewed delta"
        )
    return {
        "status": "PASS_EXACT_ALLOWED_DELTA",
        "upstream_tracked_file_manifest_sha256": (
            ZENOH_UPSTREAM_TRACKED_MANIFEST_SHA256
        ),
        "backport_tracked_file_manifest_sha256": (
            ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256
        ),
        "added_file_count": len(added_paths),
        "modified_file_count": len(modified_paths),
        "removed_file_count": len(removed_paths),
        "unchanged_file_count": len(shared_paths) - len(modified_paths),
    }


def verify_conditioned_sources(
    metadata: dict[str, object],
    unpatched_metadata: dict[str, object],
    qualification: Qualification,
) -> dict[str, object]:
    """Bind the resolved source identities to the bytes in the fresh Cargo home."""

    upstream = verify_registry_crate_source(
        unpatched_metadata,
        qualification,
        package_name="zenoh-transport",
        version=ZENOH_TRANSPORT_VERSION,
        checksum=ZENOH_TRANSPORT_REGISTRY_CHECKSUM,
        retained_crate=RETAINED_UPSTREAM_TRANSPORT_CRATE,
    )
    backport = verify_backport_checkout(metadata, qualification)
    return {
        "zenoh_transport_upstream": upstream,
        "zenoh_transport_upstream_delta": verify_backport_upstream_delta(
            upstream, backport
        ),
        "zenoh_transport_backport": backport,
        "lz4_flex": verify_registry_crate_source(
            metadata,
            qualification,
            package_name="lz4_flex",
            version=FIXED_LZ4_VERSION,
            checksum=FIXED_LZ4_CHECKSUM,
            retained_crate=RETAINED_LZ4_CRATE,
        ),
        "twox_hash": verify_registry_crate_source(
            metadata,
            qualification,
            package_name="twox-hash",
            version=CONDITIONED_TWOX_VERSION,
            checksum=CONDITIONED_TWOX_CHECKSUM,
            retained_crate=RETAINED_TWOX_CRATE,
        ),
    }


def assert_consumer_source_point_match(
    before: dict[str, dict[str, object]],
    after: dict[str, dict[str, object]],
) -> None:
    expected = set(ZENOH_CONDITIONAL_CRATES)
    if set(before) != expected or set(after) != expected:
        raise RuntimeError("conditioned consumer source evidence is incomplete")
    canonical = before[ZENOH_CONDITIONAL_CRATES[0]]
    for crate in ZENOH_CONDITIONAL_CRATES:
        if before[crate] != canonical:
            raise RuntimeError(
                "conditioned consumers resolved different reviewed source bytes"
            )
        if after[crate] != before[crate]:
            raise RuntimeError(
                f"{crate} reviewed Cargo source bytes changed during offline compilation"
            )


def assert_unpatched_archive_fallback(
    crate: str,
    manifest: dict[str, object],
    lock: dict[str, object],
    lock_sha256: str,
) -> dict[str, object]:
    """Prove the normalized archive alone retains the unsafe registry fallback."""

    if crate not in ZENOH_CONDITIONAL_CRATES:
        raise RuntimeError(f"unexpected conditional Zenoh archive: {crate}")
    if "patch" in manifest:
        raise RuntimeError(f"{crate} normalized archive unexpectedly contains a patch")
    if HEX_SHA256.fullmatch(lock_sha256) is None:
        raise RuntimeError(f"{crate} archive Cargo.lock digest is malformed")
    transport = one_lock_package(lock, "zenoh-transport", ZENOH_TRANSPORT_VERSION)
    if (
        transport.get("source") != CRATES_IO_SOURCE
        or transport.get("checksum") != ZENOH_TRANSPORT_REGISTRY_CHECKSUM
    ):
        raise RuntimeError(
            f"{crate} archive no longer demonstrates the reviewed registry fallback"
        )
    dependencies = transport.get("dependencies")
    if not isinstance(dependencies, list) or "lz4_flex" not in dependencies:
        raise RuntimeError(f"{crate} archive lost the transport-to-lz4 dependency edge")
    lz4 = one_lock_package(lock, "lz4_flex", VULNERABLE_LZ4_VERSION)
    if (
        lz4.get("source") != CRATES_IO_SOURCE
        or lz4.get("checksum") != VULNERABLE_LZ4_CHECKSUM
    ):
        raise RuntimeError(
            f"{crate} archive no longer demonstrates the vulnerable lz4 fallback"
        )
    lz4_dependencies = lz4.get("dependencies")
    if not isinstance(lz4_dependencies, list) or "twox-hash" not in lz4_dependencies:
        raise RuntimeError(f"{crate} archive lost the lz4-to-twox dependency edge")
    twox = one_lock_package(lock, "twox-hash", FALLBACK_TWOX_VERSION)
    if (
        twox.get("source") != CRATES_IO_SOURCE
        or twox.get("checksum") != FALLBACK_TWOX_CHECKSUM
    ):
        raise RuntimeError(f"{crate} archive fallback twox-hash identity drifted")
    return {
        "crate": crate,
        "cargo_lock_sha256": lock_sha256,
        "advisory": "RUSTSEC-2026-0041",
        "zenoh_transport_source": CRATES_IO_SOURCE,
        "zenoh_transport_checksum_sha256": ZENOH_TRANSPORT_REGISTRY_CHECKSUM,
        "lz4_flex_version": VULNERABLE_LZ4_VERSION,
        "lz4_flex_source": CRATES_IO_SOURCE,
        "lz4_flex_checksum_sha256": VULNERABLE_LZ4_CHECKSUM,
        "twox_hash_version": FALLBACK_TWOX_VERSION,
        "twox_hash_source": CRATES_IO_SOURCE,
        "twox_hash_checksum_sha256": FALLBACK_TWOX_CHECKSUM,
        "compiled": False,
    }


def validate_conditioned_zenoh_lock(lock: dict[str, object]) -> None:
    transports = [
        package
        for package in lock.get("package", [])
        if isinstance(package, dict) and package.get("name") == "zenoh-transport"
    ]
    if len(transports) != 1:
        raise RuntimeError("conditioned lock has an incomplete Zenoh transport set")
    transport = one_lock_package(lock, "zenoh-transport", ZENOH_TRANSPORT_VERSION)
    if transport.get("source") != ZENOH_BACKPORT_SOURCE or "checksum" in transport:
        raise RuntimeError("conditioned lock does not select the exact Zenoh backport")
    dependencies = transport.get("dependencies")
    if not isinstance(dependencies, list) or "lz4_flex" not in dependencies:
        raise RuntimeError("conditioned lock lost the transport-to-lz4 dependency edge")

    lz4_packages = [
        package
        for package in lock.get("package", [])
        if isinstance(package, dict) and package.get("name") == "lz4_flex"
    ]
    if len(lz4_packages) != 1:
        raise RuntimeError("conditioned lock has an incomplete lz4_flex set")
    lz4 = one_lock_package(lock, "lz4_flex", FIXED_LZ4_VERSION)
    if (
        lz4.get("source") != CRATES_IO_SOURCE
        or lz4.get("checksum") != FIXED_LZ4_CHECKSUM
    ):
        raise RuntimeError("conditioned lock does not select exact fixed lz4_flex")
    lz4_dependencies = lz4.get("dependencies")
    if not isinstance(lz4_dependencies, list) or "twox-hash" not in lz4_dependencies:
        raise RuntimeError("conditioned lock lost the lz4-to-twox dependency edge")
    twox_packages = [
        package
        for package in lock.get("package", [])
        if isinstance(package, dict) and package.get("name") == "twox-hash"
    ]
    if len(twox_packages) != 1:
        raise RuntimeError("conditioned lock has an incomplete twox-hash set")
    twox = one_lock_package(lock, "twox-hash", CONDITIONED_TWOX_VERSION)
    if (
        twox.get("source") != CRATES_IO_SOURCE
        or twox.get("checksum") != CONDITIONED_TWOX_CHECKSUM
    ):
        raise RuntimeError("conditioned lock does not select exact twox-hash update")


def _unrelated_lock_projection(lock: dict[str, object]) -> dict[str, object]:
    """Return every lock value except the three deliberately conditioned packages."""

    packages = lock.get("package")
    if not isinstance(packages, list):
        raise RuntimeError("Cargo.lock package array is malformed")
    identities: set[tuple[str, str, str | None]] = set()
    retained: list[dict[str, object]] = []
    for package in packages:
        if (
            not isinstance(package, dict)
            or not isinstance(package.get("name"), str)
            or not isinstance(package.get("version"), str)
            or (
                package.get("source") is not None
                and not isinstance(package.get("source"), str)
            )
        ):
            raise RuntimeError("Cargo.lock contains a malformed package record")
        identity = (
            str(package["name"]),
            str(package["version"]),
            package.get("source"),
        )
        if identity in identities:
            raise RuntimeError("Cargo.lock contains a duplicate package identity")
        identities.add(identity)
        if package["name"] not in {"zenoh-transport", "lz4_flex", "twox-hash"}:
            retained.append(package)
    projection = dict(lock)
    projection["package"] = retained
    return projection


def validate_conditioned_lock_transition(
    fallback: dict[str, object], conditioned: dict[str, object]
) -> None:
    """Reject any lock drift outside the reviewed transport/lz4 substitution."""

    if _unrelated_lock_projection(fallback) != _unrelated_lock_projection(conditioned):
        raise RuntimeError("conditioned lock changed an unrelated dependency record")

    def exact_named_record(
        lock: dict[str, object], name: str, *, context: str
    ) -> dict[str, object]:
        packages = lock.get("package")
        if not isinstance(packages, list):
            raise RuntimeError(f"{context} Cargo.lock package array is malformed")
        matches = [
            package
            for package in packages
            if isinstance(package, dict) and package.get("name") == name
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"{context} Cargo.lock does not contain one exact {name} record"
            )
        return matches[0]

    fallback_transport = exact_named_record(
        fallback, "zenoh-transport", context="fallback"
    )
    conditioned_transport = exact_named_record(
        conditioned, "zenoh-transport", context="conditioned"
    )
    expected_transport = dict(fallback_transport)
    if set(expected_transport) != {
        "name",
        "version",
        "source",
        "checksum",
        "dependencies",
    }:
        raise RuntimeError("fallback Zenoh transport lock record shape drifted")
    expected_transport["source"] = ZENOH_BACKPORT_SOURCE
    expected_transport.pop("checksum")
    if conditioned_transport != expected_transport:
        raise RuntimeError("conditioned Zenoh transport lock delta is not exact")

    fallback_lz4 = exact_named_record(fallback, "lz4_flex", context="fallback")
    conditioned_lz4 = exact_named_record(conditioned, "lz4_flex", context="conditioned")
    expected_lz4 = dict(fallback_lz4)
    if set(expected_lz4) != {
        "name",
        "version",
        "source",
        "checksum",
        "dependencies",
    }:
        raise RuntimeError("fallback lz4_flex lock record shape drifted")
    expected_lz4["version"] = FIXED_LZ4_VERSION
    expected_lz4["checksum"] = FIXED_LZ4_CHECKSUM
    if conditioned_lz4 != expected_lz4:
        raise RuntimeError("conditioned lz4_flex lock delta is not exact")

    fallback_twox = exact_named_record(fallback, "twox-hash", context="fallback")
    conditioned_twox = exact_named_record(
        conditioned, "twox-hash", context="conditioned"
    )
    expected_twox = dict(fallback_twox)
    if set(expected_twox) != {
        "name",
        "version",
        "source",
        "checksum",
        "dependencies",
    } or expected_twox.get("dependencies") != ["cfg-if", "static_assertions"]:
        raise RuntimeError("fallback twox-hash lock record shape drifted")
    expected_twox["version"] = CONDITIONED_TWOX_VERSION
    expected_twox["checksum"] = CONDITIONED_TWOX_CHECKSUM
    expected_twox.pop("dependencies")
    if conditioned_twox != expected_twox:
        raise RuntimeError("conditioned twox-hash lock delta is not exact")


def one_metadata_package(
    metadata: dict[str, object], name: str, version: str
) -> dict[str, object]:
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        raise RuntimeError("cargo metadata package array is malformed")
    matches = [
        package
        for package in packages
        if isinstance(package, dict)
        and package.get("name") == name
        and package.get("version") == version
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"cargo metadata does not contain one exact {name} {version} package"
        )
    return matches[0]


def _metadata_maps(
    metadata: dict[str, object],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    packages = metadata.get("packages")
    resolve = metadata.get("resolve")
    nodes = resolve.get("nodes") if isinstance(resolve, dict) else None
    if not isinstance(packages, list) or not isinstance(nodes, list):
        raise RuntimeError(
            "cargo metadata package or resolved-node array is unavailable"
        )
    package_ids: dict[str, dict[str, object]] = {}
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("id"), str):
            raise RuntimeError("cargo metadata contains a malformed package")
        package_id = package["id"]
        if package_id in package_ids:
            raise RuntimeError("cargo metadata contains a duplicate package identity")
        package_ids[package_id] = package
    resolved: dict[str, dict[str, object]] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise RuntimeError("cargo metadata contains a malformed resolved node")
        node_id = node["id"]
        if node_id in resolved:
            raise RuntimeError(
                "cargo metadata contains a duplicate resolved-node identity"
            )
        resolved[node_id] = node
    return package_ids, resolved


def _resolved_features(node: dict[str, object], label: str) -> list[str]:
    features = node.get("features")
    if not isinstance(features, list) or not all(
        isinstance(feature, str) and feature for feature in features
    ):
        raise RuntimeError(f"{label} resolved feature set is malformed")
    if len(features) != len(set(features)):
        raise RuntimeError(f"{label} resolved feature set contains duplicates")
    return sorted(features)


def _resolution_projection(
    metadata: dict[str, object], *, crate: str, target: str, conditioned: bool
) -> dict[str, object]:
    if crate not in ZENOH_CONDITIONAL_CRATES or TARGET_TRIPLE.fullmatch(target) is None:
        raise RuntimeError("cargo metadata projection identity is malformed")
    lz4_version = FIXED_LZ4_VERSION if conditioned else VULNERABLE_LZ4_VERSION
    twox_version = CONDITIONED_TWOX_VERSION if conditioned else FALLBACK_TWOX_VERSION
    transport = one_metadata_package(
        metadata, "zenoh-transport", ZENOH_TRANSPORT_VERSION
    )
    lz4 = one_metadata_package(metadata, "lz4_flex", lz4_version)
    twox = one_metadata_package(metadata, "twox-hash", twox_version)
    zenoh = one_metadata_package(metadata, "zenoh", ZENOH_TRANSPORT_VERSION)
    package_ids, resolved = _metadata_maps(metadata)
    selected = (zenoh, transport, lz4, twox)
    for package in selected:
        package_id = package.get("id")
        if not isinstance(package_id, str) or package_id not in package_ids:
            raise RuntimeError("cargo metadata selected package identity is malformed")
        if package_id not in resolved:
            raise RuntimeError("cargo metadata selected package has no resolved node")
    transport_id = str(transport["id"])
    lz4_id = str(lz4["id"])
    twox_id = str(twox["id"])

    def resolved_dependency_ids(package_id: str, label: str) -> list[str]:
        dependencies = resolved[package_id].get("deps")
        if not isinstance(dependencies, list):
            raise RuntimeError(f"cargo metadata {label} dependency set is malformed")
        dependency_ids: list[str] = []
        for dependency in dependencies:
            if not isinstance(dependency, dict) or not isinstance(
                dependency.get("pkg"), str
            ):
                raise RuntimeError(f"cargo metadata {label} dependency is malformed")
            dependency_ids.append(dependency["pkg"])
        if len(dependency_ids) != len(set(dependency_ids)):
            raise RuntimeError(f"cargo metadata {label} dependencies are duplicated")
        return dependency_ids

    if lz4_id not in resolved_dependency_ids(transport_id, "transport"):
        raise RuntimeError("cargo metadata lost the exact transport-to-lz4 edge")
    if twox_id not in resolved_dependency_ids(lz4_id, "lz4"):
        raise RuntimeError("cargo metadata lost the exact lz4-to-twox edge")
    feature_records = []
    for package in selected:
        package_id = str(package["id"])
        feature_records.append(
            {
                "name": package["name"],
                "version": package["version"],
                "features": _resolved_features(
                    resolved[package_id], str(package["name"])
                ),
            }
        )
    return {
        "root_crate": crate,
        "target": target,
        "packages": [
            {
                "name": package["name"],
                "version": package["version"],
                "source": package.get("source"),
            }
            for package in selected
        ],
        "resolved_features": feature_records,
        "transport_to_lz4": {
            "from": "zenoh-transport",
            "to": "lz4_flex",
            "present": True,
        },
        "lz4_to_twox_hash": {
            "from": "lz4_flex",
            "to": "twox-hash",
            "present": True,
        },
    }


def validate_resolution_projection(
    value: object, *, crate: str, target: str, conditioned: bool
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "root_crate",
        "target",
        "packages",
        "resolved_features",
        "transport_to_lz4",
        "lz4_to_twox_hash",
    }:
        raise RuntimeError("retained cargo metadata projection shape is invalid")
    if value.get("root_crate") != crate or value.get("target") != target:
        raise RuntimeError("retained cargo metadata projection identity drifted")
    lz4_version = FIXED_LZ4_VERSION if conditioned else VULNERABLE_LZ4_VERSION
    twox_version = CONDITIONED_TWOX_VERSION if conditioned else FALLBACK_TWOX_VERSION
    transport_source = ZENOH_BACKPORT_SOURCE if conditioned else CRATES_IO_SOURCE
    expected_packages = [
        {
            "name": "zenoh",
            "version": ZENOH_TRANSPORT_VERSION,
            "source": CRATES_IO_SOURCE,
        },
        {
            "name": "zenoh-transport",
            "version": ZENOH_TRANSPORT_VERSION,
            "source": transport_source,
        },
        {
            "name": "lz4_flex",
            "version": lz4_version,
            "source": CRATES_IO_SOURCE,
        },
        {
            "name": "twox-hash",
            "version": twox_version,
            "source": CRATES_IO_SOURCE,
        },
    ]
    if value.get("packages") != expected_packages:
        raise RuntimeError("retained cargo metadata package selection drifted")
    features = value.get("resolved_features")
    if not isinstance(features, list) or len(features) != 4:
        raise RuntimeError("retained cargo metadata feature evidence is incomplete")
    for expected, record in zip(expected_packages, features, strict=True):
        if not isinstance(record, dict) or set(record) != {
            "name",
            "version",
            "features",
        }:
            raise RuntimeError("retained cargo metadata feature record is malformed")
        feature_values = record.get("features")
        if (
            record.get("name") != expected["name"]
            or record.get("version") != expected["version"]
            or not isinstance(feature_values, list)
            or not all(isinstance(item, str) and item for item in feature_values)
            or feature_values != sorted(set(feature_values))
        ):
            raise RuntimeError("retained cargo metadata feature record drifted")
        if record.get("name") in {"zenoh", "zenoh-transport"} and {
            "default",
            "transport_compression",
        }.intersection(feature_values):
            raise RuntimeError("retained cargo metadata enables forbidden features")
    if value.get("transport_to_lz4") != {
        "from": "zenoh-transport",
        "to": "lz4_flex",
        "present": True,
    }:
        raise RuntimeError("retained cargo metadata lost the transport-to-lz4 edge")
    if value.get("lz4_to_twox_hash") != {
        "from": "lz4_flex",
        "to": "twox-hash",
        "present": True,
    }:
        raise RuntimeError("retained cargo metadata lost the lz4-to-twox edge")


def validate_conditioned_zenoh_metadata(
    metadata: dict[str, object], *, crate: str, target: str
) -> dict[str, object]:
    transport = one_metadata_package(
        metadata, "zenoh-transport", ZENOH_TRANSPORT_VERSION
    )
    lz4 = one_metadata_package(metadata, "lz4_flex", FIXED_LZ4_VERSION)
    zenoh = one_metadata_package(metadata, "zenoh", ZENOH_TRANSPORT_VERSION)
    if transport.get("source") != ZENOH_BACKPORT_SOURCE:
        raise RuntimeError("cargo metadata Zenoh transport source drifted")
    if transport.get("rust_version") != "1.81.0":
        raise RuntimeError("cargo metadata Zenoh transport Rust floor drifted")
    if lz4.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("cargo metadata lz4_flex source drifted")
    if zenoh.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("cargo metadata Zenoh source drifted")

    package_ids, resolved = _metadata_maps(metadata)
    transport_id = transport.get("id")
    lz4_id = lz4.get("id")
    zenoh_id = zenoh.get("id")
    if not all(isinstance(item, str) for item in (transport_id, lz4_id, zenoh_id)):
        raise RuntimeError("cargo metadata package identity is malformed")
    transport_node = resolved.get(transport_id)
    zenoh_node = resolved.get(zenoh_id)
    if not isinstance(transport_node, dict) or not isinstance(zenoh_node, dict):
        raise RuntimeError("cargo metadata Zenoh nodes are unavailable")
    for label, node in (("Zenoh", zenoh_node), ("Zenoh transport", transport_node)):
        features = _resolved_features(node, label)
        forbidden = {"default", "transport_compression"}.intersection(features)
        if forbidden:
            raise RuntimeError(
                f"{label} enables forbidden features: {sorted(forbidden)}"
            )
    dependency_ids: set[str] = set()
    dependencies = transport_node.get("deps")
    if not isinstance(dependencies, list):
        raise RuntimeError("cargo metadata transport dependency set is malformed")
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(
            dependency.get("pkg"), str
        ):
            raise RuntimeError("cargo metadata transport dependency is malformed")
        dependency_ids.add(dependency["pkg"])
    if lz4_id not in dependency_ids or lz4_id not in package_ids:
        raise RuntimeError("cargo metadata lost the exact transport-to-lz4 edge")
    projection = _resolution_projection(
        metadata, crate=crate, target=target, conditioned=True
    )
    validate_resolution_projection(
        projection, crate=crate, target=target, conditioned=True
    )
    return projection


def validate_unpatched_zenoh_metadata(
    metadata: dict[str, object], *, crate: str, target: str
) -> dict[str, object]:
    """Verify an executed archive-alone resolution exposes the unsafe fallback."""

    transport = one_metadata_package(
        metadata, "zenoh-transport", ZENOH_TRANSPORT_VERSION
    )
    lz4 = one_metadata_package(metadata, "lz4_flex", VULNERABLE_LZ4_VERSION)
    if transport.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("archive-alone metadata did not select registry transport")
    if lz4.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("archive-alone metadata did not select registry lz4_flex")
    resolve = metadata.get("resolve")
    nodes = resolve.get("nodes") if isinstance(resolve, dict) else None
    if not isinstance(nodes, list):
        raise RuntimeError("archive-alone metadata resolved nodes are unavailable")
    _metadata_maps(metadata)
    transport_id = transport.get("id")
    lz4_id = lz4.get("id")
    if not isinstance(transport_id, str) or not isinstance(lz4_id, str):
        raise RuntimeError("archive-alone metadata package identity is malformed")
    transport_nodes = [
        node
        for node in nodes
        if isinstance(node, dict) and node.get("id") == transport_id
    ]
    if len(transport_nodes) != 1:
        raise RuntimeError("archive-alone metadata transport node is unavailable")
    dependencies = transport_nodes[0].get("deps")
    if not isinstance(dependencies, list) or lz4_id not in {
        dependency.get("pkg")
        for dependency in dependencies
        if isinstance(dependency, dict)
    }:
        raise RuntimeError("archive-alone metadata lost the vulnerable lz4 edge")
    projection = _resolution_projection(
        metadata, crate=crate, target=target, conditioned=False
    )
    validate_resolution_projection(
        projection, crate=crate, target=target, conditioned=False
    )
    return projection


def condition_zenoh_archive(
    crate: str,
    extracted_paths: dict[str, Path],
    archive: Path,
    *,
    target: str,
    qualification: Qualification,
    version: str,
) -> tuple[
    list[str],
    dict[str, object],
    dict[str, object],
    bytes,
    dict[str, object],
    dict[str, object],
]:
    archive_root = extracted_paths[crate]
    manifest_path = archive_root / "Cargo.toml"
    lock_path = archive_root / "Cargo.lock"
    archive_files, controls = _streamed_crate_manifest(
        archive,
        f"{crate}-{version}",
        retain={"Cargo.toml", "Cargo.lock"},
    )
    if (
        manifest_path.read_bytes() != controls["Cargo.toml"]
        or lock_path.read_bytes() != controls["Cargo.lock"]
    ):
        raise RuntimeError(f"{crate} extracted controls differ from its crate archive")
    fallback_manifest = load_toml_bytes(
        controls["Cargo.toml"], f"{crate} archive Cargo.toml"
    )
    fallback_lock = load_toml_bytes(
        controls["Cargo.lock"], f"{crate} archive Cargo.lock"
    )
    fallback = assert_unpatched_archive_fallback(
        crate,
        fallback_manifest,
        fallback_lock,
        sha256_bytes(controls["Cargo.lock"]),
    )
    local_patch_args = cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths)
    fetch_locked_archive(
        manifest_path,
        local_patch_args,
        target=target,
        qualification=qualification,
    )
    unpatched_metadata_command = cargo_command(
        qualification,
        "metadata",
        "--manifest-path",
        str(manifest_path),
        "--format-version",
        "1",
        "--locked",
        "--offline",
        "--filter-platform",
        target,
        *local_patch_args,
    )
    try:
        unpatched_metadata = json.loads(
            run_capture(
                unpatched_metadata_command,
                env=qualification.env,
                cwd=qualification.work,
            )
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{crate} archive-alone cargo metadata is not JSON"
        ) from error
    if not isinstance(unpatched_metadata, dict):
        raise RuntimeError(f"{crate} archive-alone cargo metadata is not an object")
    fallback_projection = validate_unpatched_zenoh_metadata(
        unpatched_metadata, crate=crate, target=target
    )
    fallback["resolution_observation"] = "EXECUTED_OBSERVED_VULNERABLE"
    fallback["resolution_projection"] = fallback_projection

    patch_args = [*local_patch_args, *zenoh_backport_patch_args()]
    update = cargo_command(
        qualification,
        "update",
        "--manifest-path",
        str(manifest_path),
        "-p",
        f"zenoh-transport@{ZENOH_TRANSPORT_VERSION}",
        "--precise",
        ZENOH_TRANSPORT_VERSION,
        *patch_args,
    )
    run(update, env=qualification.env, cwd=qualification.work)
    conditioned_lock_bytes = lock_path.read_bytes()
    if len(conditioned_lock_bytes) > MAX_RETAINED_CONTROL_BYTES:
        raise RuntimeError(f"{crate} conditioned Cargo.lock exceeds its bound")
    conditioned_lock = load_toml_bytes(
        conditioned_lock_bytes, f"{crate} conditioned Cargo.lock"
    )
    validate_conditioned_zenoh_lock(conditioned_lock)
    validate_conditioned_lock_transition(fallback_lock, conditioned_lock)
    fetch_locked_archive(
        manifest_path,
        patch_args,
        target=target,
        qualification=qualification,
    )

    metadata_command = cargo_command(
        qualification,
        "metadata",
        "--manifest-path",
        str(manifest_path),
        "--format-version",
        "1",
        "--locked",
        "--offline",
        "--filter-platform",
        target,
        *patch_args,
    )
    try:
        metadata = json.loads(
            run_capture(
                metadata_command,
                env=qualification.env,
                cwd=qualification.work,
            )
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{crate} cargo metadata is not JSON") from error
    if not isinstance(metadata, dict):
        raise RuntimeError(f"{crate} cargo metadata is not an object")
    projection = validate_conditioned_zenoh_metadata(
        metadata, crate=crate, target=target
    )
    source_integrity = verify_conditioned_sources(
        metadata, unpatched_metadata, qualification
    )
    consumer = {
        "crate": crate,
        "target": target,
        "archive": {
            "path": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": sha256(archive),
            "file_manifest_sha256": canonical_json_sha256(archive_files),
        },
        "archive_fallback_cargo_lock_sha256": fallback["cargo_lock_sha256"],
        "conditioned_lock": {
            "path": RETAINED_CONDITIONED_LOCKS[crate],
            "size_bytes": len(conditioned_lock_bytes),
            "sha256": sha256_bytes(conditioned_lock_bytes),
        },
        "resolution_projection": projection,
        "cargo_offline_mode_for_compile": True,
        "compile_steps": [],
    }
    return (
        patch_args,
        fallback,
        consumer,
        conditioned_lock_bytes,
        source_integrity,
        (unpatched_metadata, metadata),
    )


def _retained_artifact(root: Path, relative_value: object) -> tuple[str, Path]:
    relative = _safe_manifest_path(relative_value, context="retained artifact")
    root_resolved = root.resolve(strict=True)
    path = root / relative
    current = root
    for part in Path(relative).parts[:-1]:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as error:
            raise RuntimeError(
                f"retained artifact parent is unavailable: {relative}"
            ) from error
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise RuntimeError(f"retained artifact parent is aliased: {relative}")
    try:
        mode = path.lstat().st_mode
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"retained artifact is unavailable: {relative}") from error
    if (
        stat.S_ISLNK(mode)
        or not stat.S_ISREG(mode)
        or path.stat().st_nlink != 1
        or resolved.parent
        != (root_resolved / Path(relative).parent).resolve(strict=True)
    ):
        raise RuntimeError(
            f"retained artifact is linked, special, or aliased: {relative}"
        )
    return relative, path


def _validate_artifact_record(
    value: object,
    *,
    root: Path,
    expected_path: str,
    maximum_bytes: int,
) -> Path:
    if not isinstance(value, dict) or set(value) != {
        "path",
        "size_bytes",
        "sha256",
    }:
        raise RuntimeError("retained artifact record shape is invalid")
    if value.get("path") != expected_path:
        raise RuntimeError("retained artifact path drifted")
    _, path = _retained_artifact(root, value.get("path"))
    digest = value.get("sha256")
    size = value.get("size_bytes")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or size > maximum_bytes
        or not isinstance(digest, str)
        or HEX_SHA256.fullmatch(digest) is None
        or path.stat().st_size != size
        or sha256(path) != digest
    ):
        raise RuntimeError("retained artifact bytes differ from their record")
    return path


def _retained_tree_entries(root: Path) -> tuple[set[str], set[str]]:
    """Return an exact retained tree and reject aliases or special entries."""

    try:
        root_mode = root.lstat().st_mode
    except OSError as error:
        raise RuntimeError("retained Rust artifact root is unavailable") from error
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise RuntimeError("retained Rust artifact root is linked or special")

    directory_names: set[str] = set()
    file_names: set[str] = set()
    for directory, directories, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directories.sort()
        files.sort()
        for name in directories:
            path = directory_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise RuntimeError("retained Rust artifact tree contains an alias")
            directory_names.add(path.relative_to(root).as_posix())
        for name in files:
            path = directory_path / name
            mode = path.lstat().st_mode
            if (
                stat.S_ISLNK(mode)
                or not stat.S_ISREG(mode)
                or path.stat().st_nlink != 1
            ):
                raise RuntimeError(
                    "retained Rust artifact tree contains a linked or special file"
                )
            file_names.add(path.relative_to(root).as_posix())
    return directory_names, file_names


def _validate_crate_file_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or len(value) > MAX_CRATE_MEMBERS:
        raise RuntimeError("retained crate file manifest is malformed")
    records: list[dict[str, object]] = []
    paths: list[str] = []
    expanded = 0
    for record in value:
        if not isinstance(record, dict) or set(record) != {
            "path",
            "mode",
            "size_bytes",
            "sha256",
        }:
            raise RuntimeError("retained crate file record shape is invalid")
        path = _safe_manifest_path(record.get("path"), context="crate file manifest")
        size = record.get("size_bytes")
        digest = record.get("sha256")
        if (
            not isinstance(record.get("mode"), str)
            or re.fullmatch(r"0[0-7]{3}", str(record["mode"])) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_CRATE_MEMBER_BYTES
            or not isinstance(digest, str)
            or HEX_SHA256.fullmatch(digest) is None
        ):
            raise RuntimeError("retained crate file identity is malformed")
        expanded += size
        if expanded > MAX_CRATE_EXPANDED_BYTES:
            raise RuntimeError("retained crate file manifest exceeds its size bound")
        paths.append(path)
        records.append(record)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise RuntimeError("retained crate file paths are not exact")
    return records


def _validate_qualification_environment(
    value: object, *, expected_identity: str
) -> str:
    expected_keys = {
        "policy",
        "fresh_home",
        "fresh_cargo_home",
        "fresh_target_dir",
        "fresh_work_dir",
        "fresh_tmp_dir",
        "inherited_source_cache",
        "network_phase",
        "compile_phase",
        "host_network_isolation",
        "child_process_network_isolation",
        "host_filesystem_isolation",
        "system_executable_isolation",
        "credential_access_isolation",
        "caller_credential_environment",
        "cargo_config",
        "environment",
        "environment_allowlist",
        "stripped_injection_classes",
        "toolchain",
        "toolchain_pre_post_point_match",
        "target",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise RuntimeError("qualification environment receipt shape is invalid")
    if (
        value.get("policy") != "FRESH_HOME_CACHE_AND_CALLER_ENV_STRIPPED"
        or value.get("fresh_home") is not True
        or value.get("fresh_cargo_home") is not True
        or value.get("fresh_target_dir") is not True
        or value.get("fresh_work_dir") is not True
        or value.get("fresh_tmp_dir") is not True
        or value.get("inherited_source_cache") is not False
        or value.get("network_phase")
        != "PACKAGE_RESOLUTION_AND_EXACT_PATCH_LOCKED_FETCH"
        or value.get("compile_phase")
        != "CARGO_DEPENDENCY_ACCESS_OFFLINE_DURING_COMPILE_TEST"
        or value.get("host_network_isolation") != "NOT_CLAIMED"
        or value.get("child_process_network_isolation") != "NOT_CLAIMED"
        or value.get("host_filesystem_isolation") != "NOT_CLAIMED"
        or value.get("system_executable_isolation") != "NOT_CLAIMED"
        or value.get("credential_access_isolation") != "NOT_CLAIMED"
        or value.get("caller_credential_environment") != "STRIPPED_FOR_CARGO_AND_GIT"
        or value.get("toolchain_pre_post_point_match") is not True
        or value.get("cargo_config") != list(SECURE_CARGO_CONFIG)
    ):
        raise RuntimeError("qualification environment boundary drifted")
    environment = value.get("environment")
    required_environment = {
        "PATH": "SYSTEM_TOOL_DIRECTORIES_ONLY",
        "HOME": "FRESH_PRIVATE_EMPTY",
        "CARGO_HOME": "FRESH_PRIVATE_EMPTY",
        "CARGO_TARGET_DIR": "FRESH_PRIVATE_EMPTY",
        "CARGO_INCREMENTAL": "0",
        "CARGO_TERM_COLOR": "never",
        "RUSTC": "REVIEWED_INVOCATION",
        "RUSTDOC": "REVIEWED_INVOCATION",
        "PYO3_PYTHON": "REVIEWED_PYTHON_INVOCATION",
        "TMPDIR": "FRESH_PRIVATE_EMPTY",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "DISABLED_NULL_DEVICE",
        "GIT_CONFIG_SYSTEM": "DISABLED_NULL_DEVICE",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "NONINTERACTIVE_FALSE_PROGRAM",
        "GCM_INTERACTIVE": "never",
        "GIT_ALLOW_PROTOCOL": "https",
        "NCP_EXPECTED_BUILD_IDENTITY": expected_identity,
    }
    if not isinstance(environment, dict):
        raise RuntimeError("qualification environment map is malformed")
    allowed_keys = {*required_environment, "RUSTUP_HOME", "SOURCE_DATE_EPOCH"}
    if not set(environment).issubset(allowed_keys) or any(
        environment.get(key) != expected
        for key, expected in required_environment.items()
    ):
        raise RuntimeError("qualification environment allowlist drifted")
    if (
        "RUSTUP_HOME" in environment
        and environment.get("RUSTUP_HOME") != "EXISTING_TOOLCHAIN_ONLY"
    ):
        raise RuntimeError("qualification Rust toolchain boundary drifted")
    if (
        "SOURCE_DATE_EPOCH" in environment
        and re.fullmatch(r"[0-9]{1,20}", str(environment["SOURCE_DATE_EPOCH"])) is None
    ):
        raise RuntimeError("qualification source date is malformed")
    path_values = {
        "HOME",
        "CARGO_HOME",
        "CARGO_TARGET_DIR",
        "TMPDIR",
        "RUSTC",
        "RUSTDOC",
        "PYO3_PYTHON",
        "RUSTUP_HOME",
    }
    expected_allowlist = sorted(key for key in environment if key not in path_values)
    if value.get("environment_allowlist") != expected_allowlist:
        raise RuntimeError("qualification environment name receipt drifted")
    if value.get("stripped_injection_classes") != [
        "CARGO_CONFIG_AND_ALIAS",
        "CARGO_CREDENTIAL_AND_REGISTRY",
        "CARGO_ENCODED_RUSTFLAGS",
        "CALLER_COMPILER_AND_LINKER_ENV",
        "GIT_CONFIG_CREDENTIAL_PROXY_AND_REPLACE",
        "RUSTC_AND_RUSTDOC_FLAGS",
        "RUSTC_WRAPPERS",
    ]:
        raise RuntimeError("qualification injection-denial classes drifted")

    target = value.get("target")
    if not isinstance(target, str) or TARGET_TRIPLE.fullmatch(target) is None:
        raise RuntimeError("qualification target is malformed")
    toolchain = value.get("toolchain")
    hash_keys = {
        "cargo_invocation_sha256",
        "cargo_binary_sha256",
        "rustc_invocation_sha256",
        "rustc_binary_sha256",
        "rustdoc_invocation_sha256",
        "rustdoc_binary_sha256",
        "git_binary_sha256",
        "python_binary_sha256",
    }
    text_keys = {
        "cargo_version",
        "rustc_verbose",
        "rustdoc_version",
        "git_version",
        "python_version",
    }
    if not isinstance(toolchain, dict) or set(toolchain) != hash_keys | text_keys:
        raise RuntimeError("qualification toolchain receipt shape is invalid")
    if any(
        not isinstance(toolchain.get(key), str)
        or HEX_SHA256.fullmatch(str(toolchain[key])) is None
        for key in hash_keys
    ) or any(
        not isinstance(toolchain.get(key), str)
        or not str(toolchain[key])
        or len(str(toolchain[key]).encode("utf-8")) > 65_536
        for key in text_keys
    ):
        raise RuntimeError("qualification toolchain identity is malformed")
    if parse_rustc_host(str(toolchain["rustc_verbose"]).encode("utf-8")) != target:
        raise RuntimeError("qualification rustc target differs from its receipt")
    if parse_rustc_host(str(toolchain["rustdoc_version"]).encode("utf-8")) != target:
        raise RuntimeError("qualification rustdoc target differs from its receipt")
    cargo_hosts = re.findall(r"(?m)^host: ([^\r\n]+)$", str(toolchain["cargo_version"]))
    if cargo_hosts != [target]:
        raise RuntimeError("qualification Cargo target differs from its receipt")
    return target


def _validate_source_integrity(value: object, *, root: Path) -> None:
    if not isinstance(value, dict) or set(value) != {
        "scope",
        "verified_before_compile",
        "verified_after_compile",
        "verification_timing",
        "compiler_input_tracing",
        "read_only_source_mount",
        "verified_consumers",
        "zenoh_transport_upstream",
        "zenoh_transport_upstream_delta",
        "zenoh_transport_backport",
        "lz4_flex",
        "twox_hash",
    }:
        raise RuntimeError("conditioned source-integrity receipt shape is invalid")
    if (
        value.get("scope") != "POINT_IN_TIME_CONDITIONED_TRANSPORT_CLOSURE_SOURCE_BYTES"
        or value.get("verified_before_compile") is not True
        or value.get("verified_after_compile") is not True
        or value.get("verification_timing")
        != "POINT_IN_TIME_BEFORE_AND_AFTER_CARGO_COMPILE_PHASE"
        or value.get("compiler_input_tracing") != "NOT_RETAINED"
        or value.get("read_only_source_mount") != "NOT_CLAIMED"
        or value.get("verified_consumers") != list(ZENOH_CONDITIONAL_CRATES)
    ):
        raise RuntimeError("conditioned source-integrity boundary drifted")

    backport = value.get("zenoh_transport_backport")
    control = reviewed_backport_source()
    expected_backport = {
        "repository": ZENOH_BACKPORT_GIT,
        "revision": ZENOH_BACKPORT_REVISION,
        "tree": ZENOH_BACKPORT_TREE,
        "tracked_file_manifest_sha256": ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256,
        "tracked_files": control["tracked_files"],
        "cargo_marker": {
            "path": ".cargo-ok",
            "size_bytes": 0,
            "sha256": sha256_bytes(b""),
        },
    }
    if backport != expected_backport:
        raise RuntimeError("retained Zenoh backport source identity drifted")

    registry_sources = (
        (
            "zenoh_transport_upstream",
            "zenoh-transport",
            ZENOH_TRANSPORT_VERSION,
            ZENOH_TRANSPORT_REGISTRY_CHECKSUM,
            RETAINED_UPSTREAM_TRANSPORT_CRATE,
        ),
        (
            "lz4_flex",
            "lz4_flex",
            FIXED_LZ4_VERSION,
            FIXED_LZ4_CHECKSUM,
            RETAINED_LZ4_CRATE,
        ),
        (
            "twox_hash",
            "twox-hash",
            CONDITIONED_TWOX_VERSION,
            CONDITIONED_TWOX_CHECKSUM,
            RETAINED_TWOX_CRATE,
        ),
    )
    for receipt_key, package_name, version, checksum, retained_path in registry_sources:
        source = value.get(receipt_key)
        if not isinstance(source, dict) or set(source) != {
            "package",
            "version",
            "source",
            "crate_sha256",
            "retained_crate",
            "tracked_file_manifest_sha256",
            "tracked_files",
            "cargo_marker",
        }:
            raise RuntimeError(
                f"retained {package_name} source receipt shape is invalid"
            )
        if (
            source.get("package") != package_name
            or source.get("version") != version
            or source.get("source") != CRATES_IO_SOURCE
            or source.get("crate_sha256") != checksum
            or source.get("cargo_marker")
            != {
                "path": ".cargo-ok",
                "size_bytes": len(REGISTRY_CARGO_OK),
                "sha256": sha256_bytes(REGISTRY_CARGO_OK),
            }
        ):
            raise RuntimeError(f"retained {package_name} source identity drifted")
        retained_crate = _validate_artifact_record(
            source.get("retained_crate"),
            root=root,
            expected_path=retained_path,
            maximum_bytes=MAX_CRATE_ARCHIVE_BYTES,
        )
        if sha256(retained_crate) != checksum:
            raise RuntimeError(
                f"retained {package_name} crate differs from its Cargo checksum"
            )
        actual_records, _ = _streamed_crate_manifest(
            retained_crate, f"{package_name}-{version}"
        )
        recorded = _validate_crate_file_records(source.get("tracked_files"))
        if recorded != actual_records or source.get(
            "tracked_file_manifest_sha256"
        ) != canonical_json_sha256(actual_records):
            raise RuntimeError(
                f"retained {package_name} source manifest differs from its crate"
            )

    upstream = value.get("zenoh_transport_upstream")
    if not isinstance(upstream, dict):
        raise RuntimeError("retained upstream transport source is unavailable")
    derived_delta = verify_backport_upstream_delta(upstream, expected_backport)
    if value.get("zenoh_transport_upstream_delta") != derived_delta:
        raise RuntimeError("policy-bound Zenoh upstream delta receipt drifted")


def verify_retained_receipt(
    root: Path, *, version: str, revision: str
) -> dict[str, Any]:
    """Recompute artifact fields and validate the v3 local-process attestation."""

    if SOURCE_REVISION.fullmatch(revision) is None:
        raise RuntimeError("retained Rust receipt revision is malformed")
    expected_files = {
        "rust-package-receipt.json",
        *(f"{crate}-{version}.crate" for crate in CRATES),
        *RETAINED_CONDITIONED_LOCKS.values(),
        RETAINED_LZ4_CRATE,
        RETAINED_TWOX_CRATE,
        RETAINED_UPSTREAM_TRANSPORT_CRATE,
    }
    actual_directories, actual_files = _retained_tree_entries(root)
    if actual_directories != {"qualification"} or actual_files != expected_files:
        raise RuntimeError("retained Rust artifact tree is not exact")
    receipt = strict_json(root / "rust-package-receipt.json")
    assert_no_local_absolute_paths(receipt, context="Rust package receipt")
    if set(receipt) != {
        "schema",
        "source_revision",
        "embedded_build_identity",
        "candidate_version",
        "reproducibility_comparison",
        "qualification_environment",
        "verification_boundary",
        "zenoh_consumption",
        "archives",
    }:
        raise RuntimeError("retained Rust package receipt shape is invalid")
    if (
        receipt.get("schema") != RUST_PACKAGE_RECEIPT_SCHEMA
        or receipt.get("source_revision") != revision
        or receipt.get("embedded_build_identity") != revision
        or receipt.get("candidate_version") != version
        or receipt.get("reproducibility_comparison") != "PASS"
        or receipt.get("verification_boundary") != RUST_RECEIPT_VERIFICATION_BOUNDARY
    ):
        raise RuntimeError("retained Rust package receipt identity drifted")
    target = _validate_qualification_environment(
        receipt.get("qualification_environment"), expected_identity=revision
    )

    archives = receipt.get("archives")
    if not isinstance(archives, list) or len(archives) != len(CRATES):
        raise RuntimeError("retained Rust archive set is incomplete")
    archive_by_crate: dict[str, dict[str, object]] = {}
    archive_paths: dict[str, Path] = {}
    archive_file_records: dict[str, list[dict[str, object]]] = {}
    archive_controls: dict[str, dict[str, bytes]] = {}
    for crate, record in zip(CRATES, archives, strict=True):
        expected_path = f"{crate}-{version}.crate"
        if not isinstance(record, dict) or set(record) != {
            "crate",
            "path",
            "size_bytes",
            "sha256",
            "file_manifest_sha256",
        }:
            raise RuntimeError("retained Rust archive record shape is invalid")
        if record.get("crate") != crate:
            raise RuntimeError("retained Rust archive order or identity drifted")
        path = _validate_artifact_record(
            {key: record[key] for key in ("path", "size_bytes", "sha256")},
            root=root,
            expected_path=expected_path,
            maximum_bytes=MAX_CRATE_ARCHIVE_BYTES,
        )
        file_records, controls = _streamed_crate_manifest(
            path,
            f"{crate}-{version}",
            retain=ARCHIVE_IDENTITY_CONTROLS[crate],
        )
        if record.get("file_manifest_sha256") != canonical_json_sha256(file_records):
            raise RuntimeError("retained Rust archive file manifest digest drifted")
        manifest = load_toml_bytes(controls["Cargo.toml"], f"{crate} Cargo.toml")
        package = manifest.get("package")
        if (
            not isinstance(package, dict)
            or package.get("name") != crate
            or package.get("version") != version
        ):
            raise RuntimeError("retained Rust archive package identity drifted")
        if any(
            not controls[path_value] for path_value in ARCHIVE_IDENTITY_CONTROLS[crate]
        ):
            raise RuntimeError(
                "retained Rust archive contains an empty identity control"
            )
        if crate == "ncp-core":
            try:
                identity_source = controls["src/contract_identity.rs"].decode(
                    "utf-8", "strict"
                )
            except UnicodeError as error:
                raise RuntimeError(
                    "retained Rust build identity is not UTF-8"
                ) from error
            if (
                identity_source.count(f'    None => "{revision}",') != 1
                or '    None => "unreleased-worktree",' in identity_source
            ):
                raise RuntimeError("retained Rust archive build identity drifted")
        archive_by_crate[crate] = record
        archive_paths[crate] = path
        archive_file_records[crate] = file_records
        archive_controls[crate] = controls

    consumption = receipt.get("zenoh_consumption")
    expected_consumption_keys = {
        "status",
        "condition",
        "package_self_contained",
        "self_contained_distribution_gate",
        "decision",
        "release_authorized",
        "affected_archives",
        "archive_fallbacks",
        "conditioned_consumers",
        "source_integrity",
        "qualifying_root_patch",
    }
    if (
        not isinstance(consumption, dict)
        or set(consumption) != expected_consumption_keys
    ):
        raise RuntimeError("retained Zenoh consumption receipt shape is invalid")
    if (
        consumption.get("status") != "CONDITIONAL_PASS"
        or consumption.get("condition") != "EXACT_CONSUMING_ROOT_PATCH_REQUIRED"
        or consumption.get("package_self_contained") is not False
        or consumption.get("self_contained_distribution_gate") != "OPEN_FAIL_CLOSED"
        or consumption.get("decision") != "NO_GO"
        or consumption.get("release_authorized") is not False
        or consumption.get("affected_archives") != list(ZENOH_CONDITIONAL_CRATES)
    ):
        raise RuntimeError("retained Zenoh consumption boundary drifted")
    expected_patch = {
        "repository": ZENOH_BACKPORT_GIT,
        "revision": ZENOH_BACKPORT_REVISION,
        "tree": ZENOH_BACKPORT_TREE,
        "tracked_file_manifest_sha256": ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256,
        "upstream_zenoh_transport_checksum_sha256": (ZENOH_TRANSPORT_REGISTRY_CHECKSUM),
        "upstream_delta_status": "PASS_EXACT_ALLOWED_DELTA",
        "cargo_source": ZENOH_BACKPORT_SOURCE,
        "cargo_config": ZENOH_BACKPORT_CONFIG,
        "lz4_flex_version": FIXED_LZ4_VERSION,
        "lz4_flex_checksum_sha256": FIXED_LZ4_CHECKSUM,
        "twox_hash_version": CONDITIONED_TWOX_VERSION,
        "twox_hash_checksum_sha256": CONDITIONED_TWOX_CHECKSUM,
        "regression_steps": [
            "CARGO_TEST_SECURITY_BACKPORT_OFFLINE_PASS",
            "CARGO_TEST_LIB_TRANSPORT_COMPRESSION_OFFLINE_PASS",
        ],
        "cargo_verifies_git_signature": False,
    }
    if consumption.get("qualifying_root_patch") != expected_patch:
        raise RuntimeError("retained Zenoh consuming-root patch drifted")

    fallbacks = consumption.get("archive_fallbacks")
    consumers = consumption.get("conditioned_consumers")
    if (
        not isinstance(fallbacks, list)
        or not isinstance(consumers, list)
        or len(fallbacks) != len(ZENOH_CONDITIONAL_CRATES)
        or len(consumers) != len(ZENOH_CONDITIONAL_CRATES)
    ):
        raise RuntimeError("retained conditioned consumer set is incomplete")
    for crate, fallback, consumer in zip(
        ZENOH_CONDITIONAL_CRATES, fallbacks, consumers, strict=True
    ):
        file_records = archive_file_records[crate]
        controls = archive_controls[crate]
        recomputed_fallback = assert_unpatched_archive_fallback(
            crate,
            load_toml_bytes(controls["Cargo.toml"], f"{crate} archive Cargo.toml"),
            load_toml_bytes(controls["Cargo.lock"], f"{crate} archive Cargo.lock"),
            sha256_bytes(controls["Cargo.lock"]),
        )
        if not isinstance(fallback, dict):
            raise RuntimeError("retained archive fallback record is malformed")
        fallback_projection = fallback.get("resolution_projection")
        validate_resolution_projection(
            fallback_projection, crate=crate, target=target, conditioned=False
        )
        recomputed_fallback["resolution_observation"] = "EXECUTED_OBSERVED_VULNERABLE"
        recomputed_fallback["resolution_projection"] = fallback_projection
        if fallback != recomputed_fallback:
            raise RuntimeError("retained archive fallback differs from its crate bytes")

        if not isinstance(consumer, dict) or set(consumer) != {
            "crate",
            "target",
            "archive",
            "archive_fallback_cargo_lock_sha256",
            "conditioned_lock",
            "resolution_projection",
            "cargo_offline_mode_for_compile",
            "compile_steps",
        }:
            raise RuntimeError("retained conditioned consumer record shape is invalid")
        expected_archive = {
            "path": archive_by_crate[crate]["path"],
            "size_bytes": archive_by_crate[crate]["size_bytes"],
            "sha256": archive_by_crate[crate]["sha256"],
            "file_manifest_sha256": canonical_json_sha256(file_records),
        }
        expected_steps = (
            ["CARGO_TEST_PASS"]
            if crate == "ncp-zenoh"
            else ["CARGO_CHECK_PASS", "CARGO_IDENTITY_RUN_PASS"]
        )
        if (
            consumer.get("crate") != crate
            or consumer.get("target") != target
            or consumer.get("archive") != expected_archive
            or consumer.get("archive_fallback_cargo_lock_sha256")
            != recomputed_fallback["cargo_lock_sha256"]
            or consumer.get("cargo_offline_mode_for_compile") is not True
            or consumer.get("compile_steps") != expected_steps
        ):
            raise RuntimeError("retained conditioned consumer identity drifted")
        conditioned_path = _validate_artifact_record(
            consumer.get("conditioned_lock"),
            root=root,
            expected_path=RETAINED_CONDITIONED_LOCKS[crate],
            maximum_bytes=MAX_RETAINED_CONTROL_BYTES,
        )
        conditioned_lock = load_toml(conditioned_path)
        validate_conditioned_zenoh_lock(conditioned_lock)
        validate_conditioned_lock_transition(
            load_toml_bytes(controls["Cargo.lock"], f"{crate} archive Cargo.lock"),
            conditioned_lock,
        )
        validate_resolution_projection(
            consumer.get("resolution_projection"),
            crate=crate,
            target=target,
            conditioned=True,
        )

    _validate_source_integrity(consumption.get("source_integrity"), root=root)
    return receipt


def self_test() -> None:
    import copy
    import io

    artifact_claims = set(RUST_RECEIPT_VERIFICATION_BOUNDARY["artifact_derived"])
    local_claims = set(RUST_RECEIPT_VERIFICATION_BOUNDARY["local_process_attestations"])
    if (
        any("PINNED_FORK" in claim for claim in artifact_claims)
        or "POINT_IN_TIME_PINNED_FORK_SOURCE_AND_UPSTREAM_DELTA_VERIFICATION"
        not in local_claims
        or RUST_RECEIPT_VERIFICATION_BOUNDARY.get("pinned_fork_source_bytes")
        != "NOT_RETAINED"
    ):
        raise AssertionError(
            "fork-source receipt boundary overclaims retained evidence"
        )

    for hostile_path in (
        "/private/tmp/ncp",
        "C:\\Users\\builder\\ncp",
        "\\\\server\\share\\ncp",
        "\\\\?\\C:\\builder\\ncp",
        "\\rooted-on-current-drive",
        "file:///private/tmp/ncp",
    ):
        try:
            assert_no_local_absolute_paths(
                {"path": hostile_path}, context="path self-test"
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"local path passed receipt guard: {hostile_path!r}")

    control = reviewed_backport_source()
    upstream = control.get("upstream_crate")
    delta = upstream.get("allowed_delta") if isinstance(upstream, dict) else None
    if (
        not isinstance(delta, dict)
        or len(delta.get("added", [])) != 8
        or len(delta.get("modified", [])) != 3
        or delta.get("removed") != []
        or delta.get("unchanged_file_count") != 68
    ):
        raise AssertionError("reviewed Zenoh upstream delta control drifted")

    same_sources = {
        crate: {"tracked_file_manifest_sha256": "a" * 64}
        for crate in ZENOH_CONDITIONAL_CRATES
    }
    assert_consumer_source_point_match(same_sources, copy.deepcopy(same_sources))
    mutated_sources = copy.deepcopy(same_sources)
    mutated_sources[ZENOH_CONDITIONAL_CRATES[1]]["tracked_file_manifest_sha256"] = (
        "b" * 64
    )
    try:
        assert_consumer_source_point_match(same_sources, mutated_sources)
    except RuntimeError:
        pass
    else:
        raise AssertionError("second conditioned consumer source mutation passed")

    if parse_rustc_host(b"rustc 1.96.0\nhost: aarch64-apple-darwin\n") != (
        "aarch64-apple-darwin"
    ):
        raise AssertionError("rustc host parser lost the exact target")
    for hostile_host in (b"host: \n", b"host: bad/target\n", b"host: a\nhost: b\n"):
        try:
            parse_rustc_host(hostile_host)
        except RuntimeError:
            pass
        else:
            raise AssertionError("malformed rustc host output passed validation")

    with tempfile.TemporaryDirectory(prefix="ncp-qualification-selftest-") as tmp:
        qualification = create_qualification(
            Path(tmp),
            os.environ.copy(),
            expected_identity="unreleased-worktree",
        )
        if (
            qualification.env.get("GIT_CONFIG_GLOBAL") != os.devnull
            or qualification.env.get("GIT_CONFIG_SYSTEM") != os.devnull
            or qualification.env.get("GIT_ASKPASS") != "/usr/bin/false"
        ):
            raise AssertionError("live qualification Git controls are not executable")
        retained_environment = qualification.toolchain_receipt.get("environment")
        if not isinstance(retained_environment, dict) or (
            retained_environment.get("GIT_CONFIG_GLOBAL") != "DISABLED_NULL_DEVICE"
            or retained_environment.get("GIT_CONFIG_SYSTEM") != "DISABLED_NULL_DEVICE"
            or retained_environment.get("GIT_ASKPASS") != "NONINTERACTIVE_FALSE_PROGRAM"
        ):
            raise AssertionError("qualification receipt leaked executable paths")
        qualification.toolchain_receipt["target"] = rustc_host(
            qualification.env, qualification.rustc
        )
        verify_toolchain_point_match(qualification)
        _validate_qualification_environment(
            qualification.toolchain_receipt,
            expected_identity="unreleased-worktree",
        )

    with tempfile.TemporaryDirectory(prefix="ncp-package-path-selftest-") as tmp:
        root = Path(tmp)
        real_parent = root / "real source"
        real_crate = real_parent / "ncp-core"
        real_crate.mkdir(parents=True)
        detour = real_parent / "detour"
        detour.mkdir()
        aliased_paths = [detour / ".." / "ncp-core"]
        alias = root / "source-alias"
        try:
            alias.symlink_to(real_parent, target_is_directory=True)
        except OSError:
            pass
        else:
            aliased_paths.append(alias / "ncp-core")
        for aliased_path in aliased_paths:
            args = cargo_patch_args(("ncp-core",), {"ncp-core": aliased_path})
            if args[:1] != ["--config"] or len(args) != 2:
                raise AssertionError("Cargo patch arguments have an unexpected shape")
            prefix = "patch.crates-io.ncp-core.path="
            if not args[1].startswith(prefix):
                raise AssertionError(
                    "Cargo patch argument lost its exact dependency key"
                )
            encoded = args[1][len(prefix) :]
            if json.loads(encoded) != str(real_crate.resolve(strict=True)):
                raise AssertionError("Cargo patch path retained a filesystem alias")
        try:
            cargo_patch_args(("ncp-core",), {"ncp-core": root / "missing" / "ncp-core"})
        except RuntimeError:
            pass
        else:
            raise AssertionError("missing Cargo patch path passed canonicalization")

    with tempfile.TemporaryDirectory(prefix="ncp-package-tar-selftest-") as tmp:
        root = Path(tmp)
        prefix = "ncp-test-1.0.0"

        compressed_bomb = io.BytesIO()
        with gzip.GzipFile(
            fileobj=compressed_bomb,
            mode="wb",
            mtime=0,
        ) as compressed:
            compressed.write(b"\0" * 4096)
        compressed_bomb.seek(0)
        bounded_output = io.BytesIO()
        try:
            _stage_bounded_gzip(
                compressed_bomb,
                bounded_output,
                maximum_expanded_bytes=1024,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("gzip expansion bomb passed its pre-parser limit")
        if len(bounded_output.getvalue()) > 1024:
            raise AssertionError("gzip expansion limit wrote bytes past its boundary")

        guarded_reader = _BoundedTarReader(
            io.BytesIO(b"metadata"),
            maximum_read_bytes=4,
        )
        try:
            guarded_reader.read(5)
        except RuntimeError:
            pass
        else:
            raise AssertionError("oversized tar metadata read passed its parser guard")

        @contextmanager
        def canonical_tar_writer(
            path: Path,
            *,
            archive_format: int = tarfile.PAX_FORMAT,
            pax_headers: dict[str, str] | None = None,
        ) -> Iterator[tarfile.TarFile]:
            raw = io.BytesIO()
            with tarfile.open(
                fileobj=raw,
                mode="w:",
                format=archive_format,
                pax_headers=pax_headers,
            ) as package:
                yield package
                member_end = package.offset
            payload = raw.getvalue()[:member_end] + b"\0" * TAR_TERMINATOR_BYTES
            path.write_bytes(gzip.compress(payload, mtime=0))

        def write_tar(
            path: Path,
            members: list[tuple[str, bytes | None, bytes, str]],
        ) -> None:
            with canonical_tar_writer(path) as package:
                for name, body, member_type, link_name in members:
                    info = tarfile.TarInfo(name)
                    info.type = member_type
                    info.mode = 0o644
                    info.linkname = link_name
                    if body is None:
                        info.size = 0
                        package.addfile(info)
                    else:
                        info.size = len(body)
                        package.addfile(info, io.BytesIO(body))

        buffered_read_regression_size = CRATE_STREAM_CHUNK_BYTES * 2 + 17
        buffered_read_regression_body = (
            b"ncp-bounded-tar-member-read\n"
            * (
                buffered_read_regression_size
                // len(b"ncp-bounded-tar-member-read\n")
                + 1
            )
        )[:buffered_read_regression_size]
        good = root / "good.crate"
        write_tar(
            good,
            [
                (
                    f"{prefix}/Cargo.toml",
                    b"[package]\nname='ncp-test'\n",
                    tarfile.REGTYPE,
                    "",
                ),
                (f"{prefix}/src/lib.rs", b"pub fn test() {}\n", tarfile.REGTYPE, ""),
                (
                    f"{prefix}/src/buffered-read.bin",
                    buffered_read_regression_body,
                    tarfile.REGTYPE,
                    "",
                ),
            ],
        )
        records, _ = _streamed_crate_manifest(good, prefix)
        if [record["path"] for record in records] != [
            "Cargo.toml",
            "src/buffered-read.bin",
            "src/lib.rs",
        ]:
            raise AssertionError("safe crate manifest lost an exact file")
        extraction_parent = root / "good-extraction"
        extraction_parent.mkdir()
        extracted = extract_archive(good, extraction_parent, prefix)
        if (extracted / "src/lib.rs").read_bytes() != b"pub fn test() {}\n":
            raise AssertionError("safe crate extraction changed file bytes")
        if (
            extracted / "src/buffered-read.bin"
        ).read_bytes() != buffered_read_regression_body:
            raise AssertionError("bounded crate streaming changed a large member")

        second = root / "second-valid.crate"
        write_tar(
            second,
            [(f"{prefix}/second.txt", b"hidden", tarfile.REGTYPE, "")],
        )
        hidden_unsafe = root / "second-unsafe.crate"
        write_tar(
            hidden_unsafe,
            [(f"{prefix}/../escape", b"hidden", tarfile.REGTYPE, "")],
        )
        good_gzip = good.read_bytes()
        good_tar = gzip.decompress(good_gzip)
        second_tar = gzip.decompress(second.read_bytes())
        unsafe_tar = gzip.decompress(hidden_unsafe.read_bytes())
        boundary_cases = {
            "two-tars-one-gzip": gzip.compress(good_tar + second_tar, mtime=0),
            "two-concatenated-gzip-members": good_gzip + second.read_bytes(),
            "unsafe-path-in-hidden-second-tar": gzip.compress(
                good_tar + unsafe_tar,
                mtime=0,
            ),
            "trailing-junk-inside-gzip": gzip.compress(good_tar + b"junk", mtime=0),
            "trailing-junk-after-gzip": good_gzip + b"junk",
            "trailing-zero-record": gzip.compress(
                good_tar + b"\0" * TAR_RECORD_BYTES,
                mtime=0,
            ),
            "truncated-gzip-member": good_gzip[:-8],
            "truncated-tar-terminator": gzip.compress(good_tar[:-512], mtime=0),
        }
        for label, encoded in boundary_cases.items():
            archive = root / f"boundary-{label}.crate"
            archive.write_bytes(encoded)
            try:
                _streamed_crate_manifest(archive, prefix)
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"{label} passed streamed validation")
            destination = root / f"boundary-extraction-{label}"
            destination.mkdir()
            try:
                extract_archive(archive, destination, prefix)
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"{label} passed extraction validation")

        oversized_raw = root / "oversized-raw.crate"
        with oversized_raw.open("wb") as output:
            output.truncate(MAX_CRATE_ARCHIVE_BYTES + 1)
        try:
            _streamed_crate_manifest(oversized_raw, prefix)
        except RuntimeError:
            pass
        else:
            raise AssertionError("oversized compressed crate passed its raw-byte limit")

        pax_bomb = root / "pax-metadata-bomb.crate"
        with canonical_tar_writer(pax_bomb) as package:
            info = tarfile.TarInfo(f"{prefix}/pax")
            info.pax_headers = {
                "comment": "x" * (MAX_CRATE_TAR_METADATA_ENTRY_BYTES + 1)
            }
            info.size = 0
            package.addfile(info)

        pax_total_bomb = root / "pax-total-metadata-bomb.crate"
        pax_comment_bytes = MAX_CRATE_TAR_METADATA_ENTRY_BYTES // 2
        pax_member_count = MAX_CRATE_TAR_METADATA_BYTES // pax_comment_bytes + 2
        with canonical_tar_writer(
            pax_total_bomb,
        ) as package:
            for index in range(pax_member_count):
                info = tarfile.TarInfo(f"{prefix}/pax-{index}")
                info.pax_headers = {"comment": "x" * pax_comment_bytes}
                info.size = 0
                package.addfile(info)

        pax_sparse = root / "pax-sparse.crate"
        with canonical_tar_writer(pax_sparse) as package:
            info = tarfile.TarInfo(f"{prefix}/pax-sparse")
            info.pax_headers = {
                "GNU.sparse.map": "0,1",
                "GNU.sparse.size": "1",
            }
            info.size = 1
            package.addfile(info, io.BytesIO(b"x"))

        pax_global = root / "pax-global.crate"
        with canonical_tar_writer(
            pax_global,
            pax_headers={"comment": "global metadata must not amplify"},
        ) as package:
            info = tarfile.TarInfo(f"{prefix}/global-pax")
            info.size = 0
            package.addfile(info)

        gnu_bomb = root / "gnu-longname-bomb.crate"
        with canonical_tar_writer(
            gnu_bomb,
            archive_format=tarfile.GNU_FORMAT,
        ) as package:
            info = tarfile.TarInfo(
                f"{prefix}/" + "x" * (MAX_CRATE_TAR_METADATA_ENTRY_BYTES + 1)
            )
            info.size = 0
            package.addfile(info)

        for label, archive in (
            ("PAX extension metadata", pax_bomb),
            ("PAX cumulative metadata", pax_total_bomb),
            ("PAX sparse metadata", pax_sparse),
            ("global PAX metadata", pax_global),
            ("GNU long-name metadata", gnu_bomb),
        ):
            try:
                _streamed_crate_manifest(archive, prefix)
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"{label} bomb passed its pre-parser limit")

        hostile_members = {
            "path traversal": [(f"{prefix}/../escape", b"bad", tarfile.REGTYPE, "")],
            "duplicate path": [
                (f"{prefix}/same", b"one", tarfile.REGTYPE, ""),
                (f"{prefix}/same", b"two", tarfile.REGTYPE, ""),
            ],
            "symbolic link": [(f"{prefix}/link", None, tarfile.SYMTYPE, "../escape")],
            "hard link": [
                (f"{prefix}/link", None, tarfile.LNKTYPE, f"{prefix}/target")
            ],
            "special entry": [(f"{prefix}/device", None, tarfile.CHRTYPE, "")],
        }
        for index, (label, members) in enumerate(hostile_members.items()):
            archive = root / f"hostile-{index}.crate"
            write_tar(archive, members)
            try:
                _streamed_crate_manifest(archive, prefix)
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"{label} crate passed streamed validation")
            destination = root / f"hostile-extraction-{index}"
            destination.mkdir()
            try:
                extract_archive(archive, destination, prefix)
            except RuntimeError:
                pass
            else:
                raise AssertionError(f"{label} crate passed extraction validation")

        archive_alias = root / "archive-alias.crate"
        try:
            archive_alias.symlink_to(good)
        except OSError:
            pass
        else:
            try:
                _streamed_crate_manifest(archive_alias, prefix)
            except RuntimeError:
                pass
            else:
                raise AssertionError("linked crate archive passed validation")

    exact_patch = zenoh_backport_patch_args()
    hostile_patches = {
        "absent": [],
        "wrong repository": [
            "--config",
            'patch.crates-io.zenoh-transport.git="https://example.invalid/fork"',
            "--config",
            (f'patch.crates-io.zenoh-transport.rev="{ZENOH_BACKPORT_REVISION}"'),
        ],
        "wrong revision": [
            "--config",
            f'patch.crates-io.zenoh-transport.git="{ZENOH_BACKPORT_GIT}"',
            "--config",
            f'patch.crates-io.zenoh-transport.rev="{"0" * 40}"',
        ],
    }
    validate_zenoh_backport_patch_args(exact_patch)
    for label, hostile in hostile_patches.items():
        try:
            validate_zenoh_backport_patch_args(hostile)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{label} Zenoh root patch passed validation")

    fallback_lock: dict[str, object] = {
        "package": [
            {
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": ZENOH_TRANSPORT_REGISTRY_CHECKSUM,
                "dependencies": ["lz4_flex"],
            },
            {
                "name": "lz4_flex",
                "version": VULNERABLE_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": VULNERABLE_LZ4_CHECKSUM,
                "dependencies": ["twox-hash"],
            },
            {
                "name": "twox-hash",
                "version": FALLBACK_TWOX_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": FALLBACK_TWOX_CHECKSUM,
                "dependencies": ["cfg-if", "static_assertions"],
            },
        ]
    }
    fallback = assert_unpatched_archive_fallback(
        "ncp-zenoh", {}, fallback_lock, "a" * 64
    )
    if fallback.get("advisory") != "RUSTSEC-2026-0041":
        raise AssertionError("archive fallback evidence lost the advisory identity")
    omitted = copy.deepcopy(fallback_lock)
    omitted["package"] = omitted["package"][:1]
    try:
        assert_unpatched_archive_fallback("ncp-zenoh", {}, omitted, "a" * 64)
    except RuntimeError:
        pass
    else:
        raise AssertionError("archive dependency omission passed validation")

    conditioned_lock: dict[str, object] = {
        "package": [
            {
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": ZENOH_BACKPORT_SOURCE,
                "dependencies": ["lz4_flex"],
            },
            {
                "name": "lz4_flex",
                "version": FIXED_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": FIXED_LZ4_CHECKSUM,
                "dependencies": ["twox-hash"],
            },
            {
                "name": "twox-hash",
                "version": CONDITIONED_TWOX_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": CONDITIONED_TWOX_CHECKSUM,
            },
        ]
    }
    validate_conditioned_zenoh_lock(conditioned_lock)
    validate_conditioned_lock_transition(fallback_lock, conditioned_lock)
    hostile_transitions: dict[str, dict[str, object]] = {}
    transport_dependency_drift = copy.deepcopy(conditioned_lock)
    transport_dependency_drift["package"][0]["dependencies"].append("cfg-if")
    hostile_transitions["transport dependency drift"] = transport_dependency_drift
    lz4_dependency_drift = copy.deepcopy(conditioned_lock)
    lz4_dependency_drift["package"][1]["dependencies"].append("cfg-if")
    hostile_transitions["lz4 dependency drift"] = lz4_dependency_drift
    twox_dependency_drift = copy.deepcopy(conditioned_lock)
    twox_dependency_drift["package"][2]["dependencies"] = ["cfg-if"]
    hostile_transitions["twox dependency drift"] = twox_dependency_drift
    for label, hostile in hostile_transitions.items():
        validate_conditioned_zenoh_lock(hostile)
        try:
            validate_conditioned_lock_transition(fallback_lock, hostile)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{label} passed exact transition validation")

    hostile_locks: dict[str, dict[str, object]] = {}
    registry_fallback = copy.deepcopy(conditioned_lock)
    registry_fallback["package"][0]["source"] = CRATES_IO_SOURCE
    registry_fallback["package"][0]["checksum"] = ZENOH_TRANSPORT_REGISTRY_CHECKSUM
    hostile_locks["registry fallback"] = registry_fallback
    wrong_source_revision = copy.deepcopy(conditioned_lock)
    wrong_source_revision["package"][0]["source"] = (
        f"git+{ZENOH_BACKPORT_GIT}?rev={'0' * 40}#{'0' * 40}"
    )
    hostile_locks["wrong source revision"] = wrong_source_revision
    vulnerable_lock = copy.deepcopy(conditioned_lock)
    vulnerable_lock["package"][1]["version"] = VULNERABLE_LZ4_VERSION
    vulnerable_lock["package"][1]["checksum"] = VULNERABLE_LZ4_CHECKSUM
    hostile_locks["vulnerable dependency"] = vulnerable_lock
    wrong_checksum = copy.deepcopy(conditioned_lock)
    wrong_checksum["package"][1]["checksum"] = "0" * 64
    hostile_locks["wrong fixed checksum"] = wrong_checksum
    missing_edge = copy.deepcopy(conditioned_lock)
    missing_edge["package"][0]["dependencies"] = []
    hostile_locks["missing dependency edge"] = missing_edge
    for label, hostile in hostile_locks.items():
        try:
            validate_conditioned_zenoh_lock(hostile)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{label} conditioned lock passed validation")

    transport_id = ZENOH_BACKPORT_SOURCE
    lz4_id = f"{CRATES_IO_SOURCE}#lz4_flex@{FIXED_LZ4_VERSION}"
    twox_id = f"{CRATES_IO_SOURCE}#twox-hash@{CONDITIONED_TWOX_VERSION}"
    zenoh_id = f"{CRATES_IO_SOURCE}#zenoh@{ZENOH_TRANSPORT_VERSION}"
    metadata: dict[str, object] = {
        "packages": [
            {
                "id": transport_id,
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": ZENOH_BACKPORT_SOURCE,
                "rust_version": "1.81.0",
            },
            {
                "id": lz4_id,
                "name": "lz4_flex",
                "version": FIXED_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
            },
            {
                "id": zenoh_id,
                "name": "zenoh",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": CRATES_IO_SOURCE,
            },
            {
                "id": twox_id,
                "name": "twox-hash",
                "version": CONDITIONED_TWOX_VERSION,
                "source": CRATES_IO_SOURCE,
            },
        ],
        "resolve": {
            "nodes": [
                {
                    "id": transport_id,
                    "features": ["transport_tcp"],
                    "deps": [{"pkg": lz4_id}],
                },
                {"id": zenoh_id, "features": ["transport_tcp"], "deps": []},
                {
                    "id": lz4_id,
                    "features": ["safe-encode"],
                    "deps": [{"pkg": twox_id}],
                },
                {"id": twox_id, "features": [], "deps": []},
            ]
        },
    }
    validate_conditioned_zenoh_metadata(
        metadata, crate="ncp-zenoh", target="aarch64-apple-darwin"
    )
    hostile_metadata = copy.deepcopy(metadata)
    hostile_metadata["packages"][0]["source"] = CRATES_IO_SOURCE
    try:
        validate_conditioned_zenoh_metadata(
            hostile_metadata, crate="ncp-zenoh", target="aarch64-apple-darwin"
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("registry metadata fallback passed validation")
    hostile_metadata = copy.deepcopy(metadata)
    hostile_metadata["resolve"]["nodes"][0]["features"].append("transport_compression")
    try:
        validate_conditioned_zenoh_metadata(
            hostile_metadata, crate="ncp-zenoh", target="aarch64-apple-darwin"
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("forbidden conditioned feature passed validation")

    fallback_transport_id = (
        f"{CRATES_IO_SOURCE}#zenoh-transport@{ZENOH_TRANSPORT_VERSION}"
    )
    fallback_lz4_id = f"{CRATES_IO_SOURCE}#lz4_flex@{VULNERABLE_LZ4_VERSION}"
    fallback_twox_id = f"{CRATES_IO_SOURCE}#twox-hash@{FALLBACK_TWOX_VERSION}"
    fallback_zenoh_id = f"{CRATES_IO_SOURCE}#zenoh@{ZENOH_TRANSPORT_VERSION}"
    fallback_metadata: dict[str, object] = {
        "packages": [
            {
                "id": fallback_transport_id,
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": CRATES_IO_SOURCE,
            },
            {
                "id": fallback_lz4_id,
                "name": "lz4_flex",
                "version": VULNERABLE_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
            },
            {
                "id": fallback_zenoh_id,
                "name": "zenoh",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": CRATES_IO_SOURCE,
            },
            {
                "id": fallback_twox_id,
                "name": "twox-hash",
                "version": FALLBACK_TWOX_VERSION,
                "source": CRATES_IO_SOURCE,
            },
        ],
        "resolve": {
            "nodes": [
                {
                    "id": fallback_transport_id,
                    "features": ["transport_tcp"],
                    "deps": [{"pkg": fallback_lz4_id}],
                },
                {
                    "id": fallback_lz4_id,
                    "features": [],
                    "deps": [{"pkg": fallback_twox_id}],
                },
                {"id": fallback_twox_id, "features": [], "deps": []},
                {
                    "id": fallback_zenoh_id,
                    "features": ["transport_tcp"],
                    "deps": [],
                },
            ]
        },
    }
    validate_unpatched_zenoh_metadata(
        fallback_metadata, crate="ncp-zenoh", target="aarch64-apple-darwin"
    )
    hostile_fallback_metadata = copy.deepcopy(fallback_metadata)
    hostile_fallback_metadata["resolve"]["nodes"][0]["deps"] = []
    try:
        validate_unpatched_zenoh_metadata(
            hostile_fallback_metadata,
            crate="ncp-zenoh",
            target="aarch64-apple-darwin",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "incomplete archive fallback observation passed validation"
        )


def extract_archive(archive: Path, destination: Path, expected_prefix: str) -> Path:
    """Extract a validated crate without delegating path handling to tarfile."""

    outer_digest = sha256(archive)
    records, _ = _streamed_crate_manifest(archive, expected_prefix)
    expected = {str(record["path"]): record for record in records}
    try:
        destination_mode = destination.lstat().st_mode
        destination_resolved = destination.resolve(strict=True)
    except OSError as error:
        raise RuntimeError("crate extraction destination is unavailable") from error
    if stat.S_ISLNK(destination_mode) or not stat.S_ISDIR(destination_mode):
        raise RuntimeError("crate extraction destination is linked or special")

    archive_root = destination / expected_prefix
    try:
        archive_root.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise RuntimeError("crate extraction root cannot be inspected") from error
    else:
        raise RuntimeError("crate extraction root already exists")
    archive_root.mkdir(mode=0o755)

    with _open_bounded_crate_tar(archive) as package:
        seen: set[str] = set()
        member_count = 0
        for member in package:
            member_count += 1
            if member_count > MAX_CRATE_MEMBERS:
                raise RuntimeError(
                    f"crate archive has too many members: {archive.name}"
                )
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "." in path.parts
                or not path.parts
                or path.parts[0] != expected_prefix
                or "\\" in member.name
                or len(member.name.encode("utf-8")) > 512
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in member.name
                )
                or path.as_posix() != member.name.rstrip("/")
            ):
                raise RuntimeError(f"unsafe path in {archive.name}: {member.name}")
            canonical = path.as_posix()
            if canonical in seen:
                raise RuntimeError(f"duplicate path in {archive.name}: {member.name}")
            seen.add(canonical)
            if member.issym() or member.islnk():
                raise RuntimeError(f"link in {archive.name}: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(
                    f"special archive entry in {archive.name}: {member.name}"
                )
            if member.isdir():
                continue

            relative = path.relative_to(expected_prefix).as_posix()
            record = expected.pop(relative, None)
            if record is None or (
                member.size != record["size_bytes"]
                or f"{member.mode & 0o777:04o}" != record["mode"]
            ):
                raise RuntimeError(
                    f"crate member identity changed during extraction: {member.name}"
                )
            target = archive_root / relative
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            current = archive_root
            for part in Path(relative).parts[:-1]:
                current = current / part
                mode = current.lstat().st_mode
                if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                    raise RuntimeError("crate extraction created a directory alias")
            if target.parent.resolve(strict=True) != (
                destination_resolved / expected_prefix / Path(relative).parent
            ):
                raise RuntimeError("crate extraction target escaped its root")
            digest = hashlib.sha256()
            observed = 0
            try:
                with target.open("xb") as output:
                    for chunk in _iter_bounded_tar_member(package, member):
                        observed += len(chunk)
                        if observed > member.size:
                            raise RuntimeError(
                                f"member size overflow in {archive.name}: {member.name}"
                            )
                        digest.update(chunk)
                        output.write(chunk)
                target.chmod(member.mode & 0o777)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            if observed != member.size or digest.hexdigest() != record["sha256"]:
                raise RuntimeError(
                    f"crate member bytes changed during extraction: {member.name}"
                )
    if expected or sha256(archive) != outer_digest:
        raise RuntimeError("crate archive changed during extraction")
    return archive_root


def assert_archive_surface(crate: str, source: Path, archive_root: Path) -> None:
    required = {
        Path("Cargo.toml"),
        Path("README.md"),
        Path("LICENSE-MIT"),
        Path("LICENSE-APACHE"),
    }
    testdata = source / "testdata"
    if testdata.is_dir():
        required.update(
            path.relative_to(source) for path in testdata.rglob("*") if path.is_file()
        )

    missing = sorted(path for path in required if not (archive_root / path).is_file())
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"{crate} archive is missing required files: {formatted}")

    for license_name in ("LICENSE-MIT", "LICENSE-APACHE"):
        if (archive_root / license_name).read_bytes() != (
            ROOT / license_name
        ).read_bytes():
            raise RuntimeError(f"{crate} archive carries a stale {license_name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "request a network-free run; rejected because qualification starts "
            "with an empty Cargo home and never restores an inherited cache"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "atomically retain verified crate archives, conditioned locks, fixed "
            "registry source crates, and a v3 evidence receipt in this new directory; "
            "also rebuild and compare every NCP archive"
        ),
    )
    parser.add_argument(
        "--source-revision",
        help="exact 40-hex source revision bound into an --output-dir receipt",
    )
    parser.add_argument(
        "--verify-retained-receipt",
        type=Path,
        help="verify one retained Rust product directory and emit its receipt JSON",
    )
    parser.add_argument("--candidate-version")
    parser.add_argument("--receipt-revision")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.flags.safe_path:
        parser.error("Rust package policy must run under isolated Python (-I)")
    if args.verify_retained_receipt is not None:
        if (
            args.self_test
            or args.offline
            or args.output_dir is not None
            or args.source_revision is not None
            or not isinstance(args.candidate_version, str)
            or not args.candidate_version
            or SOURCE_REVISION.fullmatch(args.receipt_revision or "") is None
        ):
            parser.error(
                "--verify-retained-receipt requires --candidate-version and "
                "--receipt-revision and cannot be combined with build modes"
            )
        receipt = verify_retained_receipt(
            args.verify_retained_receipt.resolve(),
            version=args.candidate_version,
            revision=args.receipt_revision or "",
        )
        sys.stdout.write(
            json.dumps(
                receipt, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            )
            + "\n"
        )
        return 0
    if args.candidate_version is not None or args.receipt_revision is not None:
        parser.error(
            "--candidate-version and --receipt-revision require "
            "--verify-retained-receipt"
        )
    if args.self_test:
        if (
            args.offline
            or args.output_dir is not None
            or args.source_revision is not None
        ):
            parser.error("--self-test cannot be combined with package build options")
        self_test()
        print("Rust package archive checker self-test passed.")
        return 0
    if args.offline:
        parser.error(
            "--offline cannot populate the mandatory fresh Cargo home; the default "
            "run performs an exact network resolution/fetch phase and then compiles "
            "with Cargo offline mode"
        )
    output = args.output_dir.resolve() if args.output_dir is not None else None
    if output is None and args.source_revision is not None:
        parser.error("--source-revision requires --output-dir")
    if output is not None:
        if not SOURCE_REVISION.fullmatch(args.source_revision or ""):
            parser.error(
                "--output-dir requires --source-revision with exactly 40 lowercase hex"
            )
        if output.exists():
            parser.error(f"--output-dir must not already exist: {output}")
        if (ROOT / ".git").exists():
            parser.error(
                "retained archives must be built from build_candidate_dossier.py's "
                "Git archive, not a mutable worktree"
            )
        if os.environ.get("NCP_ARCHIVED_SOURCE_REVISION") != args.source_revision:
            parser.error(
                "retained archive source revision is not bound by the candidate builder"
            )
        output.parent.mkdir(parents=True, exist_ok=True)

    run([sys.executable, "-I", "scripts/sync_rust_package_testdata.py"])
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    version = workspace["workspace"]["package"]["version"]

    with tempfile.TemporaryDirectory(prefix="ncp-package-selftest-") as tmp:
        temp = Path(tmp).resolve(strict=True)
        package_target = temp / "package-target"
        extracted_parent = temp / "extracted"
        extracted_parent.mkdir()
        package_root = ROOT
        package_snapshot: dict[str, tuple[int, int, str]] | None = None
        if output is not None:
            package_root = temp / "package-source"
            copy_regular_tree(ROOT, package_root)
            inject_packaged_source_identity(package_root, args.source_revision or "")
            package_snapshot = tree_snapshot(package_root)
        expected_identity = args.source_revision or "unreleased-worktree"
        qualification = create_qualification(
            temp,
            os.environ.copy(),
            expected_identity=expected_identity,
        )
        source_paths = {crate: package_root / crate for crate in CRATES}
        extracted_paths: dict[str, Path] = {}
        archives: dict[str, Path] = {}
        archive_file_manifest_digests: dict[str, str] = {}

        for crate in CRATES:
            command = cargo_command(
                qualification,
                "package",
                "--manifest-path",
                str(package_root / "Cargo.toml"),
                "--package",
                crate,
                "--allow-dirty",
                "--locked",
                "--no-verify",
                "--target-dir",
                str(package_target),
                *cargo_patch_args(LOCAL_DEPENDENCIES[crate], source_paths),
            )
            run(command, env=qualification.env, cwd=qualification.work)

            archive = package_target / "package" / f"{crate}-{version}.crate"
            if not archive.is_file():
                raise RuntimeError(f"Cargo did not produce {archive}")
            archives[crate] = archive
            prefix = f"{crate}-{version}"
            archive_records, _ = _streamed_crate_manifest(archive, prefix)
            archive_file_manifest_digests[crate] = canonical_json_sha256(
                archive_records
            )
            extracted = extract_archive(archive, extracted_parent, prefix)
            assert_archive_surface(crate, source_paths[crate], extracted)
            extracted_paths[crate] = extracted

        # Keep build artifacts under the same temporary tree as the extraction.
        # `CARGO_MANIFEST_DIR` is compiled into several fixture paths; reusing a
        # target directory across differently named temp extractions can otherwise
        # execute a stale test binary that points at an already-deleted directory.
        host_target = rustc_host(qualification.env, qualification.rustc)
        qualification.toolchain_receipt["target"] = host_target
        consumer_patch_args: dict[str, list[str]] = {}
        archive_fallbacks: list[dict[str, object]] = []
        conditioned_consumers: list[dict[str, object]] = []
        conditioned_locks: dict[str, bytes] = {}
        conditioned_metadata: dict[
            str, tuple[dict[str, object], dict[str, object]]
        ] = {}
        pre_compile_sources: dict[str, dict[str, object]] = {}
        for crate in ZENOH_CONDITIONAL_CRATES:
            (
                patch_args,
                fallback,
                consumer,
                conditioned_lock,
                source_integrity,
                metadata_pair,
            ) = condition_zenoh_archive(
                crate,
                extracted_paths,
                archives[crate],
                target=host_target,
                qualification=qualification,
                version=version,
            )
            consumer_patch_args[crate] = patch_args
            archive_fallbacks.append(fallback)
            conditioned_consumers.append(consumer)
            conditioned_locks[crate] = conditioned_lock
            conditioned_metadata[crate] = metadata_pair
            pre_compile_sources[crate] = source_integrity
        assert_consumer_source_point_match(
            pre_compile_sources,
            pre_compile_sources,
        )
        backport_checkouts = {
            backport_checkout_path(metadata_pair[1], qualification)
            for metadata_pair in conditioned_metadata.values()
        }
        if len(backport_checkouts) != 1:
            raise RuntimeError(
                "conditioned consumers used different backport checkouts"
            )
        backport_checkout = next(iter(backport_checkouts))
        fetch_locked_archive(
            backport_checkout / "Cargo.toml",
            [],
            target=host_target,
            qualification=qualification,
        )

        for crate in CRATES:
            if crate in ZENOH_CONDITIONAL_CRATES:
                continue
            fetch_locked_archive(
                extracted_paths[crate] / "Cargo.toml",
                cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths),
                target=host_target,
                qualification=qualification,
            )

        extracted_snapshots = {
            crate: tree_snapshot(path) for crate, path in extracted_paths.items()
        }
        consumer_by_crate = {
            str(record["crate"]): record for record in conditioned_consumers
        }
        backport_regression_steps = [
            "CARGO_TEST_SECURITY_BACKPORT_OFFLINE_PASS",
            "CARGO_TEST_LIB_TRANSPORT_COMPRESSION_OFFLINE_PASS",
        ]
        for arguments in (
            ("--test", "security_backport"),
            ("--lib",),
        ):
            command = cargo_command(
                qualification,
                "test",
                "--manifest-path",
                str(backport_checkout / "Cargo.toml"),
                "--locked",
                "--offline",
                "--target",
                host_target,
                "--no-default-features",
                "--features",
                "transport_compression",
                *arguments,
            )
            run(command, env=qualification.env, cwd=qualification.work)

        for crate in TEST_CRATES:
            command = cargo_command(
                qualification,
                "test",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
                "--offline",
                "--target",
                host_target,
                *(
                    consumer_patch_args.get(
                        crate,
                        cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths),
                    )
                ),
            )
            run(command, env=qualification.env, cwd=qualification.work)
            if crate in consumer_by_crate:
                consumer_by_crate[crate]["compile_steps"].append("CARGO_TEST_PASS")

        for crate in CHECK_CRATES:
            command = cargo_command(
                qualification,
                "check",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
                "--offline",
                "--target",
                host_target,
                *(
                    consumer_patch_args.get(
                        crate,
                        cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths),
                    )
                ),
            )
            run(command, env=qualification.env, cwd=qualification.work)
            if crate in consumer_by_crate:
                consumer_by_crate[crate]["compile_steps"].append("CARGO_CHECK_PASS")

        gateway_command = cargo_command(
            qualification,
            "run",
            "--quiet",
            "--manifest-path",
            str(extracted_paths["ncp-gateway"] / "Cargo.toml"),
            "--locked",
            "--offline",
            "--target",
            host_target,
            *consumer_patch_args["ncp-gateway"],
            "--",
            "--identity-json",
        )
        gateway_identity = json.loads(
            run_capture(
                gateway_command,
                env=qualification.env,
                cwd=qualification.work,
            )
        )
        consumer_by_crate["ncp-gateway"]["compile_steps"].append(
            "CARGO_IDENTITY_RUN_PASS"
        )
        contract = json.loads(
            (package_root / "contract" / "manifest.v1.json").read_text(encoding="utf-8")
        )
        expected_gateway_identity = {
            "package": "ncp-gateway",
            "package_version": version,
            "wire_version": contract["wire_version"],
            "compact_proto_hash": contract["wire_proto_contract_hash_fnv1a64"],
            "normative_contract_digest": contract["contract_digest_sha256"],
            "build_identity": expected_identity,
        }
        if gateway_identity != expected_gateway_identity:
            raise RuntimeError(
                "extracted gateway identity differs from its packaged source: "
                f"{gateway_identity!r} != {expected_gateway_identity!r}"
            )

        for crate, snapshot in extracted_snapshots.items():
            if tree_snapshot(extracted_paths[crate]) != snapshot:
                raise RuntimeError(
                    f"{crate} extracted source changed during offline compilation"
                )
        for crate, retained_lock in conditioned_locks.items():
            if (extracted_paths[crate] / "Cargo.lock").read_bytes() != retained_lock:
                raise RuntimeError(
                    f"{crate} conditioned Cargo.lock changed during compilation"
                )
        post_compile_sources: dict[str, dict[str, object]] = {}
        for crate in ZENOH_CONDITIONAL_CRATES:
            unpatched_metadata, conditioned_graph_metadata = conditioned_metadata[crate]
            post_compile_sources[crate] = verify_conditioned_sources(
                conditioned_graph_metadata, unpatched_metadata, qualification
            )
        assert_consumer_source_point_match(
            pre_compile_sources,
            post_compile_sources,
        )
        verify_toolchain_point_match(qualification)

        if output is not None:
            reproduction_target = temp / "reproduction-target"
            for crate in CRATES:
                command = cargo_command(
                    qualification,
                    "package",
                    "--manifest-path",
                    str(package_root / "Cargo.toml"),
                    "--package",
                    crate,
                    "--allow-dirty",
                    "--locked",
                    "--no-verify",
                    "--target-dir",
                    str(reproduction_target),
                    "--offline",
                    *cargo_patch_args(LOCAL_DEPENDENCIES[crate], source_paths),
                )
                run(command, env=qualification.env, cwd=qualification.work)
                repeated = reproduction_target / "package" / archives[crate].name
                if sha256(repeated) != sha256(archives[crate]):
                    raise RuntimeError(
                        f"{crate} archive differs across two source-identical builds"
                    )

            if (
                package_snapshot is None
                or tree_snapshot(package_root) != package_snapshot
            ):
                raise RuntimeError(
                    "Cargo package qualification mutated its staged source tree"
                )
            verify_toolchain_point_match(qualification)

            stage = Path(
                tempfile.mkdtemp(prefix=".ncp-rust-artifacts-", dir=output.parent)
            )
            try:
                artifact_records: list[dict[str, object]] = []
                for crate in CRATES:
                    destination = stage / archives[crate].name
                    shutil.copyfile(archives[crate], destination)
                    artifact_records.append(
                        {
                            "crate": crate,
                            "path": destination.name,
                            "size_bytes": destination.stat().st_size,
                            "sha256": sha256(destination),
                            "file_manifest_sha256": (
                                archive_file_manifest_digests[crate]
                            ),
                        }
                    )
                qualification_dir = stage / "qualification"
                qualification_dir.mkdir(mode=0o755)
                for crate in ZENOH_CONDITIONAL_CRATES:
                    destination = stage / RETAINED_CONDITIONED_LOCKS[crate]
                    destination.write_bytes(conditioned_locks[crate])
                shutil.copyfile(
                    _registry_crate_archive(
                        qualification,
                        package="lz4_flex",
                        version=FIXED_LZ4_VERSION,
                    ),
                    stage / RETAINED_LZ4_CRATE,
                )
                shutil.copyfile(
                    _registry_crate_archive(
                        qualification,
                        package="twox-hash",
                        version=CONDITIONED_TWOX_VERSION,
                    ),
                    stage / RETAINED_TWOX_CRATE,
                )
                shutil.copyfile(
                    _registry_crate_archive(
                        qualification,
                        package="zenoh-transport",
                        version=ZENOH_TRANSPORT_VERSION,
                    ),
                    stage / RETAINED_UPSTREAM_TRANSPORT_CRATE,
                )
                source_integrity_receipt = {
                    "scope": (
                        "POINT_IN_TIME_CONDITIONED_TRANSPORT_CLOSURE_SOURCE_BYTES"
                    ),
                    "verified_before_compile": True,
                    "verified_after_compile": True,
                    "verification_timing": (
                        "POINT_IN_TIME_BEFORE_AND_AFTER_CARGO_COMPILE_PHASE"
                    ),
                    "compiler_input_tracing": "NOT_RETAINED",
                    "read_only_source_mount": "NOT_CLAIMED",
                    "verified_consumers": list(ZENOH_CONDITIONAL_CRATES),
                    **pre_compile_sources[ZENOH_CONDITIONAL_CRATES[0]],
                }
                receipt = {
                    "schema": RUST_PACKAGE_RECEIPT_SCHEMA,
                    "source_revision": args.source_revision,
                    "embedded_build_identity": expected_identity,
                    "candidate_version": version,
                    "reproducibility_comparison": "PASS",
                    "qualification_environment": qualification.toolchain_receipt,
                    "verification_boundary": RUST_RECEIPT_VERIFICATION_BOUNDARY,
                    "zenoh_consumption": {
                        "status": "CONDITIONAL_PASS",
                        "condition": "EXACT_CONSUMING_ROOT_PATCH_REQUIRED",
                        "package_self_contained": False,
                        "self_contained_distribution_gate": "OPEN_FAIL_CLOSED",
                        "decision": "NO_GO",
                        "release_authorized": False,
                        "affected_archives": list(ZENOH_CONDITIONAL_CRATES),
                        "archive_fallbacks": archive_fallbacks,
                        "conditioned_consumers": conditioned_consumers,
                        "source_integrity": source_integrity_receipt,
                        "qualifying_root_patch": {
                            "repository": ZENOH_BACKPORT_GIT,
                            "revision": ZENOH_BACKPORT_REVISION,
                            "tree": ZENOH_BACKPORT_TREE,
                            "tracked_file_manifest_sha256": (
                                ZENOH_BACKPORT_TRACKED_MANIFEST_SHA256
                            ),
                            "upstream_zenoh_transport_checksum_sha256": (
                                ZENOH_TRANSPORT_REGISTRY_CHECKSUM
                            ),
                            "upstream_delta_status": "PASS_EXACT_ALLOWED_DELTA",
                            "cargo_source": ZENOH_BACKPORT_SOURCE,
                            "cargo_config": ZENOH_BACKPORT_CONFIG,
                            "lz4_flex_version": FIXED_LZ4_VERSION,
                            "lz4_flex_checksum_sha256": FIXED_LZ4_CHECKSUM,
                            "twox_hash_version": CONDITIONED_TWOX_VERSION,
                            "twox_hash_checksum_sha256": CONDITIONED_TWOX_CHECKSUM,
                            "regression_steps": backport_regression_steps,
                            "cargo_verifies_git_signature": False,
                        },
                    },
                    "archives": artifact_records,
                }
                assert_no_local_absolute_paths(
                    receipt,
                    context="Rust package receipt",
                )
                (stage / "rust-package-receipt.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                verify_retained_receipt(
                    stage,
                    version=version,
                    revision=args.source_revision or "",
                )
                os.replace(stage, output)
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                raise

    # Catch a canonical fixture changing while the longer archive tests ran.
    run([sys.executable, "-I", "scripts/sync_rust_package_testdata.py"])
    print(
        "Rust candidate archives verified; ncp-zenoh and ncp-gateway consumption "
        "is conditional on the exact consuming-root backport. The vulnerable "
        "fallback was not compiled; qualification compiled offline. "
        "Self-contained Zenoh package distribution remains NO_GO."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
