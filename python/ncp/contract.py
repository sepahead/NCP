"""Application contracts and their schemas (specification section 11)."""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from . import frame as F
from .frame import FrameError
from .messages import is_name

TYPES = frozenset({"null", "boolean", "integer", "number", "string", "array", "object"})
_NUMBER_KEYWORDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
_COUNT_KEYWORDS = ("minLength", "maxLength", "minItems", "maxItems")
_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "const",
        *_NUMBER_KEYWORDS,
        *_COUNT_KEYWORDS,
        "items",
        "properties",
        "required",
        "additionalProperties",
        "ncp.array",
        "description",
        "title",
    }
)


class ContractError(ValueError):
    """A document that is not a valid NCP contract (section 11)."""


def _is_number(value: Any) -> bool:
    return type(value) is int or type(value) is float


def compile_schema(schema: Any, path: str = "$") -> dict[str, Any]:
    """Check that `schema` uses only the keywords of section 11.1 with values of their kind.
    Return it unchanged. Raise ContractError otherwise."""
    if type(schema) is not dict:
        raise ContractError(f"{path}: a schema is an object")
    unknown = schema.keys() - _KEYWORDS
    if unknown:
        raise ContractError(f"{path}: unknown schema keyword {sorted(unknown)[0]!r}")
    if "type" in schema:
        kinds = schema["type"] if type(schema["type"]) is list else [schema["type"]]
        if not kinds or any(type(k) is not str or k not in TYPES for k in kinds) or len(set(kinds)) != len(kinds):
            raise ContractError(f"{path}.type: one of {sorted(TYPES)} or a list of them")
    if "enum" in schema and type(schema["enum"]) is not list:
        raise ContractError(f"{path}.enum: an array")
    for keyword in _NUMBER_KEYWORDS:
        if keyword in schema and not _is_number(schema[keyword]):
            raise ContractError(f"{path}.{keyword}: a number")
    for keyword in _COUNT_KEYWORDS:
        if keyword in schema and not (type(schema[keyword]) is int and schema[keyword] >= 0):
            raise ContractError(f"{path}.{keyword}: an integer, 0 or larger")
    if "items" in schema:
        compile_schema(schema["items"], f"{path}.items")
    if "properties" in schema:
        if type(schema["properties"]) is not dict:
            raise ContractError(f"{path}.properties: an object of schemas")
        for name, member in schema["properties"].items():
            compile_schema(member, f"{path}.properties.{name}")
    if "required" in schema:
        required = schema["required"]
        if type(required) is not list or any(type(n) is not str for n in required) or len(set(required)) != len(
            required
        ):
            raise ContractError(f"{path}.required: an array of distinct member names")
    if "additionalProperties" in schema:
        extra = schema["additionalProperties"]
        if extra is not False:
            compile_schema(extra, f"{path}.additionalProperties")
    if "ncp.array" in schema:
        spec = schema["ncp.array"]
        if type(spec) is not dict or spec.keys() != {"dtype", "shape"}:
            raise ContractError(f"{path}.ncp.array: an object with the members dtype and shape")
        dtypes = spec["dtype"] if type(spec["dtype"]) is list else [spec["dtype"]]
        if not dtypes or any(type(d) is not str or d not in F.DTYPES for d in dtypes):
            raise ContractError(f"{path}.ncp.array.dtype: a dtype or an array of dtypes")
        shape = spec["shape"]
        if type(shape) is not list or any(not (n is None or (type(n) is int and n >= 0)) for n in shape):
            raise ContractError(f"{path}.ncp.array.shape: an array of integers or null")
    for keyword in ("description", "title"):
        if keyword in schema and type(schema[keyword]) is not str:
            raise ContractError(f"{path}.{keyword}: a string")
    return schema


def json_type(value: Any) -> str:
    """The JSON type of a decoded value (section 11.1). An array reference is an object."""
    kind = type(value)
    if value is None:
        return "null"
    if kind is bool:
        return "boolean"
    if kind is int:
        return "integer"
    if kind is float:
        return "number"
    if kind is str:
        return "string"
    if kind is list or kind is tuple:
        return "array"
    return "object"


def json_equal(a: Any, b: Any) -> bool:
    """Equality of section 11.1: the same JSON type and the same value."""
    kind = json_type(a)
    if kind != json_type(b):
        return False
    if isinstance(a, F.Array) or isinstance(b, F.Array):
        return False  # an array of section 5 never equals a value written in a contract
    if kind == "array":
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    if kind == "object":
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return a == b


def check(schema: Mapping[str, Any], value: Any, path: str = "$") -> str | None:
    """None if `value` matches `schema` (section 11.1), otherwise the first mismatch."""
    kind = json_type(value)
    if "type" in schema:
        allowed = schema["type"] if type(schema["type"]) is list else [schema["type"]]
        if kind not in allowed and not (kind == "integer" and "number" in allowed):
            return f"{path}: expected {' or '.join(allowed)}, found {kind}"
    if "enum" in schema and not any(json_equal(value, option) for option in schema["enum"]):
        return f"{path}: not one of the allowed values"
    if "const" in schema and not json_equal(value, schema["const"]):
        return f"{path}: not the required value"
    if "ncp.array" in schema and not isinstance(value, F.Array):
        return f"{path}: expected an array of section 5"
    if kind in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path}: below the minimum {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path}: above the maximum {schema['maximum']}"
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            return f"{path}: not above {schema['exclusiveMinimum']}"
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            return f"{path}: not below {schema['exclusiveMaximum']}"
        if kind == "number" and not math.isfinite(value):  # pragma: no cover - decoders refuse these
            return f"{path}: not a finite number"
    elif kind == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            return f"{path}: shorter than {schema['minLength']} characters"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{path}: longer than {schema['maxLength']} characters"
    elif kind == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            return f"{path}: fewer than {schema['minItems']} items"
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{path}: more than {schema['maxItems']} items"
        if "items" in schema:
            for index, item in enumerate(value):
                error = check(schema["items"], item, f"{path}[{index}]")
                if error:
                    return error
    elif kind == "object":
        if isinstance(value, F.Array):
            return _check_array(schema, value, path)
        for name in schema.get("required", ()):
            if name not in value:
                return f"{path}: the member {name!r} is missing"
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        for name, member in value.items():
            if name in properties:
                error = check(properties[name], member, f"{path}.{name}")
            elif extra is False:
                return f"{path}: the member {name!r} is not allowed"
            elif extra is not None:
                error = check(extra, member, f"{path}.{name}")
            else:
                error = None
            if error:
                return error
    return None


def _check_array(schema: Mapping[str, Any], value: F.Array, path: str) -> str | None:
    """Object keywords do not constrain an array of section 5; only `ncp.array` does."""
    if "ncp.array" not in schema:
        return None
    spec = schema["ncp.array"]
    dtypes = spec["dtype"] if type(spec["dtype"]) is list else [spec["dtype"]]
    if value.dtype not in dtypes:
        return f"{path}: dtype {value.dtype} is not {' or '.join(dtypes)}"
    shape = spec["shape"]
    if len(shape) != len(value.shape) or any(n is not None and n != m for n, m in zip(shape, value.shape)):
        return f"{path}: shape {list(value.shape)} does not match {shape}"
    return None


@dataclass(frozen=True)
class Contract:
    """A contract document and its identity: the SHA-256 digest of its exact bytes (section 11)."""

    data: bytes = field(repr=False)
    identity: str
    application: str
    version: str
    operations: frozenset[str]
    streams: frozenset[str]
    document: Mapping[str, Any] = field(repr=False, compare=False, hash=False)

    @classmethod
    def from_bytes(cls, data: bytes) -> Contract:
        if type(data) is not bytes:
            data = bytes(data)
        try:
            document = F.loads(data)
        except FrameError as error:
            raise ContractError(f"not an NCP contract: {error}") from error
        if type(document) is not dict:
            raise ContractError("not an NCP contract: the document is not an object")
        if type(document.get("ncp_contract")) is not int or document["ncp_contract"] != 1:
            raise ContractError("not an NCP contract: ncp_contract must be the integer 1")
        for member in ("application", "version"):
            value = document.get(member)
            if type(value) is not str or not 1 <= len(value) <= 128:
                raise ContractError(f"not an NCP contract: {member} must be a string of 1 to 128 characters")
        operations, streams = document.get("operations"), document.get("streams")
        if type(operations) is not dict or type(streams) is not dict:
            raise ContractError("not an NCP contract: operations and streams must be objects")
        for name, value in operations.items():
            if not is_name(name) or name in ("open", "close") or name.startswith("ncp."):
                raise ContractError(f"operation name {name!r} is not allowed (section 11, rule 1)")
            _schemas(value, f"operations.{name}", {"request", "result"})
        for name, value in streams.items():
            if not is_name(name):
                raise ContractError(f"stream type name {name!r} is not allowed (section 11, rule 1)")
            _schemas(value, f"streams.{name}", {"body"})
        return cls(
            data,
            hashlib.sha256(data).hexdigest(),
            document["application"],
            document["version"],
            frozenset(operations),
            frozenset(streams),
            document,
        )

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> Contract:
        with open(path, "rb") as handle:
            return cls.from_bytes(handle.read())

    def schema(self, op: str, part: str) -> Mapping[str, Any] | None:
        """The schema of an operation's `request` or `result`, or None."""
        value = self.document["operations"].get(op)
        return None if value is None else value.get("ncp.schema", {}).get(part)

    def check_request(self, op: str, body: Any) -> str | None:
        """None if the body matches the operation's request schema, otherwise the mismatch."""
        schema = self.schema(op, "request")
        return None if schema is None else check(schema, body)

    def check_result(self, op: str, body: Any) -> str | None:
        """None if the result matches the operation's result schema, otherwise the mismatch."""
        schema = self.schema(op, "result")
        return None if schema is None else check(schema, body)

    def check_stream(self, name: str, body: Any) -> str | None:
        """None if the body matches the stream type's body schema, otherwise the mismatch."""
        value = self.document["streams"].get(name)
        schema = None if value is None else value.get("ncp.schema", {}).get("body")
        return None if schema is None else check(schema, body)


def _schemas(value: Any, path: str, parts: set[str]) -> None:
    if type(value) is not dict:
        raise ContractError(f"{path}: the description must be an object (section 11, rule 2)")
    if "ncp.schema" in value:
        schemas = value["ncp.schema"]
        if type(schemas) is not dict or not schemas.keys() <= parts:
            raise ContractError(f"{path}.ncp.schema: an object with the members {sorted(parts)}")
        for part, schema in schemas.items():
            compile_schema(schema, f"{path}.ncp.schema.{part}")
