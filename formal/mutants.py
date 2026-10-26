#!/usr/bin/env python3
"""Measure the strength of the NCP 2 claims by mutating the owner model.

Each mutant changes one rule in NCP2/Model.lean in a temporary copy of formal/. The mutated model
must still compile, so that a failure comes from a proof and not from a broken edit, and the build
of Audit.lean, which proves every claim of Statements.lean, must then fail.

A failed build does not say which claims lost their proofs: once a module fails, Lake does not
build the modules that import it. The script therefore replaces each failing proof with `sorry` and
builds again, until the build succeeds, and then reads the axioms of every claim. A claim whose
proof now uses `sorryAx` is a claim whose proof the mutant broke, and the claim that the mutant
targets must be among them.

The last mutant rejects every call. Every other claim must still prove for it, with the standard
axioms only, and exactly the two claims that need an executed call must lose their proofs: the
progress claim, and the example in which `seq_stale` answers a request that executed. So the
safety claims alone allow an owner that executes nothing, and the progress claim rules it out.

`--table` prints, after the run, a Markdown table of which claims each defect breaks.
`--check README.md` also requires that table to appear in the README between the markers
`<!-- mutant-table:begin -->` and `<!-- mutant-table:end -->`, so the published table cannot drift.
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
# Column headings of the published table, in the order of MUTANTS.
LABELS = {
    "skips_ack_check": "no ack check",
    "accepts_gaps": "gaps accepted",
    "executes_after_end": "runs after end",
    "reexecutes_retransmission": "re-executes copy",
    "rejection_changes_state": "rejection changes state",
    "rejects_every_call": "rejects every call",
}
TABLE_BEGIN = "<!-- mutant-table:begin -->"
TABLE_END = "<!-- mutant-table:end -->"
EXECUTES_NOTHING = "rejects_every_call"
# The claims that need an executed call: for an owner that executes nothing, exactly these fail.
NEEDS_EXECUTION = {"FaultFreeProgress", "StaleMayHaveExecuted"}
STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}

ERROR_LINE = re.compile(r"error: ([A-Za-z0-9_./]+\.lean):(\d+):\d+")
DECLARATION = re.compile(r"^(?:private )?theorem ([A-Za-z0-9_.']+)")
CLAIM = re.compile(r"^def ([A-Z][A-Za-z0-9]*) : Prop", re.MULTILINE)
AXIOMS = re.compile(
    r"^'NCP2\.Audit\.([A-Za-z0-9_]+)' (?:depends on axioms: \[(.*)\]|does not depend on any axioms)",
    re.MULTILINE)


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


def stub(work: Path, path: str, name: str) -> bool:
    """Replace the proof of theorem `name` in `path` with `sorry`. False if its layout is unknown.

    A declaration ends before the next blank or unindented line. Its proof starts at the first
    line indented by exactly two spaces; signature lines are indented by four.
    """
    file = work / path
    lines = file.read_text(encoding="utf-8").splitlines()
    start = next((i for i, text in enumerate(lines)
                  if (match := DECLARATION.match(text)) and match.group(1) == name), None)
    if start is None:
        return False
    end = start + 1
    while end < len(lines) and lines[end].strip() and lines[end][0] == " ":
        end += 1
    body = next((i for i in range(start + 1, end)
                 if lines[i].startswith("  ") and not lines[i].startswith("   ")), None)
    if body is None:
        return False
    head = lines[body - 1].rstrip()
    if lines[body].startswith("  |"):
        head += " := sorry"
    elif head.endswith(":= by"):
        head = head[: -len("by")] + "sorry"
    elif head.endswith(":="):
        head += " sorry"
    else:
        return False
    lines[body - 1: end] = [head]
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def claim_axioms(work: Path) -> dict[str, set[str]] | None:
    """The axioms of each claim's proof in a built Audit.lean, or None if a proof fails."""
    audit = run(["lake", "env", "lean", "Audit.lean"], work)
    if audit.returncode != 0:
        return None
    return {name: {axiom.strip() for axiom in (axioms or "").split(",") if axiom.strip()}
            for name, axioms in AXIOMS.findall(audit.stdout)}


def table(claims: list[str], lost_by_mutant: dict[str, list[str]]) -> str:
    """Rows are claims, columns are defects; x marks a claim whose proof the defect breaks."""
    names = [name for name, *_ in MUTANTS]
    lines = ["| Claim | " + " | ".join(LABELS[name] for name in names) + " |",
             "| --- |" + " :---: |" * len(names)]
    for claim in claims:
        marks = ["x" if claim in lost_by_mutant[name] else "" for name in names]
        lines.append(f"| `{claim}` | " + " | ".join(marks) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    arguments = sys.argv[1:]
    readme = None
    if arguments == ["--table"]:
        pass
    elif len(arguments) == 2 and arguments[0] == "--check":
        readme = FORMAL / arguments[1]
    elif arguments:
        print("usage: mutants.py [--table | --check README.md]", file=sys.stderr)
        return 2
    model = (FORMAL / "NCP2" / "Model.lean").read_text(encoding="utf-8")
    claims = CLAIM.findall((FORMAL / "Statements.lean").read_text(encoding="utf-8"))
    lost_by_mutant: dict[str, list[str]] = {}
    failures = 0
    with tempfile.TemporaryDirectory(prefix="ncp2-mutants-") as temporary:
        for name, old, new, target in MUTANTS:
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
            if audit.returncode == 0:
                print(f"mutant {name:28} SURVIVED: every claim still proves", file=sys.stderr)
                failures += 1
                continue
            if not broken_declarations(work, audit.stdout + audit.stderr):
                print(f"mutant {name:28} failed without a proof error", file=sys.stderr)
                failures += 1
                continue
            # Lake stops at the first failing module, so the failing proofs appear a layer at a time.
            broken: list[tuple[str, str]] = []
            while audit.returncode != 0:
                fresh = [item for item in broken_declarations(work, audit.stdout + audit.stderr)
                         if item not in broken]
                if not fresh or not all(stub(work, path, theorem) for path, theorem in fresh):
                    break
                broken += fresh
                audit = run(["lake", "build", "Audit"], work)
            names = ", ".join(f"{path}:{theorem}" for path, theorem in broken)
            if audit.returncode != 0:
                print(f"mutant {name:28} could not replace every failing proof ({names})",
                      file=sys.stderr)
                failures += 1
                continue
            axioms = claim_axioms(work)
            if axioms is None or any(claim[0].lower() + claim[1:] not in axioms for claim in claims):
                print(f"mutant {name:28} proofs still fail after the broken ones were replaced",
                      file=sys.stderr)
                failures += 1
                continue
            lost = [claim for claim in claims if "sorryAx" in axioms[claim[0].lower() + claim[1:]]]
            lost_by_mutant[name] = lost
            kept = [claim for claim in claims if claim not in lost]
            nonstandard = [claim for claim in kept
                           if not axioms[claim[0].lower() + claim[1:]] <= STANDARD_AXIOMS]
            if target not in lost:
                print(f"mutant {name:28} did not break the proof of {target} ({names})",
                      file=sys.stderr)
                failures += 1
            elif name == EXECUTES_NOTHING and (set(lost) != NEEDS_EXECUTION or nonstandard):
                print(f"mutant {name:28} broke more than the claims that need execution: "
                      f"{', '.join(lost)}", file=sys.stderr)
                failures += 1
            elif name == EXECUTES_NOTHING:
                print(f"mutant {name:28} caught: only {' and '.join(lost)} lose their proofs; "
                      f"the other {len(kept)} claims still prove ({names})")
            else:
                print(f"mutant {name:28} caught: {target} and {len(lost) - 1} other claims lose "
                      f"their proofs ({names})")
    if failures:
        print(f"{failures} mutant(s) were not caught", file=sys.stderr)
        return 1
    print(f"all {len(MUTANTS)} model mutants break the proof of the claim that they target")
    generated = table(claims, lost_by_mutant)
    if arguments == ["--table"]:
        print(generated, end="")
    if readme is not None:
        text = readme.read_text(encoding="utf-8")
        if text.count(TABLE_BEGIN) != 1 or text.count(TABLE_END) != 1:
            print(f"{readme.name}: the mutant-table markers must appear exactly once", file=sys.stderr)
            return 1
        published = text.split(TABLE_BEGIN, 1)[1].split(TABLE_END, 1)[0].strip("\n") + "\n"
        if published != generated:
            print(f"{readme.name}: the published mutant table differs from the run:\n{generated}",
                  file=sys.stderr)
            return 1
        print(f"{readme.name}: the published mutant table matches the run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
