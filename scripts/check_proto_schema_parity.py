#!/usr/bin/env python3
"""Wire conformance: proto <-> JSON-Schema parity guard.

`ncp-core/tests/conformance.rs` already guards the Rust serde types against the
JSON Schemas. This script closes the third side of the triangle: it guards
`proto/ncp.proto` against those same `schemas/*.schema.json`, so the three wire
projections (Rust serde / JSON Schema / protobuf) cannot silently diverge.

What it checks (dependency-free — stdlib only):

  1. FIELD + TYPE/CARDINALITY PARITY (hard): for every object in a schema (the top-level
     message *and* every `$defs` object), the proto `message` of the same
     `title` must declare exactly the same set of field names. Catches a renamed,
     added or dropped field on either side, plus `string` vs `int64`, scalar vs
     repeated, map value types, and message/enum references.

  2. ENUM WIRE-STRING PARITY (hard, where annotated): for every `$defs` enum,
     the proto `enum` of the same title must annotate each value with its JSON
     wire string (`// wire string "..."`), and that set must equal the schema's
     `enum` array. This is the load-bearing check: proto enum *constants*
     (`V_M`, `CURRENT_PA`) are NOT the JSON wire strings (`"V_m"`, `"current_pA"`),
     so ProtoJSON != the NCP JSON wire for enums — the mapping must be explicit.

  3. PROVENANCE DISCRIMINATORS (hard): `ObservationFrame` and `SimProvenance`
     must carry `calibrated_posterior` and `is_simulation_output` (the
     scientific-boundary fields, per CLAUDE.md / RATIONALE.md).

  4. Reports (non-fatal): schema enums modeled as a plain `string` in proto
     (e.g. `mode`, `SimMode`) and proto enums lacking wire-string annotations,
     so the gaps are visible without failing the build.

Exit code is non-zero on any hard failure. Wire into CI next to the cargo gate.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROTO = REPO / "proto" / "ncp.proto"
SCHEMA_DIR = REPO / "schemas"

# Proto enums whose values intentionally carry no `// wire string` annotation
# because the proto message models the field as a plain `string`, not the enum
# (the enum is defined for typed convenience only). Reported, not failed.
_STRING_MODELED_HINT = "modeled as a `string` field in proto"

# Reverse-pass allowlist: proto messages that intentionally have NO standalone
# JSON Schema (so the proto->schema reverse parity check below doesn't flag them).
# Every entry MUST carry a rationale — the default is that a new proto message
# WITHOUT a schema is a drift bug. The JSON Schemas are generated from the Rust
# reference types, so a proto message absent from that generated set is either
# (a) a sub-structure modeled inline
# in a parent schema, or (b) a binary message proven by a different conformance
# path — both must be named here with the reason.
_PROTO_MSG_NO_SCHEMA = {
    # `map<string, ChannelValue>` wrapper. On the JSON wire a SetpointStep is just
    # an object; it is modeled inline as the items of CommandFrame.horizon
    # (`{"type":"object","additionalProperties":{"$ref":"ChannelValue"}}`), so it
    # has no standalone schema `title`.
    "SetpointStep": "map wrapper; modeled inline as CommandFrame.horizon items",
    # Binary bulk message: its payload is a packed little-endian column block
    # (`block` bytes). Conformance is proven by the committed `*.bin` golden
    # vector + the language-agnostic `decode_bulk` reference decoder in
    # check_conformance_vectors.py, not by a JSON-Schema instance. It is
    # deliberately NOT in the JSON-schema corpus.
    "BulkObservation": "binary block message; proven by *.bin vector + bulk codec",
}


def parse_proto(text: str):
    """Return (messages, enums).

    messages: {Name: {field_name: {label, type, number}}}
    enums:    {Name: {CONST: wire_string_or_None}}
    """
    messages: dict[str, dict[str, dict]] = {}
    enums: dict[str, dict[str, str | None]] = {}
    cur_kind: str | None = None
    cur_name: str | None = None

    field_re = re.compile(
        r"(?:(repeated|optional)\s+)?(map\s*<\s*\w+\s*,\s*\w+\s*>|\w+)\s+"
        r"(\w+)\s*=\s*(\d+)\s*;"
    )
    enum_re = re.compile(r"(\w+)\s*=\s*\d+\s*;(?:\s*//\s*wire string\s*\"([^\"]+)\")?")
    open_re = re.compile(r"(message|enum)\s+(\w+)\s*\{(.*)$")

    def add_message_fields(name: str, body: str) -> None:
        # Strip line comments, then capture label/type/name/number for every field.
        for chunk in body.split(";"):
            code = chunk.split("//", 1)[0]
            m = field_re.search(code + ";")
            if m:
                label, field_type, field_name, number = m.groups()
                messages[name][field_name] = {
                    "label": label or "scalar",
                    "type": re.sub(r"\s+", "", field_type),
                    "number": int(number),
                }

    for raw in text.splitlines():
        line = raw.strip()
        if cur_kind is None:
            m = open_re.match(line)
            if not m:
                continue
            cur_kind, cur_name, rest = m.group(1), m.group(2), m.group(3)
            (messages if cur_kind == "message" else enums)[cur_name] = (
                {} if cur_kind == "message" else {}
            )
            if "}" in rest:  # single-line def, e.g. `message SetpointStep { ... }`
                inner = rest[: rest.index("}")]
                if cur_kind == "message":
                    add_message_fields(cur_name, inner)
                cur_kind = cur_name = None
            continue
        # inside a block
        if line.startswith("}"):
            cur_kind = cur_name = None
            continue
        if cur_kind == "message":
            add_message_fields(cur_name, line)
        else:  # enum
            em = enum_re.match(line)
            if em:
                enums[cur_name][em.group(1)] = em.group(2)
    return messages, enums


def walk_schema_objects(schema: dict):
    """Yield (title, kind, payload, node) for the top-level object and every $defs
    entry. kind is 'object' (payload=set of property names) or 'enum'
    (payload=list of enum values)."""
    def emit(node: dict, name: str | None):
        # The type name is the node's `title` if present (Pydantic puts one inside
        # each object), else the `$defs` KEY (schemars names a def by its key, with no
        # internal `title`). Either projection works; the name is what matters.
        title = node.get("title") or name
        if not title:
            return
        if node.get("type") == "object" and "properties" in node:
            yield title, "object", set(node["properties"].keys()), node
        elif isinstance(node.get("x-ncp-known-values"), list):
            yield title, "enum", list(node["x-ncp-known-values"]), node
        elif "enum" in node:
            yield title, "enum", list(node["enum"]), node
        elif "oneOf" in node:
            # schemars renders an enum whose variants carry doc comments as a `oneOf`
            # of {enum:[...]} and {const:"..."} branches. Gather the wire strings from
            # every branch so enum wire-string parity still covers it (e.g. Observable,
            # StimulusKind, whose binary_state / rate_inject variants are documented).
            values: list[str] = []
            for branch in node["oneOf"]:
                if not isinstance(branch, dict):
                    continue
                if isinstance(branch.get("enum"), list):
                    values.extend(branch["enum"])
                elif "const" in branch:
                    values.append(branch["const"])
            if values:
                yield title, "enum", values, node

    yield from emit(schema, None)
    for key, node in (schema.get("$defs") or {}).items():
        if isinstance(node, dict):
            yield from emit(node, key)


def _schema_shape(node: dict, root: dict) -> str:
    """Return a compact JSON-wire shape for one schema field."""
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        target = (root.get("$defs") or {}).get(name, {})
        if "enum" in target or "oneOf" in target or "x-ncp-known-values" in target:
            return f"enum<{name}>"
        return f"message<{name}>"
    if "anyOf" in node:
        branches = [b for b in node["anyOf"] if b.get("type") != "null"]
        if len(branches) == 1:
            return _schema_shape(branches[0], root)
        return "union<" + ",".join(sorted(_schema_shape(b, root) for b in branches)) + ">"
    if node.get("type") == "array":
        return f"repeated<{_schema_shape(node.get('items', {}), root)}>"
    if node.get("type") == "object" and isinstance(node.get("additionalProperties"), dict):
        return f"map<string,{_schema_shape(node['additionalProperties'], root)}>"
    schema_type = node.get("type")
    if isinstance(schema_type, list):
        non_null = [value for value in schema_type if value != "null"]
        if len(non_null) == 1:
            node = dict(node)
            node["type"] = non_null[0]
            return _schema_shape(node, root)
    if schema_type == "integer":
        return "int64"
    if schema_type == "number":
        return "double"
    if schema_type in {"string", "boolean"}:
        return {"boolean": "bool"}.get(schema_type, schema_type)
    if schema_type == "object":
        return "object"
    return f"unknown<{schema_type}>"


def _proto_atom(field_type: str, messages: dict, enums: dict) -> str:
    primitive = {
        "string": "string",
        "bytes": "bytes",
        "bool": "bool",
        "double": "double",
        "float": "double",
        "int64": "int64",
        "sint64": "int64",
        "sfixed64": "int64",
        "uint64": "int64",
        "fixed64": "int64",
        "int32": "int32",
        "sint32": "sint32",
        "sfixed32": "sfixed32",
        "uint32": "uint32",
        "fixed32": "fixed32",
    }
    if field_type in primitive:
        return primitive[field_type]
    if field_type in enums:
        return f"enum<{field_type}>"
    if field_type in messages:
        return f"message<{field_type}>"
    return f"unknown<{field_type}>"


def _proto_shape(field: dict, messages: dict, enums: dict) -> str:
    field_type = field["type"]
    map_match = re.fullmatch(r"map<(\w+),(\w+)>", field_type)
    if map_match:
        key, value = map_match.groups()
        return f"map<{_proto_atom(key, messages, enums)},{_proto_atom(value, messages, enums)}>"

    atom = _proto_atom(field_type, messages, enums)
    # SetpointStep is a proto-only wrapper around `map<string, ChannelValue>`;
    # the JSON projection intentionally renders each horizon step as the map itself.
    if field_type == "SetpointStep":
        wrapper = messages.get("SetpointStep", {})
        if len(wrapper) == 1:
            atom = _proto_shape(next(iter(wrapper.values())), messages, enums)
    if field["label"] == "repeated":
        return f"repeated<{atom}>"
    return atom


def main() -> int:
    messages, enums = parse_proto(PROTO.read_text(encoding="utf-8"))

    failures: list[str] = []
    notes: list[str] = []
    checked_objs = 0
    checked_enums = 0

    for message, fields in messages.items():
        by_number: dict[int, str] = {}
        for field_name, field in fields.items():
            number = field["number"]
            if number in by_number:
                failures.append(
                    f"[proto] {message} reuses field #{number} for {by_number[number]!r} "
                    f"and {field_name!r}"
                )
            by_number[number] = field_name

    # De-dup objects/enums shared across schema files (e.g. Observable, ChannelValue).
    seen_obj: dict[str, frozenset] = {}
    seen_enum: dict[str, tuple] = {}
    schema_titles: set[str] = set()  # every object/enum title the schemas define

    for schema_path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        where = schema_path.name
        for title, kind, payload, node in walk_schema_objects(schema):
            schema_titles.add(title)
            if kind == "object":
                fields = frozenset(payload)
                if seen_obj.get(title) == fields:
                    continue
                seen_obj[title] = fields
                if title not in messages:
                    failures.append(
                        f"[{where}] schema object {title!r} has no `message {title}` in proto"
                    )
                    continue
                proto_fields = set(messages[title])
                checked_objs += 1
                missing = fields - proto_fields  # in schema, not in proto
                extra = proto_fields - fields  # in proto, not in schema
                if missing or extra:
                    failures.append(
                        f"[{where}] field-set drift in {title}: "
                        f"missing-from-proto={sorted(missing)} extra-in-proto={sorted(extra)}"
                    )
                for field_name in sorted(fields & proto_fields):
                    schema_shape = _schema_shape(node["properties"][field_name], schema)
                    proto_shape = _proto_shape(messages[title][field_name], messages, enums)
                    if schema_shape != proto_shape:
                        failures.append(
                            f"[{where}] type/cardinality drift in {title}.{field_name}: "
                            f"schema={schema_shape} proto={proto_shape} "
                            f"(field #{messages[title][field_name]['number']})"
                        )
            else:  # enum
                values = tuple(payload)
                if seen_enum.get(title) == values:
                    continue
                seen_enum[title] = values
                if title not in enums:
                    notes.append(
                        f"[{where}] schema enum {title!r} has no `enum {title}` in proto "
                        f"({_STRING_MODELED_HINT}); wire values={sorted(payload)}"
                    )
                    continue
                proto_vals = enums[title]
                wire = {w for w in proto_vals.values() if w is not None}
                unannotated = [c for c, w in proto_vals.items() if w is None and c.endswith("_UNSPECIFIED") is False]
                if not wire:
                    notes.append(
                        f"[{where}] proto enum {title} carries no `// wire string` "
                        f"annotations; cannot verify against schema {sorted(payload)} "
                        f"(add annotations to enforce)"
                    )
                    continue
                checked_enums += 1
                schema_set = set(payload)
                miss = schema_set - wire
                extra = wire - schema_set
                if miss or extra:
                    failures.append(
                        f"[{where}] enum wire-string drift in {title}: "
                        f"missing-from-proto={sorted(miss)} extra-in-proto={sorted(extra)}"
                    )
                if unannotated:
                    notes.append(
                        f"[{where}] proto enum {title} has unannotated value(s) "
                        f"{unannotated} (no `// wire string`)"
                    )

    # Provenance discriminators must be present on the scientific-boundary types.
    for title in ("ObservationFrame", "SimProvenance"):
        fields = set(messages.get(title, {}))
        for disc in ("calibrated_posterior", "is_simulation_output"):
            if disc not in fields:
                failures.append(
                    f"[provenance] proto message {title} is missing the "
                    f"scientific-boundary field {disc!r}"
                )

    # REVERSE PASS (proto -> schema): a proto message with neither a JSON Schema
    # of the same title NOR an allowlist entry is silent drift — the forward pass
    # above can only see schemas, so a proto-only message would otherwise go
    # unnoticed. Symmetric for enums.
    checked_reverse = 0
    for name in sorted(messages):
        if name in schema_titles or name in _PROTO_MSG_NO_SCHEMA:
            checked_reverse += 1
            continue
        failures.append(
            f"[reverse] proto message {name!r} has no JSON Schema and no "
            f"_PROTO_MSG_NO_SCHEMA allowlist entry (add a schema, or allowlist "
            f"it with a rationale if it is intentionally not a JSON-wire message)"
        )
    for name in sorted(enums):
        if name not in schema_titles:
            notes.append(
                f"[reverse] proto enum {name!r} has no schema enum of that title "
                f"(typed-only convenience enum?)"
            )

    print("proto <-> JSON-Schema parity guard")
    print(
        f"  checked {checked_objs} message field/type sets, {checked_enums} annotated "
        f"enums, {checked_reverse} proto messages (reverse)"
    )
    if notes:
        print("\n  notes (non-fatal):")
        for n in notes:
            print(f"    - {n}")
    if failures:
        print("\n  FAILURES:")
        for f in failures:
            print(f"    ✗ {f}")
        print(f"\nFAIL: {len(failures)} proto<->schema drift(s).")
        return 1
    print("\nPASS: proto field names, types/cardinality, and enum strings are in sync with the JSON Schemas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
