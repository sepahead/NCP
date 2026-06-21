#!/usr/bin/env python3
"""Schema-default safety guard: every committed JSON-Schema field DEFAULT must equal
the NORMATIVE Rust reference (ncp-core serde types).

The committed `schemas/*.schema.json` are currently generated from engram's Pydantic
models (a consumer); the Rust `ncp-core` serde types are the conformance-locked
*reference implementation* of the wire. A field default that disagrees between the two
is a real cross-language bug — and a SAFETY one for the action plane: e.g. an omitted
`CommandFrame.mode` must fail-safe to `"hold"` (ncp_core `default_command_mode`), never
`"active"`. The proto<->schema parity guard checks field-SETS and enum values but NOT
defaults, so this closes that gap until NCP fully owns schema generation (gen-schemas).

How: run the proto-first generator (`cargo run -p ncp-core --features schema --bin
gen-schemas`) to a temp dir — its output IS the Rust reference — then assert every
message's top-level field `default` matches the committed schema's. A default present
on only one side (e.g. `ncp_version`, which schemars does not evaluate from a serde
default fn) is reported as a note, not a failure.

Usage: python3 scripts/check_schema_defaults.py
Exit: 0 = all defaults agree; 1 = a mismatch (a real bug); 2 = setup/tooling error.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMITTED = REPO / "schemas"


def _field_defaults(schema: dict) -> dict[str, object]:
    """Top-level message fields that declare a `default`, name -> default value."""
    props = schema.get("properties", {})
    return {name: spec["default"] for name, spec in props.items() if isinstance(spec, dict) and "default" in spec}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["cargo", "run", "-q", "-p", "ncp-core", "--features", "schema", "--bin", "gen-schemas", "--", tmp],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write("ERROR: gen-schemas (the Rust reference) failed to run:\n")
            sys.stderr.write(proc.stderr[-2000:])
            return 2
        ref_dir = Path(tmp)

        problems: list[str] = []
        notes: list[str] = []
        checked = 0
        for committed_path in sorted(COMMITTED.glob("*.schema.json")):
            ref_path = ref_dir / committed_path.name
            if not ref_path.exists():
                notes.append(f"{committed_path.name}: no reference schema generated (skipped)")
                continue
            committed = json.loads(committed_path.read_text())
            reference = json.loads(ref_path.read_text())
            c_def = _field_defaults(committed)
            r_def = _field_defaults(reference)
            for field in sorted(set(c_def) & set(r_def)):
                checked += 1
                if c_def[field] != r_def[field]:
                    problems.append(
                        f"{committed_path.name}: field {field!r} default committed={c_def[field]!r} "
                        f"!= Rust reference={r_def[field]!r}"
                    )
            for field in sorted(set(c_def) ^ set(r_def)):
                notes.append(f"{committed_path.name}: field {field!r} has a default on only one side (not compared)")

    print(f"Schema-default safety guard: compared {checked} field defaults against the Rust reference.")
    for n in notes:
        print(f"  note: {n}")
    if problems:
        sys.stderr.write("\nDEFAULT MISMATCH (committed schema disagrees with the normative Rust reference):\n")
        for p in problems:
            sys.stderr.write(f"  - {p}\n")
        sys.stderr.write("\nA safety-relevant default (e.g. CommandFrame.mode) MUST match ncp-core. Fix the\n")
        sys.stderr.write("schema source (Pydantic model) to match the Rust reference, then regenerate.\n")
        return 1
    print("OK: all committed schema defaults match the Rust reference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
