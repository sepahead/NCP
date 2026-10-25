#!/usr/bin/env python3
"""Measure the strength of the NCP 2 claims by mutating the owner model.

Each mutant changes one rule in NCP2/Model.lean in a temporary copy of formal/. The mutated model
must still compile, so that a failure comes from a proof and not from a broken edit, and the build
of Audit.lean, which proves every claim of Statements.lean, must then fail. A claim set that no
mutant can break would say little about the owner.

The last mutant rejects every call. It must pass every safety claim and fail only the progress
claim: this shows that the safety claims alone allow an owner that executes nothing.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FORMAL = Path(__file__).resolve().parent

# (name, text in NCP2/Model.lean, replacement, claim whose proof must fail)
MUTANTS = (
    ("skips_ack_check",
     "      if keptId ≠ some ack then (o, reject H r .ackMismatch)",
     "      if False then (o, reject H r .ackMismatch)",
     "Acknowledged"),
    ("accepts_gaps",
     "  else if r.seq > o.high + 1 then (o, reject H r .seqGap)",
     "  else if False then (o, reject H r .seqGap)",
     "InOrder"),
    ("executes_after_end",
     "  else if o.ended then (o, reject H r .sessionEnded)",
     "  else if False then (o, reject H r .sessionEnded)",
     "NothingAfterEnd"),
    ("reexecutes_retransmission",
     "        if H (.req r) = H (.req k.request) then (o, k.response)",
     "        if H (.req r) = H (.req k.request) then accept H o r b.result",
     "AtMostOnce"),
    ("rejection_changes_state",
     "    | none => (o, reject H r .ackMissing)",
     "    | none => ({ o with high := r.seq }, reject H r .ackMissing)",
     "RejectedChangesNothing"),
    ("rejects_every_call",
     "          else if b.valid = false then (o, reject H r .bodyInvalid)",
     "          else if True then (o, reject H r .bodyInvalid)",
     "FaultFreeProgress"),
)

ERROR_LINE = re.compile(r"error: ([A-Za-z0-9_./]+\.lean):(\d+):\d+")
DECLARATION = re.compile(r"^(?:private )?theorem ([A-Za-z0-9_.']+)")
# Declarations that need requests to execute: the progress lemmas, the progress claim, and the
# concrete witness that seq_stale can answer an executed request. Every other declaration is a
# safety proof and must survive an owner that executes nothing.
NEEDS_EXECUTION = {
    ("NCP2/Progress.lean", "step_call"),
    ("NCP2/Progress.lean", "step_open"),
    ("NCP2/Client.lean", "seqStale_after_execution"),
    ("Audit.lean", "honestCalls_log"),
    ("Audit.lean", "faultFreeProgress"),
}


def broken_declarations(work: Path, output: str) -> list[tuple[str, str]]:
    """Map each error line to the theorem that contains it."""
    found = set()
    for path, line in ERROR_LINE.findall(output):
        lines = (work / path).read_text(encoding="utf-8").splitlines()
        name = "?"
        for text in reversed(lines[: int(line)]):
            match = DECLARATION.match(text)
            if match:
                name = match.group(1)
                break
        found.add((path, name))
    return sorted(found)


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def main() -> int:
    model = (FORMAL / "NCP2" / "Model.lean").read_text(encoding="utf-8")
    failures = 0
    with tempfile.TemporaryDirectory(prefix="ncp2-mutants-") as temporary:
        for name, old, new, claim in MUTANTS:
            if model.count(old) != 1:
                print(f"mutant {name:28} anchor not found exactly once", file=sys.stderr)
                return 2
            work = Path(temporary) / name
            shutil.copytree(FORMAL, work, ignore=shutil.ignore_patterns("mutants.py", "__pycache__"))
            (work / "NCP2" / "Model.lean").write_text(model.replace(old, new, 1), encoding="utf-8")
            if run(["lake", "build", "NCP2.Model"], work).returncode != 0:
                print(f"mutant {name:28} broke the model itself (not a valid mutant)", file=sys.stderr)
                failures += 1
                continue
            audit = run(["lake", "build", "Audit"], work)
            broken = broken_declarations(work, audit.stdout + audit.stderr)
            names = ", ".join(f"{path}:{theorem}" for path, theorem in broken)
            if audit.returncode == 0:
                print(f"mutant {name:28} SURVIVED: every claim still proves", file=sys.stderr)
                failures += 1
            elif not broken:
                print(f"mutant {name:28} failed without a proof error", file=sys.stderr)
                failures += 1
            elif claim == "FaultFreeProgress" and not set(broken) <= NEEDS_EXECUTION:
                print(f"mutant {name:28} broke a safety proof too: {names}", file=sys.stderr)
                failures += 1
            else:
                print(f"mutant {name:28} caught: {claim} no longer proves ({names})")
    if failures:
        print(f"{failures} mutant(s) were not caught", file=sys.stderr)
        return 1
    print(f"all {len(MUTANTS)} model mutants break a proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
