#!/usr/bin/env python3
"""Run narrow, mutation-sensitive B01 SMT obligations with exact Z3 output."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SMT = ROOT / "smt"
EXPECTED_Z3_VERSION = "Z3 version 4.16.0 - 64 bit"
EXPECTATION = re.compile(r"^; EXPECT: (sat|unsat) ([a-z0-9_]+)$", re.MULTILINE)
FORBIDDEN_COMMAND = re.compile(
    r"\(\s*(?:echo|exit|get-info|get-model|get-option|get-proof|get-unsat-core|"
    r"get-value|include|reset|reset-assertions|set-option)\b",
    re.IGNORECASE,
)


class SmtError(RuntimeError):
    """One exact-version, source, expectation, mutation, or solver failure."""


@dataclass(frozen=True, slots=True)
class SmtCase:
    path: Path
    mutations: tuple[tuple[str, str, str], ...]


CASES = (
    SmtCase(
        SMT / "authority_handover.smt2",
        (
            (
                "omit_old_revocation",
                "(and old_revoked (not old_admission_open) quiesced higher_term)",
                "(and (not old_admission_open) quiesced higher_term)",
            ),
        ),
    ),
    SmtCase(
        SMT / "stale_admission.smt2",
        (
            (
                "omit_generation_fence",
                "      (= command_generation current_generation)\n"
                "      (= command_epoch current_epoch)",
                "      true\n      (= command_epoch current_epoch)",
            ),
        ),
    ),
    SmtCase(
        SMT / "assessment_monotonicity.smt2",
        (
            (
                "omit_unauthenticated_state_preservation",
                "(assert\n  (=>\n    (not authenticated_widen)\n"
                "    (and (= local_after local_before) (=> deny_before deny_after))))",
                "(assert true)",
            ),
            (
                "omit_recovery_dwell",
                "(assert (=> (and deny_before (not deny_after)) "
                "recovery_dwell_complete))",
                "(assert true)",
            ),
            (
                "omit_evidence_authentication",
                "(assert (=> deny_applied evidence_authenticated))",
                "(assert true)",
            ),
            (
                "omit_profile_authentication",
                "(assert (=> deny_applied profile_authenticated))",
                "(assert true)",
            ),
            (
                "omit_profile_issuer_independence",
                "(assert (=> deny_applied profile_issuer_independent))",
                "(assert true)",
            ),
            (
                "omit_profile_qualification",
                "(assert (=> deny_applied qualification_valid))",
                "(assert true)",
            ),
            (
                "omit_evidence_eligibility",
                "(assert (=> deny_applied evidence_eligible))",
                "(assert true)",
            ),
            (
                "omit_causal_separation",
                "(assert (=> deny_applied causally_later))",
                "(assert true)",
            ),
            (
                "omit_disposition_authentication",
                "(assert (=> deny_applied disposition_authenticated))",
                "(assert true)",
            ),
            (
                "omit_applied_outcome",
                "(assert (=> deny_applied disposition_outcome_applied))",
                "(assert true)",
            ),
        ),
    ),
    SmtCase(
        SMT / "non_authority_inputs.smt2",
        (
            (
                "observer_can_replace_body_lease",
                "(and body_lease plant_session current_commander core_route)",
                "(and true plant_session current_commander core_route)",
            ),
        ),
    ),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _z3_identity() -> tuple[str, str]:
    z3 = shutil.which("z3")
    if z3 is None:
        raise SmtError("z3 is unavailable")
    completed = subprocess.run(  # noqa: S603
        [z3, "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if completed.stderr:
        raise SmtError("z3 -version emitted stderr")
    value = completed.stdout.strip()
    if value != EXPECTED_Z3_VERSION:
        raise SmtError(
            f"Z3 version drifted: expected {EXPECTED_Z3_VERSION!r}, received {value!r}"
        )
    binary = Path(z3).resolve().read_bytes()
    return value, _sha256(binary)


def _expectations(source: str) -> list[dict[str, str]]:
    output = [
        {"expected": expected, "id": identifier}
        for expected, identifier in EXPECTATION.findall(source)
    ]
    if not output:
        raise SmtError("SMT source contains no registered expectations")
    return output


def _validate_source(source: str, expected: list[dict[str, str]]) -> None:
    if FORBIDDEN_COMMAND.search(source):
        raise SmtError("SMT source contains a forbidden output or control command")
    if source.count("(check-sat)") != len(expected):
        raise SmtError("SMT check-sat count differs from registered expectations")
    if source.count("(push)") != source.count("(pop)"):
        raise SmtError("SMT push/pop scopes are unbalanced")
    if len(re.findall(r"\(\s*set-logic\b", source)) != 1:
        raise SmtError("SMT source must contain exactly one set-logic command")


def _solve(path: Path, source: str) -> dict[str, object]:
    expected = _expectations(source)
    _validate_source(source, expected)
    started = time.monotonic_ns()
    z3 = shutil.which("z3")
    if z3 is None:
        raise SmtError("z3 is unavailable")
    completed = subprocess.run(  # noqa: S603
        [z3, "-T:5", "-in"],
        check=False,
        capture_output=True,
        text=True,
        input=source,
        timeout=10,
    )
    elapsed = time.monotonic_ns() - started
    if completed.returncode != 0:
        raise SmtError(
            f"{path.name} exited {completed.returncode}: {completed.stderr[:512]!r}"
        )
    if completed.stderr:
        raise SmtError(f"{path.name} emitted stderr: {completed.stderr[:512]!r}")
    if len(completed.stdout.encode("utf-8")) > 65_536:
        raise SmtError(f"{path.name} exceeded the output limit")
    expected_values = [item["expected"] for item in expected]
    actual = completed.stdout.splitlines()
    if actual != expected_values:
        raise SmtError(
            f"{path.name} stdout differs: expected only {expected_values}, "
            f"received {actual}"
        )
    return {
        "source_sha256": _sha256(source.encode("utf-8")),
        "source_bytes": len(source.encode("utf-8")),
        "elapsed_microseconds_local": elapsed // 1_000,
        "checks": [
            {
                "id": item["id"],
                "expected": item["expected"],
                "actual": result,
            }
            for item, result in zip(expected, actual, strict=True)
        ],
        "stdout_sha256": _sha256(completed.stdout.encode("utf-8")),
        "command": ["z3", "-T:5", "-in"],
    }


def _mutate(source: str, replacement: tuple[str, str, str]) -> str:
    _, old, new = replacement
    output = source
    if output.count(old) != 1:
        raise SmtError(f"mutation anchor count is not exactly one: {old!r}")
    output = output.replace(old, new)
    return output


def build_result() -> dict[str, object]:
    version, binary_sha256 = _z3_identity()
    obligations: list[dict[str, object]] = []
    killed: list[dict[str, object]] = []
    for case in CASES:
        source = case.path.read_text(encoding="utf-8")
        obligation = _solve(case.path, source)
        obligation["path"] = case.path.relative_to(ROOT).as_posix()
        obligations.append(obligation)

        for replacement in case.mutations:
            mutation_id = replacement[0]
            mutant = _mutate(source, replacement)
            try:
                _solve(case.path, mutant)
            except SmtError as error:
                killed.append(
                    {
                        "mutation_id": mutation_id,
                        "path": case.path.relative_to(ROOT).as_posix(),
                        "detected": True,
                        "reason": str(error),
                        "mutant_sha256": _sha256(mutant.encode("utf-8")),
                    }
                )
            else:
                raise SmtError(
                    f"SMT mutation {mutation_id!r} survived for {case.path.name}"
                )
    return {
        "schema": "ncp.b01-preliminary-smt-result.v2",
        "scope": "narrow-pre-ratification-obligations",
        "z3_version": version,
        "z3_binary_sha256": binary_sha256,
        "claim_boundary": (
            "These finite formulas and satisfiable premises only challenge their "
            "encoded abstractions. They do not establish protocol correctness, code "
            "refinement, cryptographic security, plant safety, or release readiness."
        ),
        "obligations": obligations,
        "mutation_kill_matrix": killed,
        "counts": {
            "files": len(obligations),
            "checks": sum(len(item["checks"]) for item in obligations),
            "mutations_killed": len(killed),
            "mutations_survived": 0,
        },
    }


def _self_test() -> None:
    source = CASES[0].path.read_text(encoding="utf-8")
    hostile = source.replace("(check-sat)", '(echo "sat")\n(check-sat)', 1)
    try:
        _solve(CASES[0].path, hostile)
    except SmtError:
        pass
    else:
        raise SmtError("SMT self-test accepted an output-spoofing command")

    unregistered = source.replace("; EXPECT:", "; UNREGISTERED:", 1)
    try:
        _solve(CASES[0].path, unregistered)
    except SmtError:
        return
    raise SmtError("SMT self-test accepted an unregistered check-sat")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
    result = build_result()
    if result["counts"] != {
        "files": 4,
        "checks": 19,
        "mutations_killed": 13,
        "mutations_survived": 0,
    }:
        raise SmtError("unexpected registered SMT count")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
