#!/usr/bin/env python3
"""B05 raw-index controls: actual Git producers plus labeled derived challenges."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b05_runner_under_test", ROOT / "scripts/run_b05_preflight.py"
)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
RECORDS = []
EVIDENCE = (
    Path(os.environ["NCP_B05_INDEX_EVIDENCE_DIR"])
    if "NCP_B05_INDEX_EVIDENCE_DIR" in os.environ
    else None
)


def seal(prefix, algorithm):
    return prefix + hashlib.new(algorithm, prefix).digest()


def varint(value):
    output = [value & 127]
    value >>= 7
    while value:
        value -= 1
        output.append(128 | (value & 127))
        value >>= 7
    return bytes(reversed(output))


def derived_index(
    paths, *, version=2, algorithm="sha1", flags=0, extended=0, extensions=()
):
    """Independent test writer. These bytes are never labeled Git-generated."""
    width = 20 if algorithm == "sha1" else 32
    output = bytearray(struct.pack(">4sII", b"DIRC", version, len(paths)))
    previous = b""
    for path in paths:
        start = len(output)
        output.extend(struct.pack(">10I", 0, 0, 0, 0, 0, 0, 0o100644, 0, 0, 1))
        output.extend(b"\x11" * width)
        output.extend(struct.pack(">H", flags | min(len(path), 4095)))
        if flags & 0x4000:
            output.extend(struct.pack(">H", extended))
        suffix = path
        if version == 4:
            shared = 0
            while (
                shared < min(len(previous), len(path))
                and previous[shared] == path[shared]
            ):
                shared += 1
            output.extend(varint(len(previous) - shared))
            suffix = path[shared:]
        output.extend(suffix + b"\0")
        if version != 4:
            output.extend(b"\0" * (-(len(output) - start) % 8))
        previous = path
    for signature, payload in extensions:
        output.extend(signature + struct.pack(">I", len(payload)) + payload)
    return seal(bytes(output), algorithm)


def retain(label, raw, algorithm, accepted, origin):
    row = {
        "label": label,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "object_format": algorithm,
        "expected_acceptance": accepted,
        "origin": origin,
    }
    RECORDS.append(row)
    if EVIDENCE:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        name = f"{len(RECORDS):04d}-{row['sha256']}.index"
        (EVIDENCE / name).write_bytes(raw)
        row["artifact"] = name
        (EVIDENCE / "cases.json").write_text(json.dumps(RECORDS, indent=2) + "\n")


def fixture_fsmonitor_dirty_bits(raw, algorithm):
    """Independent v2 fixture reader; inspect the real EWAH, never a Git flag view.

    This accepts only the tiny test producer's single-literal bitmap. It is not
    an alternate production parser or a general fsmonitor implementation.
    """
    width = 20 if algorithm == "sha1" else 32
    signature, version, count = struct.unpack_from(">4sII", raw)
    assert signature == b"DIRC" and version == 2 and count <= 64
    assert seal(raw[:-width], algorithm) == raw
    offset = 12
    for _ in range(count):
        start = offset
        flags = struct.unpack_from(">H", raw, offset + 40 + width)[0]
        assert not flags & 0xF000
        offset = raw.index(b"\0", offset + 42 + width) + 1
        offset += -(offset - start) % 8
    payload = None
    while offset < len(raw) - width:
        tag, size = struct.unpack_from(">4sI", raw, offset)
        offset += 8
        assert offset + size <= len(raw) - width
        if tag == b"FSMN":
            assert payload is None
            payload = raw[offset : offset + size]
        offset += size
    assert offset == len(raw) - width and payload is not None
    assert struct.unpack_from(">I", payload)[0] == 2
    cursor = payload.index(b"\0", 4) + 1
    size = struct.unpack_from(">I", payload, cursor)[0]
    bitmap = payload[cursor + 4 :]
    assert len(bitmap) == size == 28
    bit_count, words, run, literal, last_run = struct.unpack(">IIQQI", bitmap)
    assert 0 < bit_count <= count and words == 2 and run == 1 << 33 and last_run == 0
    assert literal >> bit_count == 0
    return [bool(literal & (1 << position)) for position in range(count)]


class RawIndexTests(unittest.TestCase):
    def check(
        self,
        label,
        raw,
        *,
        algorithm="sha1",
        accepted=True,
        origin="derived structural challenge",
    ):
        retain(label, raw, algorithm, accepted, origin)
        if accepted:
            return RUNNER.parse_raw_index(raw, algorithm)
        with self.assertRaises(SystemExit, msg=label):
            RUNNER.parse_raw_index(raw, algorithm)
        return None

    def test_versions_formats_extensions_and_unsigned_non_utf8_paths(self):
        for algorithm in ("sha1", "sha256"):
            for version in (2, 3, 4):
                paths = [
                    b"FSMN-name",
                    b"shared/long/name/a",
                    b"shared/long/name/b",
                    b"\xff",
                ]
                result, metadata = self.check(
                    f"derived-v{version}-{algorithm}",
                    derived_index(paths, version=version, algorithm=algorithm),
                    algorithm=algorithm,
                )
                self.assertEqual(list(result), paths)
                self.assertEqual(metadata["version"], version)
                self.check(
                    "opaque-extension-FSMN-is-not-a-header",
                    derived_index(
                        paths,
                        version=version,
                        algorithm=algorithm,
                        extensions=((b"REUC", b"FSMN"),),
                    ),
                    algorithm=algorithm,
                )
        self.check(
            "v3-zero-extended-word", derived_index([b"a"], version=3, flags=0x4000)
        )

    def test_checksums_headers_lengths_flags_padding_and_paths(self):
        base = derived_index([b"a"])
        for label, raw in (
            ("missing-trailer", base[:-20]),
            ("zero-trailer", base[:-20] + b"\0" * 20),
            ("wrong-trailer", base[:-1] + bytes([base[-1] ^ 1])),
            ("truncated", base[:30]),
            ("oversize", b"\0" * (16 * 1024 * 1024 + 1)),
        ):
            self.check(label, raw, accepted=False)
        for offset, value in (
            (0, b"WRNG"),
            (4, struct.pack(">I", 1)),
            (4, struct.pack(">I", 5)),
            (8, struct.pack(">I", 100001)),
            (8, struct.pack(">I", 0)),
            (12 + 24, struct.pack(">I", 0o040000)),
            (12 + 60, struct.pack(">H", 2)),
        ):
            prefix = bytearray(base[:-20])
            prefix[offset : offset + len(value)] = value
            self.check(
                f"changed-field-{offset}-{value.hex()}",
                seal(bytes(prefix), "sha1"),
                accepted=False,
            )
        padded = bytearray(derived_index([b"aa"])[:-20])
        padded[-1] = 1
        self.check("nonzero-padding", seal(bytes(padded), "sha1"), accepted=False)
        for version in (2, 3, 4):
            for flags, extended in (
                (0x8000, 0),
                (0x1000, 0),
                (0x4000, 1),
                (0x4000, 0x2000),
                (0x4000, 0x4000),
                (0x4000, 0x8000),
            ):
                self.check(
                    f"flags-{version}-{flags}-{extended}",
                    derived_index(
                        [b"a"], version=version, flags=flags, extended=extended
                    ),
                    accepted=False,
                )
        for paths in (
            [b"a", b"a"],
            [b"b", b"a"],
            [b"/a"],
            [b"a/"],
            [b"a//b"],
            [b"a/../b"],
            [b".git/a"],
            [b"./a"],
            [b"a" * 4097],
        ):
            self.check("bad-path-roster", derived_index(paths), accepted=False)
        self.check("maximum-path", derived_index([b"p" * 4096]))
        self.check("unknown-storage-format", base, algorithm="sha512", accepted=False)

    def test_v4_prefix_overflow_removal_and_unfinished_integer(self):
        base = derived_index([b"aa", b"ab"], version=4)
        # First fixed entry starts at12; prefix integer follows40 stat+20OID+2flags.
        offset = 74
        for replacement in (b"\x01", b"\xff\xff\xff", b"\x80" * 8):
            prefix = base[:offset] + replacement + base[offset + 1 : -20]
            self.check("v4-invalid-first-prefix", seal(prefix, "sha1"), accepted=False)
        self.check(
            "v4-unfinished-prefix",
            seal(base[:offset] + b"\x80", "sha1"),
            accepted=False,
        )
        self.check(
            "v4-long-shared-prefix",
            derived_index([b"p" * 3990 + b"/alpha", b"p" * 3990 + b"/beta"], version=4),
        )

    def test_closed_extension_framing_and_conservative_fsmonitor_policy(self):
        for signature in (
            b"FSMN",
            b"EOIE",
            b"IEOT",
            b"link",
            b"sdir",
            b"ZZZZ",
            b"abcd",
        ):
            self.check(
                "unsupported-" + signature.decode(),
                derived_index([b"a"], extensions=((signature, b"\0" * 20),)),
                accepted=False,
            )
        self.check(
            "duplicate-TREE",
            derived_index([b"a"], extensions=((b"TREE", b""), (b"TREE", b""))),
            accepted=False,
        )
        base = derived_index([b"a"])
        for suffix in (b"F", b"TREE\0", b"TREE" + struct.pack(">I", 0xFFFFFFFF)):
            self.check(
                "truncated-extension", seal(base[:-20] + suffix, "sha1"), accepted=False
            )

    def test_entry_and_expanded_path_ceiling_before_growth(self):
        self.check(
            "maximum100000entries",
            derived_index([f"{i:06d}".encode() for i in range(100000)]),
        )
        paths = [b"p" * 249 + b"/" + f"{i:06d}".encode() for i in range(65536)]
        _, metadata = self.check(
            "maximum16MiB-expanded-paths", derived_index(paths, version=4)
        )
        self.assertEqual(metadata["expanded_path_bytes"], 16 * 1024 * 1024)
        self.check(
            "expanded-path-budget-plus-one-entry",
            derived_index(paths + [b"q"], version=4),
            accepted=False,
        )

    def test_actual_no_follow_and_capture_identity_changes(self):
        with tempfile.TemporaryDirectory(prefix="ncp-b05-capture-") as temporary:
            root = Path(temporary)
            path = root / "index"
            raw = derived_index([b"a"])
            path.write_bytes(raw)
            self.assertEqual(RUNNER.capture_index(path)[0], raw)
            link = root / "symlink"
            link.symlink_to(path)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            for wrong in (link, fifo, root):
                with self.assertRaises(SystemExit):
                    RUNNER.capture_index(wrong)
            original = os.read
            for change in ("replace", "grow", "same-inode-forced-time-change"):
                path.write_bytes(raw)
                before = path.stat()
                changed = False

                def controlled_read(fd, count):
                    nonlocal changed
                    result = original(fd, count)
                    if not changed:
                        changed = True
                        if change == "replace":
                            other = root / "replacement"
                            other.write_bytes(raw)
                            os.replace(other, path)
                        elif change == "grow":
                            with path.open("ab") as output:
                                output.write(b"x")
                        else:
                            path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
                            # Timestamp resolution can hide a same-inode write.
                            # This control explicitly changes the observed identity.
                            os.utime(
                                path,
                                ns=(
                                    before.st_atime_ns,
                                    before.st_mtime_ns + 1_000_000_000,
                                ),
                            )
                    return result

                with patch.object(RUNNER.os, "read", side_effect=controlled_read):
                    with self.assertRaises(SystemExit):
                        RUNNER.capture_index(path)
            path.write_bytes(raw)
            self.assertEqual(RUNNER.capture_index(path)[0], raw)

    def test_actual_git_producers_and_normalization(self):
        for algorithm in ("sha1", "sha256"):
            with tempfile.TemporaryDirectory(prefix="ncp-b05-git-") as temporary:
                root = Path(temporary)

                def git(*args):
                    result = subprocess.run(
                        ["/usr/bin/git", *args],
                        cwd=root,
                        env=RUNNER.COMMAND_ENVIRONMENT,
                        check=True,
                        capture_output=True,
                        timeout=10,
                    )
                    return result.stdout

                git("init", f"--object-format={algorithm}", "-b", "main")
                git("config", "user.name", "NCP structural control")
                git("config", "user.email", "ncp@example.invalid")
                for name in (
                    "FSMN-name",
                    "nested/long-shared-prefix/alpha",
                    "nested/long-shared-prefix/beta",
                    "z",
                ):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("fixture\n")
                git("add", ".")
                git("commit", "-m", "bounded fixture")
                index = root / ".git/index"
                for version in (2, 4):
                    git("update-index", f"--index-version={version}")
                    raw = index.read_bytes()
                    roster, meta = self.check(
                        f"git-generated-normal-v{version}-{algorithm}",
                        raw,
                        algorithm=algorithm,
                        origin="actual /usr/bin/git-generated index",
                    )
                    self.assertEqual(meta["version"], version)
                    self.assertEqual(
                        roster,
                        RUNNER.parse_index_stage(git("ls-files", "--stage", "-z")),
                    )
                git("update-index", "--index-version=2")
                original = index.read_bytes()
                width = 20 if algorithm == "sha1" else 32
                derived = seal(
                    original[:4] + struct.pack(">I", 3) + original[8:-width], algorithm
                )
                index.write_bytes(derived)
                self.check(
                    "derived-normal-v3-real-Git-consumer",
                    derived,
                    algorithm=algorithm,
                    origin="Git-v2 entries; test changes version and reseals checksum",
                )
                self.assertEqual(
                    RUNNER.parse_index_stage(git("ls-files", "--stage", "-z")),
                    RUNNER.parse_raw_index(derived, algorithm)[0],
                )
                git("update-index", "--skip-worktree", "z")
                self.check(
                    "actual-Git-v3-hidden-flag",
                    index.read_bytes(),
                    algorithm=algorithm,
                    accepted=False,
                    origin="actual /usr/bin/git-generated index",
                )
                self.assertEqual(int.from_bytes(index.read_bytes()[4:8], "big"), 3)
                git("update-index", "--no-skip-worktree", "z")
                self.check(
                    "Git-normalized-hidden-flag",
                    index.read_bytes(),
                    algorithm=algorithm,
                    origin="actual /usr/bin/git-generated index",
                )
                for persisted in (False, True):
                    if persisted:
                        git("config", "core.fsmonitor", "true")
                    git(
                        "-c",
                        "core.fsmonitor=true",
                        "update-index",
                        "--fsmonitor-valid",
                        "z",
                    )
                    self.check(
                        "actual-FSMN-valid",
                        index.read_bytes(),
                        algorithm=algorithm,
                        accepted=False,
                        origin="actual /usr/bin/git-generated index",
                    )
                    self.assertFalse(
                        all(fixture_fsmonitor_dirty_bits(index.read_bytes(), algorithm))
                    )
                    git(
                        "-c",
                        "core.fsmonitor=true",
                        "update-index",
                        "--no-fsmonitor-valid",
                        "FSMN-name",
                        "nested/long-shared-prefix/alpha",
                        "nested/long-shared-prefix/beta",
                        "z",
                    )
                    self.check(
                        "actual-FSMN-all-dirty",
                        index.read_bytes(),
                        algorithm=algorithm,
                        accepted=False,
                        origin="actual /usr/bin/git-generated index",
                    )
                    self.assertTrue(
                        all(fixture_fsmonitor_dirty_bits(index.read_bytes(), algorithm))
                    )
                    git("config", "core.fsmonitor", "false")
                    git("-c", "core.fsmonitor=false", "update-index", "--no-fsmonitor")
                    self.check(
                        "actual-FSMN-normalized",
                        index.read_bytes(),
                        algorithm=algorithm,
                        origin="actual /usr/bin/git-generated index",
                    )
                git("update-index", "--split-index")
                self.check(
                    "actual-split-index",
                    index.read_bytes(),
                    algorithm=algorithm,
                    accepted=False,
                    origin="actual /usr/bin/git-generated index",
                )
                git("update-index", "--no-split-index")
                self.check(
                    "actual-unsplit-index",
                    index.read_bytes(),
                    algorithm=algorithm,
                    origin="actual /usr/bin/git-generated index",
                )
                git("sparse-checkout", "init", "--cone", "--sparse-index")
                git("sparse-checkout", "set", "absent-directory")
                self.check(
                    "actual-sparse-index",
                    index.read_bytes(),
                    algorithm=algorithm,
                    accepted=False,
                    origin="actual /usr/bin/git-generated index",
                )
                git("sparse-checkout", "disable")
                self.check(
                    "actual-expanded-index",
                    index.read_bytes(),
                    algorithm=algorithm,
                    origin="actual /usr/bin/git-generated index",
                )
                linked = root / "linked"
                git("worktree", "add", "-b", "linked-control", str(linked))
                with patch.object(RUNNER, "ROOT", linked):
                    located, actual_algorithm = RUNNER.index_locator()
                    self.assertNotEqual(located, linked / ".git/index")
                    self.assertEqual(actual_algorithm, algorithm)
                    self.check(
                        "actual-linked-worktree",
                        RUNNER.capture_index(located)[0],
                        algorithm=algorithm,
                        origin="actual /usr/bin/git-generated linked-worktree index",
                    )
                    head = RUNNER.git_text("rev-parse", "HEAD")
                    RUNNER.index_snapshot(head)
                    original_capture = RUNNER.capture_index
                    original_raw = located.read_bytes()
                    first_stamp = None
                    calls = 0

                    def collision_capture(path):
                        nonlocal calls, first_stamp
                        calls += 1
                        if calls == 2:
                            # Actual same-size file overwrite with a preserved roster.
                            # Model a stamp collision explicitly on every host; do not
                            # claim that Darwin physically returned an unchanged ctime.
                            changed = bytearray(path.read_bytes()[:-width])
                            changed[12] ^= 1
                            path.write_bytes(seal(bytes(changed), algorithm))
                        captured, stamp = original_capture(path)
                        if calls == 1:
                            first_stamp = stamp
                        return captured, first_stamp

                    try:
                        with patch.object(
                            RUNNER, "capture_index", side_effect=collision_capture
                        ):
                            with self.assertRaisesRegex(
                                SystemExit, "changed across its adjacent Git view"
                            ):
                                RUNNER.index_snapshot(head)
                        self.assertEqual(calls, 2)
                    finally:
                        located.write_bytes(original_raw)
                    RUNNER.index_snapshot(head)


if __name__ == "__main__":
    unittest.main(verbosity=2)
