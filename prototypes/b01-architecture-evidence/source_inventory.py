#!/usr/bin/env python3
"""Bounded, symlink-safe source and support-file snapshots for B01 evidence."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

SOURCE_SUFFIXES = frozenset({".py", ".sh", ".smt2", ".md"})
MAX_SOURCE_FILES = 64
MAX_SOURCE_DIRECTORIES = 64
MAX_SOURCE_DIRECTORY_ENTRIES = 512
MAX_SOURCE_TREE_ENTRIES = 2048
MAX_SOURCE_FILE_BYTES = 4_194_304
MAX_SOURCE_TOTAL_BYTES = 8_388_608
MAX_RELATIVE_PATH_UTF8_BYTES = 16_384
MAX_RELATIVE_PATH_COMPONENTS = 256
MAX_RELATIVE_PATH_COMPONENT_UTF8_BYTES = 255


class SourceInventoryError(RuntimeError):
    """A source tree or bounded file changed, escaped, or exceeded its cap."""


def _open_flags(*, directory: bool = False) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    return flags


def _read_regular_at(
    directory_fd: int,
    name: str,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[bytes, tuple[int, int]]:
    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise SourceInventoryError(f"{label} is not one regular file")
    if not 0 < before.st_size <= maximum_bytes:
        raise SourceInventoryError(f"{label} is empty or exceeds {maximum_bytes} bytes")
    descriptor = os.open(
        name,
        _open_flags(),
        dir_fd=directory_fd,
    )
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise SourceInventoryError(f"{label} changed before open")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    identity = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        len(content) > maximum_bytes
        or len(content) != opened.st_size
        or any(getattr(opened, field) != getattr(after, field) for field in identity)
        or any(getattr(after, field) != getattr(current, field) for field in identity)
    ):
        raise SourceInventoryError(f"{label} changed while it was read")
    return content, (after.st_dev, after.st_ino)


def _read_bounded_relative_file_snapshot(
    root: Path,
    relative_path: str,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[bytes, tuple[int, int]]:
    """Read one root-relative file and retain its opened physical identity."""

    if type(relative_path) is not str or type(maximum_bytes) is not int:
        raise SourceInventoryError(f"{label} path or limit type is invalid")
    if (
        not relative_path
        or len(relative_path) > MAX_RELATIVE_PATH_UTF8_BYTES
        or "\x00" in relative_path
    ):
        raise SourceInventoryError(f"{label} path is empty or unbounded")
    try:
        relative_path_bytes = relative_path.encode("utf-8")
    except UnicodeEncodeError as error:
        raise SourceInventoryError(
            f"{label} path is not Unicode scalar text"
        ) from error
    if len(relative_path_bytes) > MAX_RELATIVE_PATH_UTF8_BYTES:
        raise SourceInventoryError(f"{label} path exceeds its UTF-8 byte bound")
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or len(relative.parts) > MAX_RELATIVE_PATH_COMPONENTS
        or relative.as_posix() != relative_path
        or any(
            part in {"", ".", ".."}
            or len(part) > MAX_RELATIVE_PATH_COMPONENT_UTF8_BYTES
            or len(part.encode("utf-8")) > MAX_RELATIVE_PATH_COMPONENT_UTF8_BYTES
            for part in relative.parts
        )
    ):
        raise SourceInventoryError(f"{label} path is not a closed relative path")
    descriptor = os.open(root, _open_flags(directory=True))
    try:
        for component in relative.parts[:-1]:
            child = os.open(
                component,
                _open_flags(directory=True),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return _read_regular_at(
            descriptor,
            relative.parts[-1],
            maximum_bytes=maximum_bytes,
            label=label,
        )
    finally:
        os.close(descriptor)


def read_bounded_relative_file(
    root: Path,
    relative_path: str,
    *,
    maximum_bytes: int,
    label: str,
) -> bytes:
    """Read one root-relative regular file through pinned no-follow dirfds."""

    content, _identity = _read_bounded_relative_file_snapshot(
        root,
        relative_path,
        maximum_bytes=maximum_bytes,
        label=label,
    )
    return content


def build_source_inventory(
    root: Path,
    repository: Path,
    *,
    support_relative_paths: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Snapshot the closed source and support set without following symlinks."""

    if (
        type(support_relative_paths) is not tuple
        or len(support_relative_paths) > MAX_SOURCE_FILES
        or any(type(path) is not str for path in support_relative_paths)
        or any(
            not path or len(path) > MAX_RELATIVE_PATH_UTF8_BYTES
            for path in support_relative_paths
        )
        or tuple(sorted(set(support_relative_paths))) != support_relative_paths
    ):
        raise SourceInventoryError(
            "support source paths are duplicate, unordered, or unbounded"
        )

    root_relative = root.relative_to(repository)
    root_descriptor = os.open(root, _open_flags(directory=True))
    pending: list[tuple[int, tuple[str, ...]]] = [(root_descriptor, ())]
    output: list[dict[str, Any]] = []
    directory_count = 0
    tree_entry_count = 0
    total_bytes = 0
    root_identity = os.fstat(root_descriptor)
    seen_directories = {(root_identity.st_dev, root_identity.st_ino)}
    seen_source_files: set[tuple[int, int]] = set()
    try:
        while pending:
            directory_fd, relative_parts = pending.pop()
            try:
                directory_count += 1
                if directory_count > MAX_SOURCE_DIRECTORIES:
                    raise SourceInventoryError(
                        "source tree exceeds its directory bound"
                    )
                entries: list[os.DirEntry[str]] = []
                with os.scandir(directory_fd) as iterator:
                    for entry in iterator:
                        if len(entries) >= MAX_SOURCE_DIRECTORY_ENTRIES:
                            raise SourceInventoryError(
                                "source directory exceeds its entry bound"
                            )
                        entries.append(entry)
                entries.sort(key=lambda entry: entry.name)
                tree_entry_count += len(entries)
                if tree_entry_count > MAX_SOURCE_TREE_ENTRIES:
                    raise SourceInventoryError(
                        "source tree exceeds its total entry bound"
                    )
                for entry in entries:
                    name = entry.name
                    if name in {"", ".", ".."} or "/" in name or "\x00" in name:
                        raise SourceInventoryError(
                            "source tree contains an invalid entry name"
                        )
                    metadata = os.stat(
                        name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(metadata.st_mode):
                        raise SourceInventoryError(
                            "source tree contains a symbolic link"
                        )
                    child_parts = (*relative_parts, name)
                    if stat.S_ISDIR(metadata.st_mode):
                        child = os.open(
                            name,
                            _open_flags(directory=True),
                            dir_fd=directory_fd,
                        )
                        opened = os.fstat(child)
                        if (opened.st_dev, opened.st_ino) != (
                            metadata.st_dev,
                            metadata.st_ino,
                        ):
                            os.close(child)
                            raise SourceInventoryError(
                                "source directory changed before open"
                            )
                        child_identity = (opened.st_dev, opened.st_ino)
                        if child_identity in seen_directories:
                            os.close(child)
                            raise SourceInventoryError(
                                "source tree contains an aliased directory"
                            )
                        seen_directories.add(child_identity)
                        if len(seen_directories) > MAX_SOURCE_DIRECTORIES:
                            os.close(child)
                            raise SourceInventoryError(
                                "source tree exceeds its directory bound"
                            )
                        pending.append((child, child_parts))
                        continue
                    if not stat.S_ISREG(metadata.st_mode):
                        raise SourceInventoryError(
                            "source tree contains a non-regular entry"
                        )
                    if Path(name).suffix not in SOURCE_SUFFIXES:
                        continue
                    source_identity = (metadata.st_dev, metadata.st_ino)
                    if source_identity in seen_source_files:
                        raise SourceInventoryError(
                            "source tree contains an aliased source file"
                        )
                    seen_source_files.add(source_identity)
                    if len(output) >= MAX_SOURCE_FILES:
                        raise SourceInventoryError(
                            "source inventory exceeds its file bound"
                        )
                    logical = root_relative.joinpath(*child_parts).as_posix()
                    content, opened_identity = _read_regular_at(
                        directory_fd,
                        name,
                        maximum_bytes=MAX_SOURCE_FILE_BYTES,
                        label=logical,
                    )
                    if opened_identity != source_identity:
                        raise SourceInventoryError(
                            "source file identity changed before snapshot"
                        )
                    total_bytes += len(content)
                    if total_bytes > MAX_SOURCE_TOTAL_BYTES:
                        raise SourceInventoryError(
                            "source inventory exceeds its aggregate byte bound"
                        )
                    output.append(
                        {
                            "path": logical,
                            "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    )
            finally:
                os.close(directory_fd)
        logical_paths = {source["path"] for source in output}
        for logical in support_relative_paths:
            if (
                logical in logical_paths
                or PurePosixPath(logical).suffix not in SOURCE_SUFFIXES
            ):
                raise SourceInventoryError(
                    "support source path is duplicate or has an unsupported suffix"
                )
            content, source_identity = _read_bounded_relative_file_snapshot(
                repository,
                logical,
                maximum_bytes=MAX_SOURCE_FILE_BYTES,
                label=logical,
            )
            if source_identity in seen_source_files:
                raise SourceInventoryError(
                    "source inventory contains an aliased support file"
                )
            seen_source_files.add(source_identity)
            if len(output) >= MAX_SOURCE_FILES:
                raise SourceInventoryError("source inventory exceeds its file bound")
            total_bytes += len(content)
            if total_bytes > MAX_SOURCE_TOTAL_BYTES:
                raise SourceInventoryError(
                    "source inventory exceeds its aggregate byte bound"
                )
            output.append(
                {
                    "path": logical,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
            logical_paths.add(logical)
    except Exception:
        for directory_fd, _parts in pending:
            os.close(directory_fd)
        raise
    output.sort(key=lambda source: source["path"])
    if len(output) < 10:
        raise SourceInventoryError(
            "preliminary evidence source set is unexpectedly small"
        )
    return output


def _must_reject(operation: Any, label: str) -> None:
    try:
        operation()
    except (OSError, SourceInventoryError):
        return
    raise SourceInventoryError(f"source inventory self-test accepted {label}")


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ncp-b01-source-inventory-") as temporary:
        repository = Path(temporary)
        root = repository / "sources"
        root.mkdir()
        for index in range(10):
            (root / f"source_{index}.py").write_bytes(
                f"VALUE = {index}\n".encode("ascii")
            )
        inventory = build_source_inventory(root, repository)
        if len(inventory) != 10:
            raise SourceInventoryError(
                "source inventory self-test lost a regular source"
            )
        support = repository / "support"
        support.mkdir()
        helper = support / "bounded_helper.py"
        helper.write_bytes(b"VALUE = 'bounded-support'\n")
        supported_inventory = build_source_inventory(
            root,
            repository,
            support_relative_paths=("support/bounded_helper.py",),
        )
        if supported_inventory[-1] != {
            "path": "support/bounded_helper.py",
            "bytes": len(b"VALUE = 'bounded-support'\n"),
            "sha256": hashlib.sha256(b"VALUE = 'bounded-support'\n").hexdigest(),
        }:
            raise SourceInventoryError(
                "support source did not join the exact inventory"
            )
        support_alias = support / "aliased_helper.py"
        os.link(root / "source_0.py", support_alias)
        _must_reject(
            lambda: build_source_inventory(
                root,
                repository,
                support_relative_paths=("support/aliased_helper.py",),
            ),
            "hard-link support alias",
        )
        support_alias.unlink()
        support_symlink = support / "linked_helper.py"
        support_symlink.symlink_to(helper)
        _must_reject(
            lambda: build_source_inventory(
                root,
                repository,
                support_relative_paths=("support/linked_helper.py",),
            ),
            "symbolic-link support source",
        )
        support_symlink.unlink()
        if (
            read_bounded_relative_file(
                repository,
                "sources/source_0.py",
                maximum_bytes=64,
                label="source fixture",
            )
            != b"VALUE = 0\n"
        ):
            raise SourceInventoryError(
                "bounded relative read changed exact fixture bytes"
            )
        _must_reject(
            lambda: read_bounded_relative_file(
                repository,
                "../escape",
                maximum_bytes=64,
                label="traversal fixture",
            ),
            "parent traversal",
        )
        _must_reject(
            lambda: read_bounded_relative_file(
                repository,
                "sources//source_0.py",
                maximum_bytes=64,
                label="noncanonical path fixture",
            ),
            "noncanonical relative path",
        )
        _must_reject(
            lambda: read_bounded_relative_file(
                repository,
                "x" * (MAX_RELATIVE_PATH_UTF8_BYTES + 1),
                maximum_bytes=64,
                label="oversized path fixture",
            ),
            "oversized relative path",
        )
        symlink = root / "source_link.py"
        symlink.symlink_to(root / "source_0.py")
        _must_reject(
            lambda: build_source_inventory(root, repository),
            "symbolic-link source",
        )
        symlink.unlink()
        hardlink = root / "source_hardlink.py"
        os.link(root / "source_0.py", hardlink)
        _must_reject(
            lambda: build_source_inventory(root, repository),
            "hard-link source alias",
        )
        hardlink.unlink()
        wide = root / "wide"
        wide.mkdir()
        for index in range(MAX_SOURCE_DIRECTORY_ENTRIES + 1):
            (wide / f"ignored_{index}.bin").touch()
        _must_reject(
            lambda: build_source_inventory(root, repository),
            "wide source directory",
        )
        for entry in wide.iterdir():
            entry.unlink()
        wide.rmdir()
        fanout = root / "fanout"
        fanout.mkdir()
        for index in range(MAX_SOURCE_DIRECTORIES):
            (fanout / f"directory_{index}").mkdir()
        _must_reject(
            lambda: build_source_inventory(root, repository),
            "source directory fanout",
        )
        for entry in fanout.iterdir():
            entry.rmdir()
        fanout.rmdir()
        oversized = root / "source_9.py"
        oversized.write_bytes(b"x" * (MAX_SOURCE_FILE_BYTES + 1))
        _must_reject(
            lambda: build_source_inventory(root, repository),
            "oversized source",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if not arguments.self_test:
        raise SourceInventoryError("source inventory has no standalone result")
    self_test()
    print("source inventory self-test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
