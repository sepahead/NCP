#!/usr/bin/env python3
"""Validate coordination JSON with one pinned Draft 2020-12 implementation.

This gate validates structure only. It does not establish external authorship,
organizational independence, live execution, or release authorization.
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

from bounded_json import (
    BoundedJsonError,
    FileSnapshotLimits,
    JsonLimits,
    parse_json_bytes,
    read_bounded_regular_file,
    validate_native_json_tree,
)
from bounded_json import (
    run_self_test as run_bounded_json_self_test,
)
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
LEDGER_SCHEMA = ROOT / "evidence" / "implementation" / "task-ledger.schema.v1.json"
LEDGER = ROOT / "evidence" / "implementation" / "task-ledger.v1.json"
DECISION_REGISTRY_SCHEMA = (
    ROOT / "docs" / "adr" / "decision-registry.proposed.schema.v1.json"
)
DECISION_REGISTRY = ROOT / "docs" / "adr" / "decision-registry.proposed.v1.json"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_SCHEMA_ERRORS = 64
DRAFT_2020_12_ID = "https://json-schema.org/draft/2020-12/schema"
LEDGER_SCHEMA_ID = (
    "https://github.com/sepahead/NCP/evidence/implementation/"
    "task-ledger.schema.v1.json"
)
DECISION_REGISTRY_SCHEMA_ID = (
    "https://sepahead.github.io/NCP/schemas/proposed-decision-registry.v1.json"
)
LOCAL_DEFINITION_REF = re.compile(r"^#/\$defs/[A-Za-z][A-Za-z0-9]*$")
MAX_SCHEMA_PATTERNS = 64
MAX_SCHEMA_PATTERN_CHARS = 256
MAX_SCHEMA_OBJECTS = 4096
MAX_SCHEMA_REFERENCES = 512
MAX_SCHEMA_COMBINATORS = 64
MAX_SCHEMA_COMBINATOR_BRANCHES = 256
MAX_SCHEMA_COMBINATOR_WIDTH = 16
MAX_SCHEMA_COMBINATOR_DEPTH = 8
MAX_SCHEMA_REFERENCE_EXPANSION = 100_000
# The validator executes Python regular expressions in-process. Keep the
# executable pattern language closed so a schema edit cannot add an
# exponential-time expression or a silently different regex dialect.
ALLOWED_SCHEMA_PATTERNS = frozenset(
    {
        r"^(?!.*[?#])https://[!-~]+$",
        r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[^\\]+$",
        r"^(?!/)(?![A-Za-z]:[\\/])(?!.*(?:^|/)\.\.(?:/|$)).+$",
        r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
        r"^ADR-0(0[1-9]|1[01])$",
        r"^D(0[1-9]|1[0-9]|20)$",
        r"^D(?:0[1-9]|1[0-9]|20)$",
        r"^L(?:0[1-9]|1[0-9]|20)$",
        r"^L(?:10|[1-9])$",
        r"^[0-9a-f]{40}$",
        r"^[0-9a-f]{64}$",
        r"^[A-Z0-9][A-Z0-9._-]{1,63}$",
        r"^[BEHNFGCPXR][0-9]{2}$",
        r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$",
        r"^[a-z0-9][a-z0-9._:-]{2,127}$",
        r"^[a-z][a-z0-9+.-]*:[!-~]+$",
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        (
            r"^docs/adr/(?:00(0[1-9]|1[01])-[a-z0-9-]+|"
            r"modules/adr-0(0[1-9]|1[01])-[a-z0-9-]+)\.md$"
        ),
        r"^docs/adr/00(0[1-9]|1[01])-[a-z0-9-]+\.md$",
        r"^docs/adr/modules/adr-0(0[1-9]|1[01])-[a-z0-9-]+\.md$",
        (
            r"^evidence/implementation/reviews/B01/"
            r"(?!.*(?:^|/)\.\.(?:/|$))[^\\]+$"
        ),
    }
)
FORBIDDEN_SCHEMA_KEYWORDS = frozenset(
    {
        "$anchor",
        "$comment",
        "$dynamicAnchor",
        "$dynamicRef",
        "$recursiveAnchor",
        "$recursiveRef",
        "$vocabulary",
        "contentEncoding",
        "contentMediaType",
        "contentSchema",
        "format",
        "patternProperties",
    }
)
ALLOWED_SCHEMA_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$defs",
        "$ref",
        "title",
        "description",
        "type",
        "const",
        "enum",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "prefixItems",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "allOf",
        "oneOf",
        "if",
        "then",
        "else",
    }
)
SCHEMA_SINGLE_CHILD_KEYWORDS = frozenset({"items"})
SCHEMA_MULTI_CHILD_KEYWORDS = frozenset({"prefixItems", "allOf", "oneOf"})
SCHEMA_PRIMITIVE_TYPES = frozenset(
    {"null", "boolean", "object", "array", "number", "integer", "string"}
)
EVIDENCE_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_JSON_BYTES,
    maximum_depth=32,
    maximum_items=100_000,
    maximum_object_members=256,
    maximum_array_items=4096,
    maximum_key_utf8_bytes=128,
    maximum_string_utf8_bytes=4096,
    maximum_total_string_utf8_bytes=MAX_JSON_BYTES,
    maximum_integer_chars=128,
    maximum_float_chars=128,
    allow_floats=False,
)
EVIDENCE_FILE_LIMITS = FileSnapshotLimits(
    minimum_bytes=1,
    maximum_bytes=MAX_JSON_BYTES,
)
PINNED_DISTRIBUTIONS = {
    "attrs": "26.1.0",
    "jsonschema": "4.26.0",
    "jsonschema-specifications": "2025.9.1",
    "referencing": "0.37.0",
    "rpds-py": "2026.6.3",
}
if sys.version_info < (3, 13):
    PINNED_DISTRIBUTIONS["typing-extensions"] = "4.16.0"


class EvidenceSchemaError(RuntimeError):
    """Raised when a schema, instance, or validator environment is invalid."""


def _fail(message: str) -> NoReturn:
    raise EvidenceSchemaError(message)


def load_json(path: Path) -> Any:
    try:
        label = path.relative_to(ROOT).as_posix()
    except ValueError:
        label = str(path)
    try:
        raw = read_bounded_regular_file(
            path,
            limits=EVIDENCE_FILE_LIMITS,
            label=label,
        )
        return parse_json_bytes(
            raw,
            limits=EVIDENCE_JSON_LIMITS,
            label=label,
        )
    except BoundedJsonError as error:
        _fail(str(error))


def require_pinned_validator() -> None:
    for distribution, expected in PINNED_DISTRIBUTIONS.items():
        try:
            observed = version(distribution)
        except PackageNotFoundError:
            _fail(
                f"required evidence-schema distribution is missing: "
                f"{distribution}=={expected}; install with "
                "scripts/requirements-evidence-schema.txt --require-hashes"
            )
        if observed != expected:
            _fail(
                f"evidence-schema distribution drift: {distribution} "
                f"expected {expected}, observed {observed}"
            )


def _bounded_schema_errors(errors: Any) -> tuple[list[Any], bool]:
    """Retain at most one deterministic error window plus a truncation bit."""

    retained: list[Any] = []
    iterator = iter(errors)
    for _ in range(MAX_SCHEMA_ERRORS + 1):
        try:
            error = next(iterator)
        except StopIteration:
            return retained, False
        retained.append(error)
    retained.pop()
    return retained, True


def _schema_error_key(error: Any) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    return (
        tuple(str(part) for part in error.absolute_path),
        error.validator or "",
        tuple(str(part) for part in error.absolute_schema_path),
    )


def _validate_schema_resource_policy(schema: dict[str, Any], label: str) -> None:
    """Reject network-capable, dialect-ambiguous, or unbounded schema features."""

    definitions = schema.get("$defs", {})
    if type(definitions) is not dict:
        _fail(f"{label} $defs must be one native object")
    definition_names = set(definitions)
    if any(
        type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name) is None
        for name in definition_names
    ):
        _fail(f"{label} has an invalid local definition name")

    pattern_count = 0
    schema_object_count = 0
    reference_count = 0
    combinator_count = 0
    combinator_branch_count = 0
    owner_object_counts = {name: 0 for name in definition_names}
    owner_object_counts[None] = 0
    owner_reference_targets: dict[str | None, list[str]] = {
        name: [] for name in definition_names
    }
    owner_reference_targets[None] = []
    stack: list[tuple[Any, bool, str | None, int]] = [(schema, True, None, 0)]
    while stack:
        value, is_root, owner, combinator_depth = stack.pop()
        if type(value) is not dict:
            _fail(f"{label} contains a non-object boolean or schema node")
        schema_object_count += 1
        owner_object_counts[owner] += 1
        if schema_object_count > MAX_SCHEMA_OBJECTS:
            _fail(f"{label} has more than {MAX_SCHEMA_OBJECTS} schema objects")
        keys = set(value)
        for key, member in value.items():
            if key in FORBIDDEN_SCHEMA_KEYWORDS:
                _fail(f"{label} uses forbidden schema keyword {key!r}")
            if key not in ALLOWED_SCHEMA_KEYWORDS:
                _fail(f"{label} uses unsupported schema keyword {key!r}")
            if key in {"$schema", "$id", "$defs"} and not is_root:
                _fail(f"{label} nests schema resource keyword {key!r}")
            if key == "$ref":
                if (
                    type(member) is not str
                    or LOCAL_DEFINITION_REF.fullmatch(member) is None
                    or member.removeprefix("#/$defs/") not in definition_names
                ):
                    _fail(f"{label} has a non-local, missing, or malformed $ref")
                if keys != {"$ref"}:
                    _fail(f"{label} has a $ref with evaluation siblings")
                reference_count += 1
                if reference_count > MAX_SCHEMA_REFERENCES:
                    _fail(
                        f"{label} has more than "
                        f"{MAX_SCHEMA_REFERENCES} local references"
                    )
                owner_reference_targets[owner].append(member.removeprefix("#/$defs/"))
            if key == "pattern":
                pattern_count += 1
                if (
                    type(member) is not str
                    or not member
                    or len(member) > MAX_SCHEMA_PATTERN_CHARS
                    or member not in ALLOWED_SCHEMA_PATTERNS
                ):
                    _fail(f"{label} has an unreviewed executable regex pattern")
                try:
                    re.compile(member)
                except re.error as error:
                    _fail(f"{label} has an invalid regex pattern: {error}")
        if "$ref" in value:
            continue
        if is_root:
            if value.get("$schema") != DRAFT_2020_12_ID:
                _fail(f"{label} does not select the pinned schema dialect")
            schema_id = value.get("$id")
            if (
                type(schema_id) is not str
                or re.fullmatch(
                    r"^(?!.*[?#])https://[!-~]+$",
                    schema_id,
                )
                is None
            ):
                _fail(f"{label} has an invalid root schema identifier")
            if (
                value.get("type") != "object"
                or type(value.get("properties")) is not dict
                or value.get("additionalProperties") is not False
            ):
                _fail(f"{label} root schema is not one closed object")
        for annotation in ("title", "description"):
            if annotation in value and type(value[annotation]) is not str:
                _fail(f"{label} {annotation} annotation must be one string")
        if "type" in value:
            declared_type = value["type"]
            if type(declared_type) is str:
                declared_types = (declared_type,)
            elif (
                type(declared_type) is list
                and 1 <= len(declared_type) <= 2
                and all(type(item) is str for item in declared_type)
            ):
                declared_types = tuple(declared_type)
            else:
                _fail(f"{label} has an invalid or over-wide type union")
            if len(declared_types) != len(set(declared_types)) or any(
                item not in SCHEMA_PRIMITIVE_TYPES for item in declared_types
            ):
                _fail(f"{label} has an unknown or duplicated primitive type")
            if "object" in declared_types and (
                type(value.get("properties")) is not dict
                or value.get("additionalProperties") is not False
            ):
                _fail(f"{label} object schema is not explicitly closed")
            if "array" in declared_types and (
                (
                    "maxItems" in value
                    and (
                        type(value["maxItems"]) is not int
                        or not (
                            0
                            <= value["maxItems"]
                            <= EVIDENCE_JSON_LIMITS.maximum_array_items
                        )
                    )
                )
                or not ({"items", "prefixItems"} & keys)
            ):
                _fail(f"{label} array schema lacks one bounded item contract")
        if "required" in value:
            required = value["required"]
            if (
                type(required) is not list
                or len(required) > EVIDENCE_JSON_LIMITS.maximum_object_members
                or any(type(item) is not str for item in required)
                or len(required) != len(set(required))
                or (
                    type(value.get("properties")) is not dict
                    or not set(required).issubset(value["properties"])
                )
            ):
                _fail(f"{label} has an invalid or duplicated required set")
        if "enum" in value:
            enum = value["enum"]
            if type(enum) is not list or not 1 <= len(enum) <= 64:
                _fail(f"{label} has an empty or over-wide enum")
        if "uniqueItems" in value and type(value["uniqueItems"]) is not bool:
            _fail(f"{label} uniqueItems must be one native boolean")
        for bound in (
            "minItems",
            "maxItems",
            "minLength",
            "maxLength",
            "minimum",
            "maximum",
        ):
            if bound in value and (type(value[bound]) is not int or value[bound] < 0):
                _fail(f"{label} {bound} must be one non-negative integer")
        if (
            "minItems" in value
            and "maxItems" in value
            and value["minItems"] > value["maxItems"]
        ):
            _fail(f"{label} has inverted minItems/maxItems bounds")
        if (
            "minLength" in value
            and "maxLength" in value
            and value["minLength"] > value["maxLength"]
        ):
            _fail(f"{label} has inverted minLength/maxLength bounds")
        if (
            "minimum" in value
            and "maximum" in value
            and value["minimum"] > value["maximum"]
        ):
            _fail(f"{label} has inverted minimum/maximum bounds")
        if "additionalProperties" in value and (
            value["additionalProperties"] is not False
        ):
            _fail(f"{label} must close additionalProperties with false")
        if "properties" in value:
            properties = value["properties"]
            if type(properties) is not dict:
                _fail(f"{label} properties must be one native object")
            stack.extend(
                (child, False, owner, combinator_depth) for child in properties.values()
            )
        if "$defs" in value:
            stack.extend((child, False, name, 0) for name, child in definitions.items())
        for keyword in SCHEMA_SINGLE_CHILD_KEYWORDS:
            if keyword in value:
                stack.append(
                    (
                        value[keyword],
                        False,
                        owner,
                        combinator_depth,
                    )
                )
        conditional_keys = keys & {"if", "then", "else"}
        if conditional_keys:
            if "if" not in conditional_keys or not (
                {"then", "else"} & conditional_keys
            ):
                _fail(f"{label} has an incomplete conditional schema")
            next_depth = combinator_depth + 1
            if next_depth > MAX_SCHEMA_COMBINATOR_DEPTH:
                _fail(
                    f"{label} exceeds schema combinator depth "
                    f"{MAX_SCHEMA_COMBINATOR_DEPTH}"
                )
            combinator_count += 1
            combinator_branch_count += len(conditional_keys)
            if (
                combinator_count > MAX_SCHEMA_COMBINATORS
                or combinator_branch_count > MAX_SCHEMA_COMBINATOR_BRANCHES
            ):
                _fail(f"{label} exceeds the schema combinator budget")
            stack.extend(
                (value[keyword], False, owner, next_depth)
                for keyword in conditional_keys
            )
        for keyword in SCHEMA_MULTI_CHILD_KEYWORDS:
            if keyword not in value:
                continue
            children = value[keyword]
            if (
                type(children) is not list
                or not 1 <= len(children) <= MAX_SCHEMA_COMBINATOR_WIDTH
            ):
                _fail(f"{label} has an empty or over-wide {keyword}")
            is_combinator = keyword in {"allOf", "oneOf"}
            next_depth = combinator_depth + (1 if is_combinator else 0)
            if next_depth > MAX_SCHEMA_COMBINATOR_DEPTH:
                _fail(
                    f"{label} exceeds schema combinator depth "
                    f"{MAX_SCHEMA_COMBINATOR_DEPTH}"
                )
            if is_combinator:
                combinator_count += 1
                combinator_branch_count += len(children)
                if (
                    combinator_count > MAX_SCHEMA_COMBINATORS
                    or combinator_branch_count > MAX_SCHEMA_COMBINATOR_BRANCHES
                ):
                    _fail(f"{label} exceeds the schema combinator budget")
            stack.extend((child, False, owner, next_depth) for child in children)
    if pattern_count > MAX_SCHEMA_PATTERNS:
        _fail(
            f"{label} has {pattern_count} regex patterns; "
            f"maximum is {MAX_SCHEMA_PATTERNS}"
        )

    reference_expansion_cost: dict[str, int] = {}
    pending = set(definition_names)
    while pending:
        progressed = False
        for name in tuple(sorted(pending)):
            targets = owner_reference_targets[name]
            if any(target not in reference_expansion_cost for target in targets):
                continue
            cost = owner_object_counts[name] + sum(
                reference_expansion_cost[target] for target in targets
            )
            if cost > MAX_SCHEMA_REFERENCE_EXPANSION:
                _fail(f"{label} exceeds the local $ref expansion budget")
            reference_expansion_cost[name] = cost
            pending.remove(name)
            progressed = True
        if not progressed:
            _fail(f"{label} has a cyclic local $ref graph")
    root_expansion_cost = owner_object_counts[None] + sum(
        reference_expansion_cost[target] for target in owner_reference_targets[None]
    )
    if root_expansion_cost > MAX_SCHEMA_REFERENCE_EXPANSION:
        _fail(f"{label} exceeds the local $ref expansion budget")


def validate_instance(
    schema: Any,
    instance: Any,
    label: str,
    *,
    expected_schema_id: str | None = None,
) -> None:
    try:
        validate_native_json_tree(
            schema,
            limits=EVIDENCE_JSON_LIMITS,
            label=f"{label} schema",
        )
        validate_native_json_tree(
            instance,
            limits=EVIDENCE_JSON_LIMITS,
            label=f"{label} instance",
        )
    except BoundedJsonError as error:
        _fail(str(error))
    if type(schema) is not dict or schema.get("$schema") != DRAFT_2020_12_ID:
        _fail(f"{label} does not declare Draft 2020-12")
    if expected_schema_id is not None and schema.get("$id") != expected_schema_id:
        _fail(f"{label} has an unexpected root schema identifier")
    _validate_schema_resource_policy(schema, label)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        _fail(f"{label} schema is invalid: {error.message}")
    try:
        errors, truncated = _bounded_schema_errors(
            Draft202012Validator(schema).iter_errors(instance)
        )
    except Exception as error:
        detail = str(error)
        if len(detail) > 512:
            detail = detail[:509] + "..."
        _fail(f"{label} validator failed closed with {type(error).__name__}: {detail}")
    if errors:
        error = min(errors, key=_schema_error_key)
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        detail = error.message
        if len(detail) > 512:
            detail = detail[:509] + "..."
        error_count = f">={MAX_SCHEMA_ERRORS + 1}" if truncated else f"={len(errors)}"
        _fail(
            f"{label} fails Draft 2020-12 at {location or '/'} "
            f"({error.validator}): {detail}; total_errors{error_count}"
        )


def validate_ledger_instance(instance: Any) -> None:
    require_pinned_validator()
    validate_instance(
        load_json(LEDGER_SCHEMA),
        instance,
        "implementation ledger",
        expected_schema_id=LEDGER_SCHEMA_ID,
    )


def validate_decision_registry_instance(instance: Any) -> None:
    require_pinned_validator()
    validate_instance(
        load_json(DECISION_REGISTRY_SCHEMA),
        instance,
        "proposed decision registry",
        expected_schema_id=DECISION_REGISTRY_SCHEMA_ID,
    )


def _must_fail(action: Any, label: str, expected: str) -> None:
    try:
        action()
    except EvidenceSchemaError as error:
        if expected not in str(error):
            _fail(
                f"hostile schema test {label} failed for the wrong reason: "
                f"expected {expected!r}, observed {str(error)!r}"
            )
        return
    _fail(f"hostile schema test unexpectedly passed: {label}")


def self_test() -> None:
    run_bounded_json_self_test()
    require_pinned_validator()
    ledger_schema = load_json(LEDGER_SCHEMA)
    ledger = load_json(LEDGER)
    registry_schema = load_json(DECISION_REGISTRY_SCHEMA)
    registry = load_json(DECISION_REGISTRY)
    validate_instance(
        ledger_schema,
        ledger,
        "implementation ledger",
        expected_schema_id=LEDGER_SCHEMA_ID,
    )
    validate_instance(
        registry_schema,
        registry,
        "proposed decision registry",
        expected_schema_id=DECISION_REGISTRY_SCHEMA_ID,
    )

    _must_fail(
        lambda: validate_instance(
            {"$schema": DRAFT_2020_12_ID},
            {"anything": ["goes"]},
            "hostile erased schema",
        ),
        "schema erasure",
        "invalid root schema identifier",
    )
    closed_erasure = {
        "$id": LEDGER_SCHEMA_ID,
        "$schema": DRAFT_2020_12_ID,
        "additionalProperties": False,
        "properties": {},
        "type": "object",
    }
    _must_fail(
        lambda: validate_instance(
            closed_erasure,
            ledger,
            "hostile closed schema erasure",
            expected_schema_id=LEDGER_SCHEMA_ID,
        ),
        "closed schema erasure",
        "additionalProperties",
    )

    hostile_schema = copy.deepcopy(ledger_schema)
    hostile_schema["properties"]["defect_traceability"]["maxItems"] = 19
    _must_fail(
        lambda: validate_instance(
            hostile_schema, ledger, "hostile implementation ledger"
        ),
        "schema count silently excludes D20",
        "maxItems",
    )
    hostile_schema = copy.deepcopy(ledger_schema)
    hostile_schema["properties"]["defect_traceability"]["items"]["properties"]["id"][
        "pattern"
    ] = r"^D(?:0[1-9]|1[0-9])$"
    _must_fail(
        lambda: validate_instance(
            hostile_schema, ledger, "hostile implementation ledger"
        ),
        "schema pattern silently excludes D20",
        "pattern",
    )
    hostile_registry = copy.deepcopy(registry)
    del hostile_registry["decisions"][0]["source_set"]
    _must_fail(
        lambda: validate_instance(
            registry_schema,
            hostile_registry,
            "hostile proposed decision registry",
        ),
        "generated decision omits its source set",
        "required",
    )
    hostile_schema = copy.deepcopy(ledger_schema)
    hostile_schema["$defs"]["commit"]["$ref"] = (
        "https://attacker.invalid/remote-schema.json"
    )
    _must_fail(
        lambda: validate_instance(
            hostile_schema, ledger, "hostile implementation ledger"
        ),
        "remote schema reference",
        "non-local",
    )
    hostile_schema = copy.deepcopy(ledger_schema)
    hostile_schema["$defs"]["commit"]["$dynamicRef"] = "#task"
    _must_fail(
        lambda: validate_instance(
            hostile_schema, ledger, "hostile implementation ledger"
        ),
        "dynamic schema reference",
        "$dynamicRef",
    )
    hostile_schema = copy.deepcopy(ledger_schema)
    hostile_schema["$defs"]["commit"]["pattern"] = r"^(a+)+$"
    _must_fail(
        lambda: validate_instance(
            hostile_schema, ledger, "hostile implementation ledger"
        ),
        "unreviewed regex",
        "unreviewed executable regex",
    )
    hostile_schema = copy.deepcopy(ledger_schema)
    hostile_schema["$defs"]["commit"]["format"] = "uri"
    _must_fail(
        lambda: validate_instance(
            hostile_schema, ledger, "hostile implementation ledger"
        ),
        "silently ignored format",
        "format",
    )
    hostile_schema = copy.deepcopy(ledger_schema)
    hostile_schema["ignoredSecurityExtension"] = True
    _must_fail(
        lambda: validate_instance(
            hostile_schema, ledger, "hostile implementation ledger"
        ),
        "silently ignored extension keyword",
        "unsupported schema keyword",
    )
    cyclic_schema = {
        "$id": "https://example.invalid/cyclic-schema",
        "$schema": DRAFT_2020_12_ID,
        "$defs": {
            "A": {"$ref": "#/$defs/B"},
            "B": {"$ref": "#/$defs/A"},
        },
        "type": "object",
        "properties": {"value": {"$ref": "#/$defs/A"}},
        "additionalProperties": False,
    }
    _must_fail(
        lambda: validate_instance(
            cyclic_schema,
            {"value": "untrusted"},
            "hostile cyclic schema",
        ),
        "cyclic local references",
        "cyclic local $ref graph",
    )
    sibling_ref_schema = {
        "$id": "https://example.invalid/sibling-ref-schema",
        "$schema": DRAFT_2020_12_ID,
        "$defs": {"A": {"type": "string"}},
        "type": "object",
        "properties": {
            "value": {
                "$ref": "#/$defs/A",
                "description": "ambiguous sibling evaluation",
            }
        },
        "additionalProperties": False,
    }
    _must_fail(
        lambda: validate_instance(
            sibling_ref_schema,
            {"value": "untrusted"},
            "hostile sibling reference schema",
        ),
        "reference with evaluation sibling",
        "$ref with evaluation siblings",
    )
    wide_combinator_schema = {
        "$id": "https://example.invalid/wide-combinator-schema",
        "$schema": DRAFT_2020_12_ID,
        "additionalProperties": False,
        "properties": {
            "value": {
                "oneOf": [
                    {"type": "string"}
                    for _ in range(MAX_SCHEMA_COMBINATOR_WIDTH + 1)
                ]
            }
        },
        "required": ["value"],
        "type": "object",
    }
    _must_fail(
        lambda: validate_instance(
            wide_combinator_schema,
            {"value": "untrusted"},
            "hostile wide combinator schema",
        ),
        "over-wide combinator",
        "empty or over-wide oneOf",
    )

    consumed = 0

    def hostile_error_fanout() -> Any:
        nonlocal consumed
        for index in range(MAX_SCHEMA_ERRORS + 17):
            consumed += 1
            yield SimpleNamespace(
                absolute_path=(index,),
                absolute_schema_path=("items", "type"),
                validator="type",
                message="hostile",
            )

    retained, truncated = _bounded_schema_errors(hostile_error_fanout())
    if (
        len(retained) != MAX_SCHEMA_ERRORS
        or not truncated
        or consumed != MAX_SCHEMA_ERRORS + 1
    ):
        _fail("schema error fanout did not stop at the deterministic cap")
    fanout_schema = {
        "$id": "https://example.invalid/fanout-schema",
        "$schema": DRAFT_2020_12_ID,
        "additionalProperties": False,
        "properties": {
            "values": {
                "items": {"type": "integer"},
                "maxItems": MAX_SCHEMA_ERRORS + 17,
                "type": "array",
            }
        },
        "required": ["values"],
        "type": "object",
    }
    _must_fail(
        lambda: validate_instance(
            fanout_schema,
            {"values": ["invalid"] * (MAX_SCHEMA_ERRORS + 17)},
            "hostile schema fanout",
        ),
        "schema error fanout",
        f"total_errors>={MAX_SCHEMA_ERRORS + 1}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            print(
                "OK evidence schemas: pinned Draft 2020-12 validator; "
                "hostile schema drift rejected"
            )
        else:
            validate_ledger_instance(load_json(LEDGER))
            validate_decision_registry_instance(load_json(DECISION_REGISTRY))
            print(
                "OK evidence schemas: implementation ledger and proposed "
                "decision registry conform to Draft 2020-12"
            )
        return 0
    except (OSError, EvidenceSchemaError) as error:
        print(f"ERROR evidence schemas: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
