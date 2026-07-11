#!/usr/bin/env python3
"""Conformance corpus validator — golden message vectors vs the JSON Schemas.

Every file in `conformance/vectors/*.json` is a canonical NCP message instance.
This validates each against the schema for its `kind` (field-set + required +
enum membership, recursively resolving local `$ref`/`$defs`), so any peer can run
the same corpus to prove wire conformance. Dependency-free (stdlib only).

This complements:
  - ncp-core/tests/conformance.rs   (Rust serde  <-> schema, type-driven)
  - scripts/check_proto_schema_parity.py (proto <-> schema)
by checking concrete *instances* — the language-agnostic interop corpus.
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO / "schemas"
VECTOR_DIR = REPO / "conformance" / "vectors"

# ── Binary bulk-codec vectors (#6) ──────────────────────────────────────────
# The observation plane may carry bulk numeric arrays as a packed little-endian
# COLUMN BLOCK (ncp-core::bulk; proto `BulkObservation.block`) instead of
# repeated double/int64. This is the language-agnostic reference DECODER for that
# block, so a peer in any language can verify its codec against the committed
# `conformance/vectors/*.bin` (the Rust encoder is byte-pinned to the same files
# by `bulk::tests::matches_committed_golden_vector`).
_BULK_MAGIC = b"NCPB"
_BULK_VERSION = 1
_BULK_MAX_BYTES = 64 * 1024 * 1024
_BULK_MAX_COLUMNS = 4096
_DT = {1: ("<f", 4, "f32"), 2: ("<d", 8, "f64"), 3: ("<i", 4, "i32"), 4: ("<q", 8, "i64")}


def decode_bulk(buf: bytes) -> list[tuple[str, str, list]]:
    """Decode a packed bulk column block -> [(name, dtype, values), ...].

    Fully bounds-checked, like the Rust `BulkBlock::decode`; raises ValueError on
    a malformed/truncated/oversize block rather than over-reading."""
    if len(buf) < 12:
        raise ValueError("bulk block shorter than header")
    if buf[0:4] != _BULK_MAGIC:
        raise ValueError("bad magic")
    if buf[4] != _BULK_VERSION:
        raise ValueError(f"unsupported version {buf[4]}")
    if buf[5] != 0:
        raise ValueError(f"unsupported flags {buf[5]:#x}")
    n_cols = struct.unpack_from("<H", buf, 6)[0]
    if n_cols > _BULK_MAX_COLUMNS:
        raise ValueError("bulk block exceeds 4096 columns")
    total = struct.unpack_from("<I", buf, 8)[0]
    if total != len(buf):
        raise ValueError(f"total_len {total} != buffer {len(buf)}")
    if total > _BULK_MAX_BYTES:
        raise ValueError("bulk block exceeds 64 MiB")
    dir_end = 12 + n_cols * 16
    if dir_end > len(buf):
        raise ValueError("directory out of bounds")
    pending = []
    regions: list[tuple[int, int]] = []
    seen_names: set[str] = set()
    allocation_budget = len(buf)
    for i in range(n_cols):
        base = 12 + i * 16
        name_off = struct.unpack_from("<I", buf, base)[0]
        name_len = struct.unpack_from("<H", buf, base + 4)[0]
        dtype = buf[base + 6]
        if buf[base + 7] != 0:
            raise ValueError("non-zero directory padding")
        n_rows = struct.unpack_from("<I", buf, base + 8)[0]
        data_off = struct.unpack_from("<I", buf, base + 12)[0]
        if dtype not in _DT:
            raise ValueError(f"unknown dtype {dtype}")
        fmt, width, name = _DT[dtype]
        name_end = name_off + name_len
        data_end = data_off + n_rows * width
        if name_off < dir_end or data_off < dir_end:
            raise ValueError("name/data region enters header or directory")
        if name_end > len(buf) or data_end > len(buf):
            raise ValueError("offset/length out of bounds")
        allocation_budget -= name_len + n_rows * width
        if allocation_budget < 0:
            raise ValueError("overlapping columns amplify decoded allocation")
        col_name = buf[name_off : name_off + name_len].decode("utf-8")
        if not col_name or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in col_name):
            raise ValueError("column name must be non-empty control-free UTF-8")
        if col_name in seen_names:
            raise ValueError("duplicate column name")
        seen_names.add(col_name)
        if name_off != name_end:
            regions.append((name_off, name_end))
        if data_off != data_end:
            regions.append((data_off, data_end))
        pending.append((col_name, name, fmt, width, n_rows, data_off))

    regions.sort()
    if any(right[0] < left[1] for left, right in zip(regions, regions[1:])):
        raise ValueError("overlapping name/data regions")

    cols = []
    for col_name, name, fmt, width, n_rows, data_off in pending:
        vals = [struct.unpack_from(fmt, buf, data_off + j * width)[0] for j in range(n_rows)]
        cols.append((col_name, name, vals))
    return cols


def self_test_bulk_decoder() -> list[str]:
    failures: list[str] = []
    golden = (VECTOR_DIR / "bulk_observation.bin").read_bytes()
    try:
        decode_bulk(golden)
    except ValueError as error:
        failures.append(f"canonical bulk fixture rejected: {error}")

    mutations = []
    too_many = bytearray(golden)
    too_many[6:8] = (_BULK_MAX_COLUMNS + 1).to_bytes(2, "little")
    mutations.append(("column ceiling", too_many))
    padded = bytearray(golden)
    padded[12 + 7] = 1
    mutations.append(("directory padding", padded))
    header_overlap = bytearray(golden)
    header_overlap[12:16] = (0).to_bytes(4, "little")
    mutations.append(("header overlap", header_overlap))
    span_overlap = bytearray(golden)
    span_overlap[12 + 16 : 12 + 20] = span_overlap[12:16]
    mutations.append(("span overlap", span_overlap))

    for label, hostile in mutations:
        try:
            decode_bulk(bytes(hostile))
        except (ValueError, UnicodeDecodeError):
            continue
        failures.append(f"{label}: hostile bulk fixture was accepted")
    return failures


# Expected decode of each committed binary vector (the conformance assertion).
_BULK_EXPECTED = {
    "bulk_observation.bin": [
        ("times", "f64", [1.5, 2.5, 9.0]),
        ("senders", "i64", [7, 7, 9]),
    ],
}


def check_bulk_vectors() -> int:
    """Validate every `conformance/vectors/*.bin` decodes to its expected columns.
    Returns the error count."""
    errs = 0
    for bp in sorted(VECTOR_DIR.glob("*.bin")):
        expected = _BULK_EXPECTED.get(bp.name)
        try:
            got = decode_bulk(bp.read_bytes())
        except ValueError as e:
            print(f"  ✗ {bp.name}: decode failed: {e}")
            errs += 1
            continue
        if expected is None:
            print(f"  ? {bp.name}: decoded {len(got)} column(s) (no expectation registered)")
            continue
        if got != expected:
            print(f"  ✗ {bp.name}: decoded {got} != expected {expected}")
            errs += 1
        else:
            cols = ", ".join(f"{n}:{dt}[{len(v)}]" for n, dt, v in got)
            print(f"  ✓ {bp.name} (bulk: {cols})")
    return errs


def load_schemas() -> dict:
    """Map message `kind` -> schema (via properties.kind.const)."""
    by_kind = {}
    for p in SCHEMA_DIR.glob("*.schema.json"):
        s = json.loads(p.read_text(encoding="utf-8"))
        const = (s.get("properties", {}).get("kind", {}) or {}).get("const")
        if const:
            by_kind[const] = s
    return by_kind


def resolve(schema: dict, root: dict) -> dict:
    """Resolve a local $ref (#/$defs/Name), rejecting broken/cyclic refs."""
    seen: set[str] = set()
    while "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/") or ref in seen:
            return {}
        seen.add(ref)
        name = ref.split("/")[-1]
        schema = (root.get("$defs") or {}).get(name, {})
    return schema


def _type_ok(inst, t: str) -> bool:
    """JSON-Schema primitive type-check (bool is NOT an int/number here)."""
    if t == "null":
        return inst is None
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "integer":
        return (
            isinstance(inst, int)
            and not isinstance(inst, bool)
            or isinstance(inst, float)
            and math.isfinite(inst)
            and inst.is_integer()
        )
    if t == "number":
        return (
            isinstance(inst, (int, float))
            and not isinstance(inst, bool)
            and (not isinstance(inst, float) or math.isfinite(inst))
        )
    if t == "string":
        return isinstance(inst, str)
    if t == "array":
        return isinstance(inst, list)
    if t == "object":
        return isinstance(inst, dict)
    return True  # unknown type keyword: don't block


def validate(inst, schema: dict, root: dict, path: str, errs: list) -> None:
    schema = resolve(schema, root)
    if not schema:
        errs.append(f"{path}: unresolved or empty schema")
        return
    # anyOf (nullable unions): valid iff SOME branch validates with zero errors.
    # (The old bare `return` accepted ANYTHING, so every nullable field — units,
    # seed, duration_ms, horizon_dt_ms, recordable, provenance — went unchecked.)
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            sub: list = []
            validate(inst, branch, root, path, sub)
            if not sub:
                return
        errs.append(f"{path}: value {inst!r} matched no anyOf branch")
        return
    if "oneOf" in schema:
        matches = 0
        for branch in schema["oneOf"]:
            sub: list = []
            validate(inst, branch, root, path, sub)
            if not sub:
                matches += 1
        if matches != 1:
            errs.append(f"{path}: value {inst!r} matched {matches} oneOf branches (want exactly 1)")
        return
    # Primitive `type` check — makes anyOf branch-trying meaningful (a {"type":
    # "null"} branch must actually reject a non-null), and catches wrong-typed
    # scalars the structural checks below would otherwise wave through.
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(inst, tt) for tt in types):
            errs.append(f"{path}: expected type {t}, got {type(inst).__name__}")
            return
    enum = schema.get("enum")
    if enum is not None and inst not in enum:
        errs.append(f"{path}: value {inst!r} not in enum {enum}")
        return
    if "const" in schema and inst != schema["const"]:
        errs.append(f"{path}: value {inst!r} != const {schema['const']!r}")
        return
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]:
            errs.append(f"{path}: value {inst!r} < minimum {schema['minimum']!r}")
        if "maximum" in schema and inst > schema["maximum"]:
            errs.append(f"{path}: value {inst!r} > maximum {schema['maximum']!r}")
    if isinstance(inst, str):
        if "minLength" in schema and len(inst) < schema["minLength"]:
            errs.append(f"{path}: string length {len(inst)} < minLength {schema['minLength']}")
        if "maxLength" in schema and len(inst) > schema["maxLength"]:
            errs.append(f"{path}: string length {len(inst)} > maxLength {schema['maxLength']}")
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            errs.append(f"{path}: array length {len(inst)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(inst) > schema["maxItems"]:
            errs.append(f"{path}: array length {len(inst)} > maxItems {schema['maxItems']}")
    props = schema.get("properties")
    if props is not None:
        if not isinstance(inst, dict):
            errs.append(f"{path}: expected object, got {type(inst).__name__}")
            return
        additional = schema.get("additionalProperties", True)
        for key in inst:
            if key not in props:
                if additional is False:
                    errs.append(f"{path}.{key}: additional property is forbidden")
                elif isinstance(additional, dict):
                    validate(inst[key], additional, root, f"{path}.{key}", errs)
        for req in schema.get("required", []):
            if req not in inst:
                errs.append(f"{path}.{req}: required field missing")
        for key, val in inst.items():
            if key in props:
                validate(val, props[key], root, f"{path}.{key}", errs)
    if schema.get("type") == "array" and isinstance(inst, list):
        item = schema.get("items", {})
        for i, v in enumerate(inst):
            validate(v, item, root, f"{path}[{i}]", errs)
    elif props is None and "additionalProperties" in schema and isinstance(inst, dict):
        ap = schema["additionalProperties"]
        if ap is False and inst:
            for key in inst:
                errs.append(f"{path}.{key}: additional property is forbidden")
        if isinstance(ap, dict):
            for k, v in inst.items():
                validate(v, ap, root, f"{path}.{k}", errs)


def self_test_validator() -> list[str]:
    """Pin the JSON-Schema subset this dependency-free validator claims to enforce."""
    failures: list[str] = []

    def expect_valid(instance, schema, label: str) -> None:
        errs: list[str] = []
        validate(instance, schema, schema, label, errs)
        if errs:
            failures.append(f"{label}: expected valid, got {errs}")

    def expect_invalid(instance, schema, label: str) -> None:
        errs: list[str] = []
        validate(instance, schema, schema, label, errs)
        if not errs:
            failures.append(f"{label}: expected invalid, got no errors")

    expect_invalid("wrong", {"type": "string", "const": "right"}, "const")
    expect_invalid(11, {"type": "integer", "maximum": 10}, "maximum")
    expect_valid(1.0, {"type": "integer"}, "integral float is a JSON-Schema integer")
    expect_invalid(1.5, {"type": "integer"}, "fractional float is not an integer")
    expect_invalid(True, {"type": "integer"}, "boolean is not an integer")
    expect_invalid("", {"type": "string", "minLength": 1}, "minLength")
    expect_invalid(
        {"known": 1, "extra": 2},
        {"type": "object", "properties": {"known": {"type": "integer"}}, "additionalProperties": False},
        "additionalProperties=false",
    )
    expect_valid(
        {"known": 1, "future": {"anything": True}},
        {"type": "object", "properties": {"known": {"type": "integer"}}},
        "unknown fields allowed by default",
    )
    expect_valid("x", {"anyOf": [{"type": "null"}, {"type": "string"}]}, "anyOf")
    expect_invalid(True, {"oneOf": [{"type": "string"}, {"type": "integer"}]}, "oneOf")
    return failures


def main() -> int:
    self_failures = self_test_validator()
    self_failures.extend(self_test_bulk_decoder())
    if self_failures:
        for failure in self_failures:
            print(f"  ✗ validator self-test: {failure}")
        return 1
    by_kind = load_schemas()
    vectors = sorted(VECTOR_DIR.glob("*.json"))
    if not vectors:
        print(f"no vectors in {VECTOR_DIR}")
        return 1
    total_errs = 0
    covered: set = set()
    for vp in vectors:
        inst = json.loads(vp.read_text(encoding="utf-8"))
        kind = inst.get("kind")
        schema = by_kind.get(kind)
        if schema is None:
            print(f"  ✗ {vp.name}: no schema for kind {kind!r}")
            total_errs += 1
            continue
        covered.add(kind)
        errs: list = []
        validate(inst, schema, schema, vp.stem, errs)
        if errs:
            print(f"  ✗ {vp.name} ({kind}):")
            for e in errs:
                print(f"      {e}")
            total_errs += len(errs)
        else:
            print(f"  ✓ {vp.name} ({kind})")

    # Corpus-coverage gate: every schema `kind` MUST have at least one golden
    # vector, else the corpus silently omits message types from interop proof.
    uncovered = sorted(set(by_kind) - covered)
    if uncovered:
        print(f"  ✗ corpus coverage: no JSON vector for kind(s): {', '.join(uncovered)}")
        total_errs += len(uncovered)
    else:
        print(f"  ✓ corpus coverage: all {len(by_kind)} schema kind(s) have a vector")

    # Binary bulk-codec vectors (#6) — packed little-endian column blocks.
    bulk_errs = check_bulk_vectors()
    total_errs += bulk_errs
    n_bin = len(list(VECTOR_DIR.glob("*.bin")))

    print()
    if total_errs:
        print(f"FAIL: {total_errs} conformance error(s).")
        return 1
    print(
        f"PASS: {len(vectors)} JSON + {n_bin} binary golden vectors conform "
        f"(schemas + bulk codec)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
