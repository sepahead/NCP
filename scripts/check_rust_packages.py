#!/usr/bin/env python3
"""Build and exercise the distributable Rust crate archives.

All five packageable workspace crates are packaged and inspected. The three
crates with package-sensitive test fixtures are tested from their extracted
archives; the Python binding is type-checked and the gateway is type-checked plus
executed for its exact identity receipt. Temporary
Cargo patches point exact unpublished NCP dependencies at the corresponding
extracted archives, leaving the normalized/published manifests untouched.
"""

from __future__ import annotations

import argparse
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
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRATES = ("ncp-core", "ncp-zenoh", "ncp-cpp", "ncp-python", "ncp-gateway")
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


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


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
        stdout=subprocess.PIPE,
    )
    return process.stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def self_test() -> None:
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


def extract_archive(archive: Path, destination: Path, expected_prefix: str) -> Path:
    with tarfile.open(archive, "r:gz") as package:
        seen: set[str] = set()
        for member in package.getmembers():
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "." in path.parts
                or not path.parts
                or path.parts[0] != expected_prefix
                or "\\" in member.name
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
        package.extractall(destination)
    return destination / expected_prefix


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
        help="pass --offline to Cargo (useful after the workspace gate populated its cache)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "atomically retain verified crate archives and a checksum receipt in this "
            "new directory; also rebuild and compare every archive"
        ),
    )
    parser.add_argument(
        "--source-revision",
        help="exact 40-hex source revision bound into an --output-dir receipt",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
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

    run([sys.executable, "scripts/sync_rust_package_testdata.py"])
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    version = workspace["workspace"]["package"]["version"]

    with tempfile.TemporaryDirectory(prefix="ncp-package-selftest-") as tmp:
        temp = Path(tmp)
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
        source_paths = {crate: package_root / crate for crate in CRATES}
        extracted_paths: dict[str, Path] = {}
        archives: dict[str, Path] = {}

        for crate in CRATES:
            command = [
                "cargo",
                "package",
                "--package",
                crate,
                "--allow-dirty",
                "--locked",
                "--no-verify",
                "--target-dir",
                str(package_target),
            ]
            if args.offline:
                command.append("--offline")
            command.extend(cargo_patch_args(LOCAL_DEPENDENCIES[crate], source_paths))
            run(command, cwd=package_root)

            archive = package_target / "package" / f"{crate}-{version}.crate"
            if not archive.is_file():
                raise RuntimeError(f"Cargo did not produce {archive}")
            archives[crate] = archive
            prefix = f"{crate}-{version}"
            extracted = extract_archive(archive, extracted_parent, prefix)
            assert_archive_surface(crate, source_paths[crate], extracted)
            extracted_paths[crate] = extracted

        # Keep build artifacts under the same temporary tree as the extraction.
        # `CARGO_MANIFEST_DIR` is compiled into several fixture paths; reusing a
        # target directory across differently named temp extractions can otherwise
        # execute a stale test binary that points at an already-deleted directory.
        test_target = temp / "test-target"
        env = os.environ.copy()
        # Prove the source artifacts carry their identity without relying on the
        # candidate builder's private compiler environment.
        env.pop("NCP_BUILD_IDENTITY", None)
        expected_identity = args.source_revision or "unreleased-worktree"
        env["NCP_EXPECTED_BUILD_IDENTITY"] = expected_identity
        env["CARGO_TARGET_DIR"] = str(test_target)
        for crate in TEST_CRATES:
            command = [
                "cargo",
                "test",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
            ]
            if args.offline:
                command.append("--offline")
            command.extend(cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths))
            run(command, env=env, cwd=package_root)

        for crate in CHECK_CRATES:
            command = [
                "cargo",
                "check",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
            ]
            if args.offline:
                command.append("--offline")
            command.extend(cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths))
            run(command, env=env, cwd=package_root)

        gateway_command = [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(extracted_paths["ncp-gateway"] / "Cargo.toml"),
            "--locked",
        ]
        if args.offline:
            gateway_command.append("--offline")
        gateway_command.extend(
            cargo_patch_args(LOCAL_DEPENDENCIES["ncp-gateway"], extracted_paths)
        )
        gateway_command.extend(("--", "--identity-json"))
        gateway_identity = json.loads(
            run_capture(gateway_command, env=env, cwd=package_root)
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

        if output is not None:
            reproduction_target = temp / "reproduction-target"
            for crate in CRATES:
                command = [
                    "cargo",
                    "package",
                    "--package",
                    crate,
                    "--allow-dirty",
                    "--locked",
                    "--no-verify",
                    "--target-dir",
                    str(reproduction_target),
                ]
                if args.offline:
                    command.append("--offline")
                command.extend(
                    cargo_patch_args(LOCAL_DEPENDENCIES[crate], source_paths)
                )
                run(command, cwd=package_root)
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
                        }
                    )
                receipt = {
                    "schema": "ncp.rust-package-receipt.v1",
                    "source_revision": args.source_revision,
                    "embedded_build_identity": expected_identity,
                    "candidate_version": version,
                    "reproducibility_comparison": "PASS",
                    "archives": artifact_records,
                }
                (stage / "rust-package-receipt.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.replace(stage, output)
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                raise

    # Catch a canonical fixture changing while the longer archive tests ran.
    run([sys.executable, "scripts/sync_rust_package_testdata.py"])
    print("Rust package archive self-test passed for all five packageable crates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
