#!/usr/bin/env python3
"""Keep spec/ncp2-rules.json, the specification, both SDKs, and the Lean model equal.

spec/ncp2-rules.json states the outcomes, codes, local codes, and limits of NCP 2 as data. This
script requires:

1. the codes table of spec/NCP-2.md, section 7.5, to give each code the outcome of the data;
2. the Python constants (python/ncp/messages.py, frame.py, transcript.py) to equal the data;
3. the Rust constants (rust/src/messages.rs, frame.rs, transcript.rs) to equal the data;
4. the Lean `Code` type (formal/NCP2/Model.lean) and the oracle's code names (formal/Oracle.lean)
   to name exactly the codes that an owner sends in reply to a decoded request.

Usage: check_ncp2_rules.py   (standard library only)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from ncp import frame as F  # noqa: E402
from ncp import messages as M  # noqa: E402
from ncp import transcript as T  # noqa: E402

failures: list[str] = []


def expect(condition: bool, text: str) -> None:
    if not condition:
        failures.append(text)


def rust_constant(source: str, name: str) -> str | None:
    match = re.search(rf"pub const {name}: [^=]+= (.+?);", source, re.DOTALL)
    return match.group(1).strip() if match else None


def rust_number(source: str, name: str) -> int | None:
    value = rust_constant(source, name)
    if value is None:
        return None
    value = value.replace("_", "")
    if value == "(1 << 53) - 1":
        return 2**53 - 1
    return int(value) if value.isdigit() else None


def rust_strings(source: str, name: str) -> list[str] | None:
    value = rust_constant(source, name)
    return None if value is None else re.findall(r'"([a-z_.]+)"', value)


def camel(code: str) -> str:
    head, *rest = code.split("_")
    return head + "".join(part.capitalize() for part in rest)


def main() -> int:
    rules = json.loads((ROOT / "spec" / "ncp2-rules.json").read_text(encoding="utf-8"))
    codes = rules["codes"]
    rejected = {c["code"] for c in codes if c["outcome"] == "rejected"}
    declined = {c["code"] for c in codes if c["outcome"] == "declined"}
    ended = {c["code"]: c["client"] for c in codes if c["outcome"] == "ended"}  # the client's verdicts
    local = {c["code"] for c in rules["local_codes"]}
    limits = rules["limits"]
    expect(set(rules["outcomes"]) == set(M.OUTCOMES), "the outcomes of the data differ from python/ncp/messages.py")
    for entry in codes:  # rules 7.6.3 and 7.6.4: the client's verdicts that follow from the outcome
        if entry["outcome"] == "rejected":
            want = "no" if entry.get("open") else "unknown"
            expect(entry["client"] == want, f"the client's verdict on {entry['code']} must be {want} (rule 7.6.4)")
        elif entry["outcome"] == "declined":
            expect(entry["client"] == "no", f"the client's verdict on {entry['code']} must be no (rule 7.6.3)")

    # 1. The specification's codes table.
    spec = (ROOT / "spec" / "NCP-2.md").read_text(encoding="utf-8")
    table = spec.split("### 7.5 Codes", 1)[1].split("\n\n", 2)[1]
    rows = [line for line in table.split("\n") if line.startswith("| `")]
    seen: dict[str, set[str]] = {}
    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        outcome = re.match(r"`([a-z]+)`", cells[1])
        for code in re.findall(r"`([a-z_]+)`", cells[0]):
            seen.setdefault(code, set()).add(outcome.group(1) if outcome else "?")
    for entry in codes:
        expect(entry["outcome"] in seen.get(entry["code"], set()),
               f"spec 7.5: the code {entry['code']} has no row with the outcome {entry['outcome']}")
    expect(set(seen) == {c["code"] for c in codes}, f"spec 7.5 names other codes: {sorted(set(seen) ^ {c['code'] for c in codes})}")

    # The specification's table of limits, section 12.
    labels = {
        "Bound before `open` completes": "handshake_bound",
        "Largest session bound": "max_bound",
        "Default session bound in the reference SDKs": "default_bound",
        "JSON region": "max_json",
        "JSON nesting": "max_depth",
        "Integer magnitude": "max_integer",
        "Attachments in a frame": "max_attachments",
        "Operation name, feature name, code": "max_name",
        "Stream identifier": "max_stream_identifier",
        "Features in an `open` request": "max_features",
        "Member `run` of an `open` request": "max_run",
        "Member `detail` of a response, as the reference owners write it": "max_detail",
        "Dimensions of an array shape": "max_rank",
        "Transcript header": "max_transcript_header",
    }
    section = spec.split("## 12. Limits", 1)[1].split("\n## ", 1)[0]
    stated: dict[str, int] = {}
    for line in section.split("\n"):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] in ("Limit", "---"):
            continue
        if cells[0] not in labels:
            expect(False, f"spec 12 has a limit that the data does not name: {cells[0]}")
            continue
        number = 2**53 - 1 if cells[1].startswith("2^53") else int(re.match(r"[0-9,]+", cells[1]).group(0).replace(",", ""))
        stated[labels[cells[0]]] = number
    expect(stated == limits, f"spec 12 states other limits than the data: {sorted(set(stated.items()) ^ set(limits.items()))}")

    # 2. Python.
    expect(set(M.REJECTION_CODES) == rejected, "python REJECTION_CODES differ from the data")
    expect(set(M.DECLINE_CODES) == declined, "python DECLINE_CODES differ from the data")
    expect(dict(M.ENDING_CODES) == ended, "python ENDING_CODES differ from the data")
    expect(set(M.LOCAL_CODES) == local, "python LOCAL_CODES differ from the data")
    python_limits = {
        "handshake_bound": F.HANDSHAKE_BOUND, "max_bound": F.MAX_BOUND, "default_bound": F.DEFAULT_BOUND,
        "max_json": F.MAX_JSON, "max_depth": F.MAX_DEPTH, "max_integer": F.MAX_INTEGER,
        "max_attachments": F.MAX_ATTACHMENTS, "max_name": M.MAX_NAME, "max_features": M.MAX_FEATURES,
        "max_transcript_header": T.MAX_HEADER, "max_run": M.MAX_RUN, "max_detail": M.MAX_DETAIL,
        "max_rank": F.MAX_RANK,
    }
    for name, value in python_limits.items():
        expect(limits[name] == value, f"python limit {name} is {value}, the data says {limits[name]}")
    expect(M.is_stream("s" * limits["max_stream_identifier"]) and not M.is_stream("s" * (limits["max_stream_identifier"] + 1)),
           "python stream identifiers do not stop at max_stream_identifier")

    # 3. Rust.
    messages = (ROOT / "rust" / "src" / "messages.rs").read_text(encoding="utf-8")
    frame = (ROOT / "rust" / "src" / "frame.rs").read_text(encoding="utf-8")
    transcript = (ROOT / "rust" / "src" / "transcript.rs").read_text(encoding="utf-8")
    expect(set(rust_strings(messages, "REJECTION_CODES") or []) == rejected, "rust REJECTION_CODES differ from the data")
    expect(set(rust_strings(messages, "DECLINE_CODES") or []) == declined, "rust DECLINE_CODES differ from the data")
    expect(set(rust_strings(messages, "LOCAL_CODES") or []) == local, "rust LOCAL_CODES differ from the data")
    ending = rust_constant(messages, "ENDING_CODES") or ""
    rust_ended = {code: value.lower() for code, value in re.findall(r'\("([a-z_]+)", Executed::([A-Za-z]+)\)', ending)}
    expect(rust_ended == ended, f"rust ENDING_CODES differ from the data: {rust_ended}")
    rust_limits = {
        "handshake_bound": rust_number(frame, "HANDSHAKE_BOUND"), "max_bound": rust_number(frame, "MAX_BOUND"),
        "default_bound": rust_number(frame, "DEFAULT_BOUND"), "max_json": rust_number(frame, "MAX_JSON"),
        "max_depth": rust_number(frame, "MAX_DEPTH"), "max_integer": rust_number(frame, "MAX_INTEGER"),
        "max_attachments": rust_number(frame, "MAX_ATTACHMENTS"), "max_name": rust_number(messages, "MAX_NAME"),
        "max_features": rust_number(messages, "MAX_FEATURES"), "max_transcript_header": rust_number(transcript, "MAX_HEADER"),
        "max_run": rust_number(messages, "MAX_RUN"), "max_detail": rust_number(messages, "MAX_DETAIL"),
        "max_rank": rust_number(frame, "MAX_RANK"),
    }
    for name, value in rust_limits.items():
        expect(limits[name] == value, f"rust limit {name} is {value}, the data says {limits[name]}")

    # 4. Lean: the codes that an owner sends in reply to a decoded request (bad_frame belongs to
    # the bindings, so the model has no decoded request for it).
    model = (ROOT / "formal" / "NCP2" / "Model.lean").read_text(encoding="utf-8")
    block = model.split("inductive Code where", 1)[1].split("deriving", 1)[0]
    lean_codes = set(re.findall(r"\|\s*([a-zA-Z]+)", block))
    owner_codes = {c["code"] for c in codes if c["code"] != "bad_frame"}
    expect(lean_codes == {camel(code) for code in owner_codes},
           f"the Lean Code type differs from the data: {sorted(lean_codes ^ {camel(c) for c in owner_codes})}")
    oracle = (ROOT / "formal" / "Oracle.lean").read_text(encoding="utf-8")
    named = dict(re.findall(r'\.([a-zA-Z]+) => "([a-z_]+)"', oracle))
    expect(all(named.get(camel(code)) == code for code in owner_codes), "formal/Oracle.lean names a code differently")

    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print(f"rules: {len(codes)} codes, {len(local)} local codes, and {len(limits)} limits agree in the data, the "
          "specification, both SDKs, and the Lean model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
