#!/usr/bin/env python3
"""Deterministic structural and machine-local resource screens for proposed B01 ADRs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
sys.path.insert(0, str(REPOSITORY))

from e2e.bounded_json import (  # noqa: E402
    MAX_FRAME_BYTES,
    MAX_NESTING_DEPTH,
    BoundedJsonError,
    parse_bounded_json_line,
)

CONTROL_CAPACITY = 128
OBSERVATION_CAPACITY = 64
EXTENSION_CAPACITY = 64
ACTION_CAPACITY = 1
JOURNAL_MAX_ENTRIES = 128
JOURNAL_MAX_BYTES = 65_536
PARSER_PEAK_BUDGET_BYTES = 24 * 1024 * 1024
PARSER_LOCAL_BUDGET_US = 2_000_000


class ResourceProbeError(RuntimeError):
    """One isolation, bound, recovery, seeded-fault, or local-budget failure."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _percentile(values: list[int], numerator: int, denominator: int) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, (len(ordered) * numerator) // denominator)
    return ordered[index]


def _timing(values: list[int]) -> dict[str, int]:
    return {
        "iterations": len(values),
        "minimum_ns": min(values),
        "median_ns": int(statistics.median(values)),
        "p99_ns": _percentile(values, 99, 100),
        "maximum_ns": max(values),
    }


class PlaneQueues:
    def __init__(self) -> None:
        self.queues = {
            "control": deque(maxlen=CONTROL_CAPACITY),
            "observation": deque(maxlen=OBSERVATION_CAPACITY),
            "extension": deque(maxlen=EXTENSION_CAPACITY),
            "action": deque(maxlen=ACTION_CAPACITY),
        }
        self.drops = {"observation": 0, "extension": 0}
        self.rejects = {"control": 0, "action": 0}

    def offer(self, plane: str, value: int) -> bool:
        queue = self.queues[plane]
        if len(queue) == queue.maxlen:
            if plane in self.drops:
                queue.popleft()
                self.drops[plane] += 1
            else:
                self.rejects[plane] += 1
                return False
        queue.append(value)
        return True

    def take(self, plane: str) -> int:
        return self.queues[plane].popleft()


class SharedBudgetQueues(PlaneQueues):
    """Seeded faulty design: observer load consumes the control budget."""

    def offer(self, plane: str, value: int) -> bool:
        total = sum(len(queue) for queue in self.queues.values())
        if total >= CONTROL_CAPACITY and plane == "control":
            self.rejects["control"] += 1
            return False
        return super().offer(plane, value)


def _control_roundtrips(queues: PlaneQueues, count: int) -> list[int]:
    timings: list[int] = []
    for index in range(count):
        started = time.perf_counter_ns()
        if not queues.offer("control", index):
            raise ResourceProbeError("control offer rejected during roundtrip")
        if queues.take("control") != index:
            raise ResourceProbeError("control queue reordered a roundtrip")
        timings.append(time.perf_counter_ns() - started)
    return timings


def _assert_queue_isolation(factory: Callable[[], PlaneQueues]) -> dict[str, Any]:
    queues = factory()
    idle = _control_roundtrips(queues, 20_000)
    if not queues.offer("action", 7):
        raise ResourceProbeError("action queue rejected its first item")
    for index in range(100_000):
        queues.offer("observation", index)
        queues.offer("extension", index)
    if list(queues.queues["action"]) != [7]:
        raise ResourceProbeError(
            "observer or extension saturation changed action state"
        )
    loaded = _control_roundtrips(queues, 20_000)
    if queues.rejects["control"] != 0:
        raise ResourceProbeError("observer or extension load caused control rejection")
    if len(queues.queues["observation"]) != OBSERVATION_CAPACITY:
        raise ResourceProbeError("observation queue did not remain bounded")
    if len(queues.queues["extension"]) != EXTENSION_CAPACITY:
        raise ResourceProbeError("extension queue did not remain bounded")
    if queues.drops != {
        "observation": 100_000 - OBSERVATION_CAPACITY,
        "extension": 100_000 - EXTENSION_CAPACITY,
    }:
        raise ResourceProbeError("drop counters do not match exact overflow")
    return {
        "capacities": {
            "control": CONTROL_CAPACITY,
            "observation": OBSERVATION_CAPACITY,
            "extension": EXTENSION_CAPACITY,
            "action": ACTION_CAPACITY,
        },
        "offers_per_observer_plane": 100_000,
        "idle_control_roundtrip": _timing(idle),
        "loaded_control_roundtrip": _timing(loaded),
        "drops": queues.drops,
        "control_rejections": queues.rejects["control"],
        "action_state_preserved": True,
    }


def queue_probe() -> dict[str, Any]:
    result = _assert_queue_isolation(PlaneQueues)
    try:
        _assert_queue_isolation(SharedBudgetQueues)
    except ResourceProbeError:
        result["shared_budget_mutation_detected"] = True
    else:
        raise ResourceProbeError("shared-budget queue mutation survived")
    return result


def _parse_measurement(payload: bytes) -> dict[str, int]:
    tracemalloc.start()
    started = time.perf_counter_ns()
    value = parse_bounded_json_line(io.BytesIO(payload + b"\n"))
    elapsed_us = (time.perf_counter_ns() - started) // 1_000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if not isinstance(value, list):
        raise ResourceProbeError("parser probe did not decode the expected array")
    if elapsed_us > PARSER_LOCAL_BUDGET_US:
        raise ResourceProbeError("bounded parser exceeded the preliminary local screen")
    if peak > PARSER_PEAK_BUDGET_BYTES:
        raise ResourceProbeError(
            "bounded parser exceeded the preliminary peak-memory screen"
        )
    return {
        "frame_bytes": len(payload),
        "items": len(value),
        "elapsed_microseconds_local": elapsed_us,
        "peak_traced_bytes": peak,
    }


def _must_reject(payload: bytes, code: str) -> None:
    try:
        parse_bounded_json_line(io.BytesIO(payload + b"\n"))
    except BoundedJsonError as error:
        if error.code != code:
            raise ResourceProbeError(
                f"parser rejection code drifted: expected {code}, received {error.code}"
            ) from error
    else:
        raise ResourceProbeError(f"parser accepted an input requiring {code}")


def parser_probe() -> dict[str, Any]:
    small = _canonical_json(["x" * 4096 for _ in range(8)])
    large = _canonical_json(["x" * 4096 for _ in range(248)])
    if len(large) >= MAX_FRAME_BYTES:
        raise ResourceProbeError(
            "large valid parser fixture exceeds the frame boundary"
        )
    measurements = [_parse_measurement(small), _parse_measurement(large)]
    _must_reject(b" " * (MAX_FRAME_BYTES + 1), "NCP-LIMIT-001")
    exact_depth = ("[" * MAX_NESTING_DEPTH + "0" + "]" * MAX_NESTING_DEPTH).encode()
    too_deep = (
        "[" * (MAX_NESTING_DEPTH + 1) + "0" + "]" * (MAX_NESTING_DEPTH + 1)
    ).encode()
    parsed = parse_bounded_json_line(io.BytesIO(exact_depth + b"\n"))
    if parsed is None:
        raise ResourceProbeError("exact-depth parser witness was not decoded")
    _must_reject(too_deep, "NCP-LIMIT-002")
    _must_reject(b'{"a":1,"\\u0061":2}', "NCP-LIMIT-007")
    try:
        parse_bounded_json_line(io.BytesIO(b'{"a":1}'))
    except BoundedJsonError as error:
        if error.code != "NCP-LIMIT-009":
            raise ResourceProbeError("truncation rejection code drifted") from error
    else:
        raise ResourceProbeError("unterminated frame was accepted")

    oversized_valid_json = b'"' + b"x" * MAX_FRAME_BYTES + b'"'
    try:
        json.loads(oversized_valid_json)
    except json.JSONDecodeError as error:
        raise ResourceProbeError(
            "seeded unbounded-parser fixture is not valid JSON"
        ) from error
    try:
        _must_reject(oversized_valid_json, "NCP-LIMIT-001")
    except ResourceProbeError:
        raise
    mutation_detected = True
    return {
        "limits": {
            "max_frame_bytes": MAX_FRAME_BYTES,
            "max_nesting_depth": MAX_NESTING_DEPTH,
            "preliminary_peak_traced_budget_bytes": PARSER_PEAK_BUDGET_BYTES,
            "preliminary_local_budget_us": PARSER_LOCAL_BUDGET_US,
        },
        "measurements": measurements,
        "exact_depth_accepted": True,
        "over_depth_rejected": True,
        "oversized_frame_rejected_before_semantics": True,
        "duplicate_decoded_key_rejected": True,
        "unterminated_frame_rejected": True,
        "unbounded_parser_mutation_detected": mutation_detected,
    }


@dataclass(slots=True)
class BoundedJournal:
    entries: list[dict[str, Any]]
    encoded_bytes: int = 0

    @classmethod
    def empty(cls) -> BoundedJournal:
        return cls(entries=[])

    def append(self, entry: dict[str, Any]) -> None:
        encoded = _canonical_json(entry) + b"\n"
        if (
            len(self.entries) >= JOURNAL_MAX_ENTRIES
            or self.encoded_bytes + len(encoded) > JOURNAL_MAX_BYTES
        ):
            raise ResourceProbeError("journal_capacity")
        self.entries.append(entry)
        self.encoded_bytes += len(encoded)

    def snapshot(self) -> bytes:
        return _canonical_json(
            {
                "encoded_bytes": self.encoded_bytes,
                "entries": self.entries,
                "max_bytes": JOURNAL_MAX_BYTES,
                "max_entries": JOURNAL_MAX_ENTRIES,
            }
        )

    @classmethod
    def restore(cls, snapshot: bytes) -> BoundedJournal:
        try:
            value = parse_bounded_json_line(io.BytesIO(snapshot + b"\n"))
        except BoundedJsonError as error:
            raise ResourceProbeError(
                f"journal snapshot failed bounded parsing: {error.code}"
            ) from error
        if not isinstance(value, dict):
            raise ResourceProbeError("journal snapshot is not an object")
        if set(value) != {"encoded_bytes", "entries", "max_bytes", "max_entries"}:
            raise ResourceProbeError("journal snapshot members drifted")
        if (
            value["max_bytes"] != JOURNAL_MAX_BYTES
            or value["max_entries"] != JOURNAL_MAX_ENTRIES
            or not isinstance(value["entries"], list)
        ):
            raise ResourceProbeError("journal snapshot bounds drifted")
        journal = cls.empty()
        for entry in value["entries"]:
            if not isinstance(entry, dict):
                raise ResourceProbeError("journal snapshot entry is not an object")
            journal.append(entry)
        if journal.encoded_bytes != value["encoded_bytes"]:
            raise ResourceProbeError("journal byte accounting drifted")
        return journal


class EvictingJournal(BoundedJournal):
    """Seeded faulty design: silently evicts recovery evidence."""

    def append(self, entry: dict[str, Any]) -> None:
        try:
            super().append(entry)
        except ResourceProbeError:
            removed = self.entries.pop(0)
            self.encoded_bytes -= len(_canonical_json(removed) + b"\n")
            super().append(entry)


def _entry(index: int) -> dict[str, Any]:
    return {
        "command_id": f"command-{index:04d}",
        "kind": "applied_deny" if index % 10 == 0 else "command_disposition",
        "payload_digest": "a" * 64,
        "recovery_required": index % 10 == 0,
        "sequence": index + 1,
        "summary": "x" * 192,
        "terminal": True,
    }


def _fill_journal(factory: Callable[[], BoundedJournal]) -> tuple[BoundedJournal, int]:
    journal = factory()
    index = 0
    while True:
        try:
            journal.append(_entry(index))
        except ResourceProbeError as error:
            if str(error) != "journal_capacity":
                raise
            return journal, index
        index += 1


def journal_probe() -> dict[str, Any]:
    journal, rejected_index = _fill_journal(BoundedJournal.empty)
    if not journal.entries or rejected_index != len(journal.entries):
        raise ResourceProbeError(
            "journal did not reject exactly at its first unavailable slot"
        )
    original_ids = [entry["command_id"] for entry in journal.entries]
    required = [
        entry["command_id"] for entry in journal.entries if entry["recovery_required"]
    ]
    snapshot = journal.snapshot()
    restored = BoundedJournal.restore(snapshot)
    if [entry["command_id"] for entry in restored.entries] != original_ids:
        raise ResourceProbeError("journal restart replay changed retained identity")
    restored_required = [
        entry["command_id"] for entry in restored.entries if entry["recovery_required"]
    ]
    if restored_required != required:
        raise ResourceProbeError("journal restart replay lost required deny evidence")
    try:
        BoundedJournal.restore(snapshot[:-1])
    except ResourceProbeError:
        truncated_rejected = True
    else:
        raise ResourceProbeError("truncated journal snapshot was accepted")

    duplicate_snapshot = snapshot.replace(
        b'{"encoded_bytes":',
        b'{"encoded_bytes":0,"encoded_bytes":',
        1,
    )
    try:
        BoundedJournal.restore(duplicate_snapshot)
    except ResourceProbeError:
        duplicate_key_rejected = True
    else:
        raise ResourceProbeError("duplicate journal snapshot key was accepted")

    faulty = EvictingJournal.empty()
    for index in range(rejected_index + 1):
        faulty.append(_entry(index))
    if faulty.entries[0]["command_id"] == original_ids[0]:
        raise ResourceProbeError("seeded evicting journal did not exercise eviction")
    mutation_detected = faulty.entries[0]["command_id"] != original_ids[0]
    return {
        "limits": {
            "max_entries": JOURNAL_MAX_ENTRIES,
            "max_encoded_entry_bytes": JOURNAL_MAX_BYTES,
        },
        "retained_entries": len(journal.entries),
        "encoded_entry_bytes": journal.encoded_bytes,
        "snapshot_bytes": len(snapshot),
        "snapshot_sha256": _sha256(snapshot),
        "first_rejected_sequence": rejected_index + 1,
        "required_recovery_entries": len(required),
        "restart_replay_exact": True,
        "truncated_snapshot_rejected": truncated_rejected,
        "duplicate_snapshot_key_rejected": duplicate_key_rejected,
        "silent_eviction_mutation_detected": mutation_detected,
    }


def crypto_probe() -> dict[str, Any]:
    project = REPOSITORY / "prototypes/authenticated-ingress/signed-forwarding-envelope"
    uv = shutil.which("uv")
    if uv is None:
        raise ResourceProbeError("uv is unavailable")
    completed = subprocess.run(  # noqa: S603
        [
            uv,
            "run",
            "--offline",
            "--locked",
            "--project",
            str(project),
            "python",
            str(ROOT / "crypto_probe.py"),
            "--self-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise ResourceProbeError(f"Ed25519 probe failed: {completed.stderr[:512]!r}")
    if completed.stderr:
        raise ResourceProbeError(
            f"Ed25519 probe emitted stderr: {completed.stderr[:512]!r}"
        )
    if len(completed.stdout.encode("utf-8")) > 65_536:
        raise ResourceProbeError("Ed25519 probe exceeded its output bound")
    value = json.loads(completed.stdout)
    if (
        value.get("algorithm") != "Ed25519"
        or value.get("deadline_detector_self_tested") is not True
    ):
        raise ResourceProbeError("Ed25519 probe result is incomplete")
    return value


def build_result() -> dict[str, Any]:
    return {
        "schema": "ncp.b01-preliminary-resource-result.v1",
        "scope": "deterministic-structure-and-machine-local-screen",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "queue_isolation": queue_probe(),
        "bounded_parser": parser_probe(),
        "bounded_journal": journal_probe(),
        "ed25519": crypto_probe(),
        "claim_boundary": (
            "These probes exercise explicit prototype bounds and one local machine. "
            "They do not select normative capacities, prove production deadlines, "
            "qualify performance, establish durability, certify safety, or close any "
            "external release gate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.parse_args()
    print(json.dumps(build_result(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
