#!/usr/bin/env python3
"""Frozen JSON-wire baseline gate (RELEASE_READINESS blocker #3).

`buf breaking` freezes the *protobuf* wire against a tagged baseline. But NCP's
actual transport is NCP **JSON**, and a break expressible only in the
JSON projection (a removed field, a field that became required, a removed enum
value, a changed type) has no frozen anchor — every other oracle (`schemas/`, the
golden vectors, the behavior corpus, the per-language constants) *regenerates from*
the reference, so it tracks HEAD rather than pinning it.

This gate closes that hole. It distills the load-bearing JSON-wire shape from
`schemas/*.schema.json` — per message-kind field set + which fields are required +
each field's structural type, plus every enum's wire-string value set (the
deserialize-only `unknown` sentinel is `schemars(skip)`, so it is already absent) —
and diffs the CURRENT distillation against every cumulative FROZEN snapshot under
`conformance/baseline/v<major>.<minor>.0/` in the compatible line. The rule is
**additive-only within a stable wire major**:

  FAIL  removed kind / removed field / field type changed / field became required /
        removed requirement / closed-enum value added or removed / the compatibility
        line changed (freeze a new baseline)
  OK    new kind / new optional field / new known value in an explicitly open
        forward-string enum

stdlib only (no jsonschema dep), so it runs anywhere `check.sh` does.

Usage:
  scripts/check_wire_baseline.py                 # diff CURRENT vs the frozen baseline
  scripts/check_wire_baseline.py --freeze DIR    # write a new frozen baseline to DIR
  scripts/check_wire_baseline.py --verify-current-cut
                                                 # current minor snapshot identity
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEMAS = REPO / "schemas"
MESSAGES_RS = REPO / "ncp-core" / "src" / "messages.rs"
GOLDEN_VECTORS = REPO / "conformance" / "vectors"

# Validation keys that define a field's accepted WIRE value set. Everything else in
# a JSON-Schema node (description, default, title, examples) is cosmetic and must
# NOT trip the gate. Changing any retained assertion on an existing field is a wire
# semantic change, even when its primitive JSON type is unchanged.
_STRUCT_KEYS = (
    "type",
    "$ref",
    "const",
    "enum",
    "format",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minContains",
    "maxContains",
    "minProperties",
    "maxProperties",
    "contentEncoding",
    "contentMediaType",
)


def _structural(node):
    """A cosmetic-insensitive signature of a JSON-Schema node's *type*."""
    if not isinstance(node, dict):
        return node
    out = {k: node[k] for k in _STRUCT_KEYS if k in node}
    for child in (
        "items",
        "contains",
        "propertyNames",
        "not",
        "if",
        "then",
        "else",
        "additionalProperties",
        "unevaluatedProperties",
        "unevaluatedItems",
    ):
        if child in node:
            value = node[child]
            out[child] = _structural(value) if isinstance(value, dict) else value
    if isinstance(node.get("prefixItems"), list):
        out["prefixItems"] = [_structural(value) for value in node["prefixItems"]]
    for mapping in (
        "properties",
        "patternProperties",
        "dependentSchemas",
        "$defs",
        "definitions",
    ):
        if isinstance(node.get(mapping), dict):
            out[mapping] = {
                name: _structural(value) for name, value in node[mapping].items()
            }
    if isinstance(node.get("required"), list):
        out["required"] = sorted(node["required"])
    if isinstance(node.get("dependentRequired"), dict):
        out["dependentRequired"] = {
            name: sorted(value) if isinstance(value, list) else value
            for name, value in node["dependentRequired"].items()
        }
    if isinstance(node.get("dependencies"), dict):
        out["dependencies"] = {
            name: sorted(value) if isinstance(value, list) else _structural(value)
            for name, value in node["dependencies"].items()
        }
    for union in ("anyOf", "oneOf", "allOf"):
        if union in node:
            out[union] = [_structural(x) for x in node[union]]
    return out


def _type_repr(field_schema) -> str:
    return json.dumps(_structural(field_schema), sort_keys=True)


def _object_repr(schema: dict) -> str:
    """Object-level constraints without member rows handled additively elsewhere."""
    memberless = dict(schema)
    memberless.pop("properties", None)
    memberless.pop("required", None)
    memberless.pop("$defs", None)
    memberless.pop("definitions", None)
    return _type_repr(memberless)


def _reject_duplicate_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def _load_json(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected regular non-symlink JSON file: {path}")
    return json.loads(path.read_text(), object_pairs_hook=_reject_duplicate_pairs)


def _enum_info(ddef) -> tuple[list, bool] | None:
    """Extract a string-enum's wire-value set from a `$defs` node, or None if it is
    not a string enum. schemars emits two shapes: a plain `{"enum": [...]}` (e.g.
    Mode, SimMode) and — when variants carry doc-comments or a skipped `Unknown` —
    a `{"oneOf": [{"enum": [...]}, {"const": "..."}]}` of string members (the six
    descriptive enums). Collect values from both so a removed value is caught either
    way; the skip-only `unknown` sentinel is already absent from the schema."""
    if isinstance(ddef.get("enum"), list):
        return list(ddef["enum"]), False
    if isinstance(ddef.get("x-ncp-known-values"), list):
        return list(ddef["x-ncp-known-values"]), True
    one = ddef.get("oneOf")
    if isinstance(one, list) and one and all(
        isinstance(m, dict) and m.get("type") == "string" and ("enum" in m or "const" in m)
        for m in one
    ):
        vals: list = []
        for m in one:
            vals.extend(m["enum"] if "enum" in m else [m["const"]])
        return vals, False
    return None


def _wire_pins() -> tuple[str, str]:
    """Read NCP_VERSION + CONTRACT_HASH from the Rust reference (single source)."""
    text = MESSAGES_RS.read_text()
    ver = re.search(r'NCP_VERSION:\s*&str\s*=\s*"([^"]+)"', text)
    h = re.search(r'CONTRACT_HASH:\s*&str\s*=\s*"([^"]+)"', text)
    if not ver or not h:
        sys.exit(f"ERROR: could not read NCP_VERSION/CONTRACT_HASH from {MESSAGES_RS}")
    return ver.group(1), h.group(1)


_WIRE_COMPONENT_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_U64_MAX = 18_446_744_073_709_551_615


def _compatibility_line(version: str) -> str:
    """Return the frozen compatibility anchor for a canonical wire version.

    Pre-1.0 minors are independent lines (`0.8`), while every stable minor shares
    its major anchor (`1.0`, `2.0`). This mirrors the runtime compatibility rule and
    prevents an additive 1.1 advertisement from silently resetting the v1 baseline.
    """
    major, minor = _wire_parts(version)
    return f"{major}.0" if major >= 1 else f"0.{minor}"


def _wire_parts(version: str) -> tuple[int, int]:
    parts = version.split(".")
    if len(parts) not in (1, 2) or any(
        not _WIRE_COMPONENT_RE.fullmatch(part) or int(part) > _U64_MAX for part in parts
    ):
        raise ValueError(f"noncanonical wire version {version!r}")
    return int(parts[0]), int(parts[1]) if len(parts) == 2 else 0


def _cut_name(version: str) -> str:
    major, minor = _wire_parts(version)
    return f"v{major}.{minor}.0"


_BASELINE_DIR_RE = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.0\Z", re.ASCII)


def _applicable_baselines(version: str) -> list[Path]:
    """All cumulative snapshots whose accepted surface this cut must preserve."""
    major, minor = _wire_parts(version)
    root = REPO / "conformance" / "baseline"
    found: list[tuple[int, Path]] = []
    for path in root.iterdir() if root.is_dir() else ():
        match = _BASELINE_DIR_RE.fullmatch(path.name)
        if match is None:
            continue
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"baseline cut path must be a non-symlink directory: {path}")
        baseline_major, baseline_minor = int(match.group(1)), int(match.group(2))
        if major == 0:
            applies = baseline_major == 0 and baseline_minor == minor
        else:
            applies = baseline_major == major and baseline_minor <= minor
        if applies:
            found.append((baseline_minor, path))
    return [path for _, path in sorted(found)]


def build_manifest(schemas_dir: Path) -> dict:
    """Distill the JSON-wire shape from a directory of *.schema.json files."""
    ncp_version, contract_hash = _wire_pins()
    kinds: dict[str, dict] = {}
    enums: dict[str, list[str]] = {}
    open_enums: set[str] = set()
    definitions: dict[str, dict] = {}
    for p in sorted(schemas_dir.glob("*.schema.json")):
        s = _load_json(p)
        props = s.get("properties") or {}
        kind = p.name[: -len(".schema.json")]  # Path.stem leaves a stray ".schema"
        kinds[kind] = {
            "fields": {name: _type_repr(fdef) for name, fdef in props.items()},
            "required": sorted(s.get("required") or []),
            "object": _object_repr(s),
        }
        schema_definitions: dict[str, dict] = {}
        for container_name in ("$defs", "definitions"):
            container = s.get(container_name) or {}
            if not isinstance(container, dict):
                raise ValueError(f"{p.name} {container_name} must be an object")
            for dname, ddef in container.items():
                previous_local = schema_definitions.get(dname)
                if previous_local is not None and previous_local != ddef:
                    raise ValueError(
                        f"{p.name} defines {dname!r} differently in $defs and definitions"
                    )
                schema_definitions[dname] = ddef
        for dname, ddef in schema_definitions.items():
            if not isinstance(ddef, dict):
                continue
            enum_info = _enum_info(ddef)
            if enum_info is not None:
                enum_values, is_open = enum_info
                enum_values = sorted(enum_values)
                previous_enum = enums.get(dname)
                if previous_enum is not None and previous_enum != enum_values:
                    raise ValueError(
                        f"enum definition {dname!r} differs between generated schemas"
                    )
                enums[dname] = enum_values
                previous_open = dname in open_enums
                if previous_enum is not None and previous_open != is_open:
                    raise ValueError(
                        f"enum definition {dname!r} changes open/closed mode between schemas"
                    )
                if is_open:
                    open_enums.add(dname)
            props = ddef.get("properties")
            if isinstance(props, dict):
                definition = {
                    "fields": {name: _type_repr(fdef) for name, fdef in props.items()},
                    "required": sorted(ddef.get("required") or []),
                    "object": _object_repr(ddef),
                }
                previous = definitions.get(dname)
                if previous is not None and previous != definition:
                    raise ValueError(
                        f"nested definition {dname!r} differs between generated schemas"
                    )
                definitions[dname] = definition
    return {
        "ncp_version": ncp_version,
        "contract_hash": contract_hash,
        "kinds": kinds,
        "definitions": definitions,
        "enums": enums,
        "open_enums": sorted(open_enums),
    }


def diff(frozen: dict, current: dict) -> list[str]:
    """Additive-only diff: list the BREAKING changes (empty list = compatible)."""
    fails: list[str] = []

    try:
        frozen_line = _compatibility_line(frozen["ncp_version"])
        current_line = _compatibility_line(current["ncp_version"])
    except (KeyError, TypeError, ValueError) as exc:
        fails.append(f"wire version metadata is invalid: {exc}")
        frozen_line = current_line = None
    if frozen_line != current_line:
        fails.append(
            f"wire version changed {frozen['ncp_version']!r} -> {current['ncp_version']!r}: "
            "that is a NEW compatibility line — a stable minor stays on its major's "
            "baseline; only a new stable major (or pre-1.0 minor) gets a new baseline"
        )

    fk_all, ck_all = frozen["kinds"], current["kinds"]
    for kind, fk in fk_all.items():
        ck = ck_all.get(kind)
        if ck is None:
            fails.append(f"kind {kind!r} was REMOVED (breaking)")
            continue
        if "object" in fk and ck.get("object") != fk["object"]:
            fails.append(
                f"kind {kind!r} OBJECT constraints changed (breaking): "
                f"{fk['object']} -> {ck.get('object')}"
            )
        for fname, ftype in fk["fields"].items():
            if fname not in ck["fields"]:
                fails.append(f"{kind}.{fname} field was REMOVED (breaking)")
            elif ck["fields"][fname] != ftype:
                fails.append(
                    f"{kind}.{fname} WIRE constraints changed (breaking): "
                    f"{ftype} -> {ck['fields'][fname]}"
                )
        for r in sorted(set(ck["required"]) - set(fk["required"])):
            fails.append(
                f"{kind}.{r} became REQUIRED (breaking: an older peer that omits it now fails)"
            )
        for r in sorted(set(fk["required"]) - set(ck["required"])):
            fails.append(
                f"{kind}.{r} stopped being REQUIRED (breaking: a newer sender may omit it "
                "and an older receiver will reject the message)"
            )

    for ename, evals in frozen["enums"].items():
        cvals = current["enums"].get(ename)
        if cvals is None:
            fails.append(f"enum {ename!r} was REMOVED (breaking)")
            continue
        for v in sorted(set(evals) - set(cvals)):
            fails.append(f"enum {ename} value {v!r} was REMOVED (breaking)")
        frozen_open = ename in set(frozen.get("open_enums", []))
        current_open = ename in set(current.get("open_enums", []))
        if frozen_open != current_open:
            fails.append(
                f"enum {ename} changed {'open' if frozen_open else 'closed'} mode to "
                f"{'open' if current_open else 'closed'} (breaking)"
            )
        if not frozen_open:
            for v in sorted(set(cvals) - set(evals)):
                fails.append(
                    f"closed enum {ename} value {v!r} was ADDED (breaking for older receivers)"
                )

    # Nested message shapes are just as wire-visible as top-level kinds. Earlier
    # baseline manifests did not carry this section; treat that as an empty legacy
    # anchor, while every newly frozen baseline gets full recursive coverage.
    for name, frozen_def in frozen.get("definitions", {}).items():
        current_def = current.get("definitions", {}).get(name)
        if current_def is None:
            fails.append(f"nested definition {name!r} was REMOVED (breaking)")
            continue
        if "object" in frozen_def and current_def.get("object") != frozen_def["object"]:
            fails.append(
                f"nested definition {name!r} OBJECT constraints changed (breaking): "
                f"{frozen_def['object']} -> {current_def.get('object')}"
            )
        for field, field_type in frozen_def["fields"].items():
            if field not in current_def["fields"]:
                fails.append(f"{name}.{field} nested field was REMOVED (breaking)")
            elif current_def["fields"][field] != field_type:
                fails.append(
                    f"{name}.{field} nested WIRE constraints changed (breaking): "
                    f"{field_type} -> {current_def['fields'][field]}"
                )
        for required in sorted(set(current_def["required"]) - set(frozen_def["required"])):
            fails.append(
                f"{name}.{required} became REQUIRED (breaking nested contract)"
            )
        for required in sorted(set(frozen_def["required"]) - set(current_def["required"])):
            fails.append(
                f"{name}.{required} stopped being REQUIRED (breaking nested contract)"
            )

    return fails


def freeze(dest: Path) -> int:
    input_symlinks = {
        label: links
        for label, root in (("schemas", SCHEMAS), ("vectors", GOLDEN_VECTORS))
        if (links := _tree_symlinks(root))
    }
    if input_symlinks:
        print(f"ERROR: refusing to freeze symlinked wire inputs: {input_symlinks}", file=sys.stderr)
        return 2
    manifest = build_manifest(SCHEMAS)
    expected = REPO / "conformance" / "baseline" / _cut_name(manifest["ncp_version"])
    if dest.resolve() != expected.resolve():
        print(
            f"ERROR: wire {manifest['ncp_version']} belongs to its per-minor cumulative "
            f"snapshot {expected.relative_to(REPO)}, not {dest}",
            file=sys.stderr,
        )
        return 2
    prior_breaks: list[str] = []
    try:
        applicable = _applicable_baselines(manifest["ncp_version"])
    except ValueError as exc:
        print(f"ERROR: cannot enumerate prior baseline snapshots: {exc}", file=sys.stderr)
        return 1
    for baseline in applicable:
        if baseline.resolve() == dest.resolve():
            continue
        frozen_path = baseline / "wire_manifest.json"
        try:
            frozen = _load_json(frozen_path)
            prior_breaks.extend(
                f"{baseline.name}: {problem}" for problem in diff(frozen, manifest)
            )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            prior_breaks.append(f"{baseline.name}: invalid prior snapshot: {exc}")
    if prior_breaks:
        print("ERROR: refusing to freeze a cut that breaks an earlier snapshot:", file=sys.stderr)
        for problem in prior_breaks:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "wire_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    # Audit snapshot: the exact schemas + golden vectors this baseline distills, so the
    # frozen wire is human-auditable, not just a derived manifest.
    # Snapshot the load-bearing wire artifacts only. Exclude README.md: a directory's
    # README has ../-relative links that are dead from inside the snapshot, and its
    # prose version goes stale against the frozen index.json — it is not part of the
    # wire and only adds rot to the immutable baseline.
    for sub, src in (("schemas", SCHEMAS), ("vectors", GOLDEN_VECTORS)):
        out = dest / sub
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(src, out, ignore=shutil.ignore_patterns("README.md"))
    print(
        f"FROZE wire baseline {manifest['ncp_version']} (hash {manifest['contract_hash']}) "
        f"-> {dest.relative_to(REPO)} : {len(manifest['kinds'])} kinds, "
        f"{len(manifest['definitions'])} nested definitions, {len(manifest['enums'])} enums"
    )
    return 0


def _tree_symlinks(root: Path) -> list[str]:
    if root.is_symlink():
        return ["."]
    if not root.is_dir():
        return []
    return [str(path.relative_to(root)) for path in sorted(root.rglob("*")) if path.is_symlink()]


def _artifact_bytes(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "README.md"
    }


def verify_exact(dest: Path) -> int:
    """Pre-tag proof that the audit snapshot is byte-exactly the release tree.

    Normal post-release checking remains additive-only so a wire line may gain
    optional fields. This stricter mode is intentionally explicit: run it only
    while cutting the immutable baseline tag.
    """
    problems: list[str] = []
    for label, root in (("baseline", dest), ("current schemas", SCHEMAS), ("current vectors", GOLDEN_VECTORS)):
        symlinks = _tree_symlinks(root)
        if symlinks:
            problems.append(f"{label}: symlinks are forbidden: {symlinks}")
    frozen_manifest = dest / "wire_manifest.json"
    if frozen_manifest.is_symlink() or not frozen_manifest.is_file():
        problems.append(f"missing {frozen_manifest}")
    else:
        try:
            expected = build_manifest(SCHEMAS)
            actual = _load_json(frozen_manifest)
            if actual != expected:
                problems.append("wire_manifest.json is not the exact current structural manifest")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            problems.append(f"wire_manifest.json is invalid: {exc}")

    for label, current, frozen in (
        ("schemas", SCHEMAS, dest / "schemas"),
        ("vectors", GOLDEN_VECTORS, dest / "vectors"),
    ):
        current_files = _artifact_bytes(current)
        frozen_files = _artifact_bytes(frozen)
        missing = sorted(set(current_files) - set(frozen_files))
        extra = sorted(set(frozen_files) - set(current_files))
        changed = sorted(
            name
            for name in set(current_files) & set(frozen_files)
            if current_files[name] != frozen_files[name]
        )
        if missing:
            problems.append(f"{label}: snapshot missing {missing}")
        if extra:
            problems.append(f"{label}: snapshot has extra files {extra}")
        if changed:
            problems.append(f"{label}: byte-different files {changed}")

    if problems:
        print("EXACT WIRE SNAPSHOT MISMATCH:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("Re-freeze the unreleased baseline, then verify again before tagging.", file=sys.stderr)
        return 1
    print(f"PASS: frozen audit snapshot {dest.relative_to(REPO)} exactly matches current schemas/vectors.")
    return 0


def verify_current_cut() -> int:
    """Require the current wire minor's own cumulative snapshot to be byte exact."""
    version, _ = _wire_pins()
    return verify_exact(REPO / "conformance" / "baseline" / _cut_name(version))


def check() -> int:
    ncp_version, _ = _wire_pins()
    compatibility_line = _compatibility_line(ncp_version)
    try:
        baselines = _applicable_baselines(ncp_version)
    except ValueError as exc:
        print(f"ERROR: cannot enumerate baseline snapshots: {exc}", file=sys.stderr)
        return 1
    required_current = REPO / "conformance" / "baseline" / _cut_name(ncp_version)
    if required_current not in baselines:
        print(
            f"ERROR: no cumulative snapshot for current wire {ncp_version} at "
            f"{required_current.relative_to(REPO)}.\n"
            f"  Freeze it once wire minor {ncp_version} is final:\n"
            f"    python3 scripts/check_wire_baseline.py --freeze "
            f"{required_current.relative_to(REPO)}",
            file=sys.stderr,
        )
        return 1
    current = build_manifest(SCHEMAS)
    fails: list[str] = []
    frozen_manifests: list[dict] = []
    for baseline in baselines:
        try:
            frozen = _load_json(baseline / "wire_manifest.json")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            fails.append(f"{baseline.name}: invalid snapshot manifest: {exc}")
            continue
        frozen_manifests.append(frozen)
        fails.extend(f"{baseline.name}: {problem}" for problem in diff(frozen, current))
    if fails:
        print(
            f"WIRE BASELINE BREAK vs cumulative {compatibility_line} snapshots "
            f"({len(fails)} breaking change(s)):",
            file=sys.stderr,
        )
        for f in fails:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nThese are NOT additive. Within a wire version the JSON wire may only grow "
            "(new kind / new optional field / new enum value). A genuine break requires a "
            "wire-version bump + a new frozen baseline.",
            file=sys.stderr,
        )
        return 1
    print(
        f"PASS: JSON wire is additively compatible with {len(baselines)} cumulative "
        f"{compatibility_line} snapshot(s) through {baselines[-1].name} "
        f"({len(frozen_manifests[-1]['kinds'])} kinds, "
        f"{len(frozen_manifests[-1]['enums'])} enums)."
    )
    return 0


def self_test() -> int:
    base_field = _type_repr({"type": "string", "pattern": r"^1(?:\.[0-9]+)?$"})
    changed_field = _type_repr({"type": "string", "pattern": r"^1\.0$"})
    object_shape = _type_repr({"type": "object", "additionalProperties": False})
    base = {
        "ncp_version": "1.0",
        "kinds": {
            "sample": {
                "fields": {"ncp_version": base_field},
                "required": ["ncp_version"],
                "object": object_shape,
            }
        },
        "definitions": {},
        "enums": {},
        "open_enums": [],
    }
    changed = copy.deepcopy(base)
    changed["kinds"]["sample"]["fields"]["ncp_version"] = changed_field
    if not diff(base, changed):
        raise AssertionError("pattern-only wire changes must be breaking")
    opened = copy.deepcopy(base)
    opened["kinds"]["sample"]["object"] = _type_repr(
        {"type": "object", "additionalProperties": True}
    )
    if not diff(base, opened):
        raise AssertionError("object acceptance changes must be breaking")
    no_longer_required = copy.deepcopy(base)
    no_longer_required["kinds"]["sample"]["required"] = []
    if not diff(base, no_longer_required):
        raise AssertionError("removing a top-level requirement must be breaking")
    nested_base = copy.deepcopy(base)
    nested_base["definitions"] = {
        "Inner": {
            "fields": {"mode": base_field},
            "required": ["mode"],
            "object": object_shape,
        }
    }
    nested_relaxed = copy.deepcopy(nested_base)
    nested_relaxed["definitions"]["Inner"]["required"] = []
    if not diff(nested_base, nested_relaxed):
        raise AssertionError("removing a nested requirement must be breaking")
    inline_base = _type_repr(
        {
            "type": "object",
            "properties": {"mode": {"type": "string"}},
            "required": ["mode"],
            "patternProperties": {"^x-": {"type": "integer"}},
            "dependentRequired": {"mode": ["detail"]},
        }
    )
    for changed_inline in (
        {
            "type": "object",
            "properties": {"mode": {"type": "number"}},
            "required": ["mode"],
            "patternProperties": {"^x-": {"type": "integer"}},
            "dependentRequired": {"mode": ["detail"]},
        },
        {
            "type": "object",
            "properties": {"mode": {"type": "string"}},
            "patternProperties": {"^y-": {"type": "integer"}},
            "dependentRequired": {"mode": ["other"]},
        },
    ):
        if _type_repr(changed_inline) == inline_base:
            raise AssertionError("inline object members/constraints must affect signatures")
    stable_minor = copy.deepcopy(base)
    stable_minor["ncp_version"] = "1.18446744073709551615"
    if diff(base, stable_minor):
        raise AssertionError("stable-minor advertisements must retain the major baseline")
    added_in_minor = copy.deepcopy(base)
    added_in_minor["ncp_version"] = "1.1"
    added_in_minor["kinds"]["sample"]["fields"]["minor_addition"] = _type_repr(
        {"type": "string"}
    )
    removed_next_minor = copy.deepcopy(base)
    removed_next_minor["ncp_version"] = "1.2"
    if diff(base, removed_next_minor):
        raise AssertionError("the major anchor alone should illustrate the cumulative-chain gap")
    if not diff(added_in_minor, removed_next_minor):
        raise AssertionError("later minors must preserve fields first frozen in an earlier minor")
    closed_enum = copy.deepcopy(base)
    closed_enum["enums"] = {"Mode": ["a"]}
    closed_added = copy.deepcopy(closed_enum)
    closed_added["enums"]["Mode"].append("b")
    if not diff(closed_enum, closed_added):
        raise AssertionError("adding a closed enum value must be breaking")
    open_enum = copy.deepcopy(closed_enum)
    open_enum["open_enums"] = ["Mode"]
    open_added = copy.deepcopy(open_enum)
    open_added["enums"]["Mode"].append("b")
    if diff(open_enum, open_added):
        raise AssertionError("adding a documented open-enum known value must remain additive")
    current_wire = build_manifest(SCHEMAS)
    if current_wire["open_enums"] != ["Mode"]:
        raise AssertionError(
            "Mode must remain the sole open wire enum; got "
            f"{current_wire['open_enums']!r}"
        )
    for enum_name in sorted(current_wire["enums"]):
        if enum_name == "Mode":
            continue
        future_wire = copy.deepcopy(current_wire)
        future_wire["enums"][enum_name].append("__future_value__")
        if not any(
            f"closed enum {enum_name} value" in failure
            for failure in diff(current_wire, future_wire)
        ):
            raise AssertionError(
                f"adding a value to closed wire enum {enum_name} must be breaking"
            )
    if _cut_name("1") != "v1.0.0" or _cut_name("0") != "v0.0.0":
        raise AssertionError("one-component wire versions must normalize to minor zero cuts")
    pre_one = copy.deepcopy(base)
    pre_one["ncp_version"] = "0.8"
    next_pre_one = copy.deepcopy(pre_one)
    next_pre_one["ncp_version"] = "0.9"
    if not diff(pre_one, next_pre_one):
        raise AssertionError("pre-1.0 minor changes must use a new baseline")
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "a.schema.json").write_text(
            json.dumps({"type": "object", "$defs": {"Mode": {"type": "string", "enum": ["a", "b"]}}})
        )
        (root / "z.schema.json").write_text(
            json.dumps({"type": "object", "definitions": {"Mode": {"type": "string", "enum": ["a"]}}})
        )
        try:
            build_manifest(root)
        except ValueError as exc:
            if "enum definition" not in str(exc):
                raise
        else:
            raise AssertionError("conflicting repeated enum definitions must fail closed")
        link = root / "linked.schema.json"
        link.symlink_to(root / "a.schema.json")
        if "linked.schema.json" not in _tree_symlinks(root):
            raise AssertionError("snapshot symlinks must be detected")
    print(
        "OK wire-baseline structural self-test: patterns, inline objects, enum collisions, "
        "symlinks, and stable-major anchoring"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Frozen JSON-wire baseline gate (additive-only).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--freeze", metavar="DIR", help="write a new frozen baseline to DIR")
    mode.add_argument(
        "--verify-exact",
        metavar="DIR",
        help="pre-tag: require snapshot schemas/vectors to byte-match current artifacts",
    )
    mode.add_argument(
        "--verify-current-cut",
        action="store_true",
        help="require the current wire minor's cumulative snapshot to be byte exact",
    )
    mode.add_argument(
        "--self-test",
        action="store_true",
        help="run synthetic structural and compatibility-line regressions",
    )
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.freeze:
        return freeze(Path(args.freeze) if Path(args.freeze).is_absolute() else REPO / args.freeze)
    if args.verify_exact:
        path = Path(args.verify_exact)
        return verify_exact(path if path.is_absolute() else REPO / path)
    if args.verify_current_cut:
        return verify_current_cut()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
