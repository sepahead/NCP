#!/usr/bin/env python3
"""Build the release artifacts of NCP 2 and the records of their contents.

Usage: build_ncp2_release.py OUT_DIR [--records DIR] [--python PYTHON]

First it checks that all four packages have one version, that each binding requires exactly that
core version, that the Python SDK names it, that each package holds exact copies of the two license
texts, and that the package READMEs, which become the PyPI and crates.io pages, link with absolute
URLs to files and headings that exist.

Then it builds, from the files of this checkout:
- the source distribution and the wheel of `sepahead-ncp` (python/) and `sepahead-ncp-zenoh`
  (bindings/zenoh/python), with `python -m build` (PYTHON needs the `build` package);
- the crate package of `sepahead-ncp-core` (rust/), with `cargo package --locked` on a copy
  outside Git, which also builds the packaged crate. The crate `sepahead-ncp-zenoh` depends on
  `sepahead-ncp-core` from the registry, so it can be packaged only after that crate is published;
  the records list it as pending.

Every artifact is built twice, into two directories, with SOURCE_DATE_EPOCH set to the release
date, and the script fails if a pair differs: wheels and crates byte for byte, source
distributions file by file, because setuptools writes the build time into their file times. It
also fails if an artifact lacks either license text. OUT_DIR then holds the artifacts of the first
build.
The records go to `--records` (default OUT_DIR): `SHA256SUMS` and `dependencies.json`, the
resolved Rust packages of both crates with their versions, checksums, and licenses, and the
Python requirements. The wheels and the crate depend only on the package files and the release
date, so a later commit that changes neither the packages nor the lockfiles keeps their checksums.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_PACKAGES = {"sepahead-ncp": ROOT / "python", "sepahead-ncp-zenoh": ROOT / "bindings" / "zenoh" / "python"}
CRATES = {"sepahead-ncp-core": ROOT / "rust", "sepahead-ncp-zenoh": ROOT / "bindings" / "zenoh" / "rust"}
# The release date of 2.0.0, 2026-11-11T00:00:00Z: the time of every file in the archives. A fixed
# time, not the commit's, keeps the records valid for every commit with the same package files.
SOURCE_DATE_EPOCH = 1794355200


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"{' '.join(command)} failed in {cwd}:\n{result.stdout[-2000:]}{result.stderr[-2000:]}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_files(directory: Path, *options: str) -> list[str]:
    relative = str(directory.relative_to(ROOT))
    output = subprocess.run(
        ["git", "ls-files", "-z", *options, "--", relative], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [os.fsdecode(name) for name in output.split(b"\0") if name]


def export(directory: Path, to: Path) -> None:
    """Copy the files that Git tracks in `directory`, with their bytes in the working tree, into
    `to`. The copies get new file times and the modes 644 or 755, as Git records them, so that a
    build depends neither on untracked files nor on file times, owners, or the umask."""
    untracked = git_files(directory, "--others", "--exclude-standard")
    if untracked:
        raise SystemExit(f"untracked files in a package directory: {untracked}")
    for name in git_files(directory):
        source = ROOT / name
        target = to / source.relative_to(directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, 0o755 if source.stat().st_mode & 0o100 else 0o644)


def normalize_sdist(path: Path) -> None:
    """Rewrite a source distribution with the same files and bytes, in the order of their names,
    with the release date as every time, no owners, and the modes 644 or 755. setuptools writes the
    build time into a source distribution; after this, a rebuild gives the same bytes."""
    with tarfile.open(path) as source:
        members = sorted(source.getmembers(), key=lambda m: m.name)
        data = {m.name: source.extractfile(m).read() for m in members if m.isfile()}
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=SOURCE_DATE_EPOCH) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for member in members:
                if not (member.isfile() or member.isdir()):
                    raise SystemExit(f"{path.name}: {member.name} is neither a file nor a directory")
                member.mtime = SOURCE_DATE_EPOCH
                member.uid = member.gid = 0
                member.uname = member.gname = ""
                member.mode = 0o755 if member.isdir() or member.mode & 0o100 else 0o644
                member.pax_headers = {}
                archive.addfile(member, io.BytesIO(data[member.name]) if member.isfile() else None)
    path.write_bytes(buffer.getvalue())


def build_once(out: Path, python: str, env: dict[str, str]) -> list[Path]:
    out.mkdir(parents=True)
    for name, directory in PYTHON_PACKAGES.items():
        source = out / f"source-{name}"
        export(directory, source)
        run([python, "-m", "build", "--outdir", str(out), str(source)], out, env)
        shutil.rmtree(source)
    for sdist in out.glob("*.tar.gz"):
        normalize_sdist(sdist)
    # Package a copy outside Git: inside the repository, cargo adds .cargo_vcs_info.json with the
    # commit hash, so the archive would change with every commit. `cargo publish` from the tagged
    # commit adds that file; its archive then differs from this one by that file only.
    source, target = out / "source-sepahead-ncp-core", out / "cargo-target"
    export(CRATES["sepahead-ncp-core"], source)
    run(["cargo", "package", "--locked", "--target-dir", str(target)], source, env)
    for crate in sorted((target / "package").glob("*.crate")):
        shutil.copyfile(crate, out / crate.name)
    shutil.rmtree(target)
    shutil.rmtree(source)
    return sorted(p for p in out.iterdir() if p.is_file())


def rust_dependencies(crate: Path) -> list[dict]:
    """The resolved packages of a crate's lockfile, with the license that `cargo metadata` gives."""
    metadata = json.loads(
        subprocess.run(
            ["cargo", "metadata", "--locked", "--format-version", "1"],
            cwd=crate,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    licenses = {(p["name"], p["version"]): p.get("license") for p in metadata["packages"]}
    lock = tomllib.loads((crate / "Cargo.lock").read_text())
    return [
        {
            "name": package["name"],
            "version": package["version"],
            "source": package.get("source", "path"),
            "checksum": package.get("checksum"),
            "license": licenses.get((package["name"], package["version"])),
        }
        for package in lock["package"]
    ]


def check_versions() -> str:
    """Every package has the same version, each binding requires that core version or a later
    compatible one, and the Python SDK names the version in its `implementation`. Returns the
    version. The requirements are ranges, not exact versions: an exact requirement in a library
    forces every consumer onto that one version of the dependency."""
    python = {n: tomllib.loads((d / "pyproject.toml").read_text())["project"] for n, d in PYTHON_PACKAGES.items()}
    rust = {n: tomllib.loads((d / "Cargo.toml").read_text()) for n, d in CRATES.items()}
    versions = {f"{n} (Python)": p["version"] for n, p in python.items()}
    versions |= {f"{n} (Rust)": c["package"]["version"] for n, c in rust.items()}
    if len(set(versions.values())) != 1:
        raise SystemExit(f"the package versions differ: {versions}")
    version = python["sepahead-ncp"]["version"]
    major = int(version.split(".")[0])
    if f"sepahead-ncp>={version},<{major + 1}" not in python["sepahead-ncp-zenoh"]["dependencies"]:
        raise SystemExit(f"the Python binding does not require sepahead-ncp>={version},<{major + 1}")
    if rust["sepahead-ncp-zenoh"]["dependencies"]["sepahead-ncp-core"].get("version") != version:
        raise SystemExit(f"the Rust binding does not require sepahead-ncp-core {version}")
    for name, manifest in rust.items():
        exact = [d for d, spec in manifest["dependencies"].items() if str(spec.get("version", spec) if isinstance(spec, dict) else spec).startswith("=")]
        if exact:
            raise SystemExit(f"{name} requires exact versions of {exact}; a library takes ranges")
    for name, project in python.items():
        exact = [d for d in project.get("dependencies", []) if "==" in d]
        if exact:
            raise SystemExit(f"{name} requires exact versions: {exact}; a library takes ranges")
    if f'IMPLEMENTATION = "ncp-python/{version}"' not in (ROOT / "python" / "ncp" / "owner.py").read_text():
        raise SystemExit(f"python/ncp/owner.py does not name ncp-python/{version}")
    return version


LICENSES = ("LICENSE-MIT", "LICENSE-APACHE")


def check_license_copies() -> None:
    """Each package directory holds exact copies of the repository's two license texts."""
    for directory in (*PYTHON_PACKAGES.values(), *CRATES.values()):
        for name in LICENSES:
            copy = directory / name
            if not copy.is_file() or copy.read_bytes() != (ROOT / name).read_bytes():
                raise SystemExit(f"{copy.relative_to(ROOT)} is not a copy of {name}")


def archive_names(path: Path) -> list[str]:
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path) as archive:
        return archive.getnames()


def check_artifact_licenses(artifacts: list[Path]) -> None:
    """Every artifact carries both license texts with the bytes of the repository's."""
    for artifact in artifacts:
        for name in LICENSES:
            members = [m for m in archive_names(artifact) if m.rsplit("/", 1)[-1] == name]
            if len(members) != 1:
                raise SystemExit(f"{artifact.name} holds {len(members)} copies of {name}")
            if artifact.name.endswith(".whl"):
                with zipfile.ZipFile(artifact) as archive:
                    data = archive.read(members[0])
            else:
                with tarfile.open(artifact) as archive:
                    data = archive.extractfile(members[0]).read()
            if data != (ROOT / name).read_bytes():
                raise SystemExit(f"{artifact.name}: {members[0]} differs from {name}")


BLOB = "https://github.com/sepahead/NCP/blob/main/"


def check_readme_links() -> None:
    """The package READMEs become the pages of PyPI and crates.io, where relative links break, so
    they use absolute URLs. Each URL into this repository must name a file of this checkout and,
    with an anchor, one of that file's headings."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from check_markdown_links import LINK, SCHEME, markdown_anchors

    problems = []
    for directory in (*PYTHON_PACKAGES.values(), *CRATES.values()):
        readme = directory / "README.md"
        for match in LINK.finditer(readme.read_text(encoding="utf-8")):
            target = match.group("target").strip("<>")
            where = f"{readme.relative_to(ROOT)}: {target}"
            if not SCHEME.match(target):
                problems.append(f"{where}: a relative link breaks on PyPI and crates.io")
            elif target.startswith(BLOB):
                path, _, anchor = target[len(BLOB) :].partition("#")
                if not (ROOT / path).is_file():
                    problems.append(f"{where}: no such file")
                elif anchor and anchor not in markdown_anchors(ROOT / path):
                    problems.append(f"{where}: no such heading")
    if problems:
        raise SystemExit("\n".join(problems))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--records", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; give a new directory")
    check_versions()
    check_license_copies()
    check_readme_links()
    os.umask(0o022)
    epoch = str(SOURCE_DATE_EPOCH)
    env = dict(os.environ, SOURCE_DATE_EPOCH=epoch, PYTHONDONTWRITEBYTECODE="1")
    first = build_once(args.out / "first", args.python, env)
    second = build_once(args.out / "second", args.python, env)
    names = [p.name for p in first]
    if names != [p.name for p in second]:
        raise SystemExit(f"the builds made different files: {names} and {[p.name for p in second]}")
    differing = [a.name for a, b in zip(first, second, strict=True) if sha256(a) != sha256(b)]
    if differing:
        raise SystemExit(f"two builds differ: {differing}")
    check_artifact_licenses(first)
    for artifact in first:
        shutil.move(artifact, args.out / artifact.name)
    shutil.rmtree(args.out / "first")
    shutil.rmtree(args.out / "second")
    records = args.records or args.out
    records.mkdir(parents=True, exist_ok=True)
    artifacts = sorted(p for p in args.out.iterdir() if p.is_file() and p.suffix in (".whl", ".gz", ".crate"))
    (records / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in artifacts))
    python_requirements = {}
    for name, directory in PYTHON_PACKAGES.items():
        project = tomllib.loads((directory / "pyproject.toml").read_text())["project"]
        python_requirements[name] = {"version": project["version"], "requires": project.get("dependencies", [])}
    sdists = {p.name: sorted(archive_names(p)) for p in artifacts if p.name.endswith(".tar.gz")}
    record = {
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "artifacts": {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in artifacts},
        "pending": {"sepahead-ncp-zenoh (crate)": "packaged after sepahead-ncp-core is published"},
        "python": python_requirements,
        "rust": {name: rust_dependencies(directory) for name, directory in CRATES.items()},
        "sdist_files": sdists,
    }
    (records / "dependencies.json").write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    for p in artifacts:
        print(f"{sha256(p)}  {p.name}  {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
