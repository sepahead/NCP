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
    total = struct.unpack_from("<I", buf, 8)[0]
    if total != len(buf):
        raise ValueError(f"total_len {total} != buffer {len(buf)}")
    if 12 + n_cols * 16 > len(buf):
        raise ValueError("directory out of bounds")
    cols = []
    for i in range(n_cols):
        base = 12 + i * 16
        name_off = struct.unpack_from("<I", buf, base)[0]
        name_len = struct.unpack_from("<H", buf, base + 4)[0]
        dtype = buf[base + 6]
        n_rows = struct.unpack_from("<I", buf, base + 8)[0]
        data_off = struct.unpack_from("<I", buf, base + 12)[0]
        if dtype not in _DT:
            raise ValueError(f"unknown dtype {dtype}")
        fmt, width, name = _DT[dtype]
        if name_off + name_len > len(buf) or data_off + n_rows * width > len(buf):
            raise ValueError("offset/length out of bounds")
        col_name = buf[name_off : name_off + name_len].decode("utf-8")
        vals = [struct.unpack_from(fmt, buf, data_off + j * width)[0] for j in range(n_rows)]
        cols.append((col_name, name, vals))
    return cols


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
    """Resolve a local $ref (#/$defs/Name) one hop."""
    ref = schema.get("$ref")
    if not ref:
        return schema
    name = ref.split("/")[-1]
    return (root.get("$defs") or {}).get(name, {})


def _type_ok(inst, t: str) -> bool:
    """JSON-Schema primitive type-check (bool is NOT an int/number here)."""
    if t == "null":
        return inst is None
    if t == "boolean":
        return isinstance(inst, bool)
    if t == "integer":
        return isinstance(inst, int) and not isinstance(inst, bool)
    if t == "number":
        return isinstance(inst, (int, float)) and not isinstance(inst, bool)
    if t == "string":
        return isinstance(inst, str)
    if t == "array":
        return isinstance(inst, list)
    if t == "object":
        return isinstance(inst, dict)
    return True  # unknown type keyword: don't block


def validate(inst, schema: dict, root: dict, path: str, errs: list) -> None:
    schema = resolve(schema, root)
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
    props = schema.get("properties")
    if props is not None:
        if not isinstance(inst, dict):
            errs.append(f"{path}: expected object, got {type(inst).__name__}")
            return
        for key in inst:
            if key not in props:
                errs.append(f"{path}.{key}: not a schema property (unknown field)")
        for req in schema.get("required", []):
            if req not in inst:
                errs.append(f"{path}.{req}: required field missing")
        for key, val in inst.items():
            if key in props:
                validate(val, props[key], root, f"{path}.{key}", errs)
    elif schema.get("type") == "array" and isinstance(inst, list):
        item = schema.get("items", {})
        for i, v in enumerate(inst):
            validate(v, item, root, f"{path}[{i}]", errs)
    elif "additionalProperties" in schema and isinstance(inst, dict):
        ap = schema["additionalProperties"]
        if isinstance(ap, dict):
            for k, v in inst.items():
                validate(v, ap, root, f"{path}.{k}", errs)


def main() -> int:
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
