#!/usr/bin/env python3
"""Shared bounded canonical-JSON primitives for the synthetic B01 probes.

The encoder never builds a normalized Python object tree.  It writes one
canonical form directly to a capped byte sink.  Authority-bearing callers must
pass structurally immutable values: frozen registered dataclasses, tuples,
``FrozenMap``/``FrozenList`` values, immutable bytes, and exact scalar types.
Registration pins the canonical access surface of each dataclass.  Each encode,
freeze, or immutable-validation traversal first validates the complete registry
backing.  It revalidates each reached class before that class's first instance
snapshot in the traversal, then reads every field of every encountered artifact
instance exactly once through ``object.__getattribute__``.  On every call, the
targeted artifact snapshot API validates the complete registry backing and
revalidates its selected class.

``freeze_owned`` exists only for a caller-owned, unpublished authoring value.
It rejects aliases and cycles while replacing every exact ``dict`` and ``list``
with a tuple-backed immutable value.  It is not an atomic snapshot API and must
not be used to claim ownership of a graph another thread can mutate.

This module is a same-process integrity mechanism, not an adversarial Python
sandbox.  A caller must prevent concurrent mutation of registered classes,
registries, and instances, and must preserve canonicalizer and interpreter code
integrity.  The configured nesting limit is also capped below Python's normal
recursion limit because the encoder and ``freeze_owned`` recurse by design.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import (
    Field,
    FrozenInstanceError,
    dataclass,
    make_dataclass,
)
from dataclasses import (
    field as dataclass_field,
)
from types import (
    CellType,
    CodeType,
    FunctionType,
    GetSetDescriptorType,
    MappingProxyType,
    MemberDescriptorType,
)
from typing import Any, Literal

MAX_CANONICAL_CONFIG_LIMIT = 1 << 30
MAX_CANONICAL_RECURSION_DEPTH = 256
MAX_FROZEN_TYPE_REGISTRY_ENTRIES = 4_096
MAX_FROZEN_TYPE_REGISTRY_FIELDS = 65_536
MAX_FROZEN_ARTIFACT_FIELDS = 4_096
MAX_FROZEN_ARTIFACT_CLASS_BINDINGS = MAX_FROZEN_ARTIFACT_FIELDS + 512
MAX_FROZEN_FIELD_NAME_BYTES = 256
MAX_FROZEN_ARTIFACT_FIELD_NAME_BYTES = 262_144
MAX_FROZEN_TYPE_ID_BYTES = 512
MAX_FROZEN_TYPE_REGISTRY_ID_BYTES = 2_097_152
MAX_INERT_DEFAULT_DEPTH = 64
MAX_INERT_DEFAULT_NODES = 4_096
MAX_INERT_DEFAULT_INTEGER_BITS = 256
MAX_INERT_DEFAULT_SCALAR_BYTES = 1_048_576
MAX_INERT_DEFAULT_AGGREGATE_SCALAR_BYTES = 1_048_576
HEX_CHUNK_BYTES = 64 * 1024
_LOG2_10_UPPER_NUMERATOR = 3_322
_LOG2_10_UPPER_DENOMINATOR = 1_000

Style = Literal[
    "bridge",
    "authority",
    "canonical_json",
    "capture_plain",
    "capture_typed",
]


def _bounded_integer_token(
    value: Any,
    *,
    maximum_chars: int,
    label: str,
    error_type: type[Exception],
) -> bytes:
    if type(value) is not int:
        raise error_type(f"{label} type is not exact")
    digit_budget = maximum_chars - (1 if value < 0 else 0)
    if digit_budget <= 0:
        raise error_type(f"{label} exceeds its lexical limit")
    maximum_bits = (
        digit_budget * _LOG2_10_UPPER_NUMERATOR + _LOG2_10_UPPER_DENOMINATOR - 1
    ) // _LOG2_10_UPPER_DENOMINATOR
    if value.bit_length() > maximum_bits:
        raise error_type(f"{label} exceeds its lexical limit")
    try:
        token = str(value).encode("ascii")
    except (MemoryError, OverflowError, ValueError) as exc:
        raise error_type(f"{label} cannot be rendered within its bound") from exc
    if len(token) > maximum_chars:
        raise error_type(f"{label} exceeds its lexical limit")
    return token


@dataclass(frozen=True, slots=True)
class CanonicalLimits:
    """Finite input and output budgets for one canonicalization."""

    max_output_bytes: int
    max_depth: int
    max_nodes: int
    max_collection_items: int
    max_artifact_fields: int
    max_string_bytes: int
    max_payload_bytes: int
    max_aggregate_scalar_bytes: int
    min_integer: int
    max_integer: int
    allow_float: bool = False
    max_number_chars: int = 64
    allow_empty_payload: bool = False

    def __post_init__(self) -> None:
        positive = (
            "max_output_bytes",
            "max_nodes",
            "max_string_bytes",
            "max_payload_bytes",
            "max_aggregate_scalar_bytes",
            "max_number_chars",
        )
        nonnegative = (
            "max_depth",
            "max_collection_items",
            "max_artifact_fields",
        )
        for name in positive:
            value = getattr(self, name)
            if (
                type(value) is not int
                or value <= 0
                or value > MAX_CANONICAL_CONFIG_LIMIT
            ):
                raise ValueError(f"{name} is outside the canonical config range")
        for name in nonnegative:
            value = getattr(self, name)
            if (
                type(value) is not int
                or value < 0
                or value > MAX_CANONICAL_CONFIG_LIMIT
            ):
                raise ValueError(f"{name} is outside the canonical config range")
        if self.max_depth > MAX_CANONICAL_RECURSION_DEPTH:
            raise ValueError("max_depth exceeds the canonical recursion ceiling")
        if (
            type(self.min_integer) is not int
            or type(self.max_integer) is not int
            or self.min_integer > self.max_integer
        ):
            raise ValueError("canonical integer range is invalid")
        if (
            type(self.allow_float) is not bool
            or type(self.allow_empty_payload) is not bool
        ):
            raise ValueError("canonical boolean config fields are not exact")
        if self.max_depth >= self.max_nodes:
            raise ValueError("max_depth must be smaller than max_nodes")
        if self.max_collection_items > self.max_nodes:
            raise ValueError("max_collection_items cannot exceed max_nodes")
        if self.max_artifact_fields > self.max_nodes:
            raise ValueError("max_artifact_fields cannot exceed max_nodes")
        if self.max_string_bytes > self.max_aggregate_scalar_bytes:
            raise ValueError("string limit cannot exceed aggregate scalar limit")
        if self.max_payload_bytes > self.max_aggregate_scalar_bytes:
            raise ValueError("payload limit cannot exceed aggregate scalar limit")
        if self.max_aggregate_scalar_bytes > self.max_output_bytes:
            raise ValueError("aggregate scalar limit cannot exceed output limit")
        if self.max_number_chars > self.max_output_bytes:
            raise ValueError("number-token limit cannot exceed output limit")
        _bounded_integer_token(
            self.min_integer,
            maximum_chars=self.max_number_chars,
            label="minimum canonical integer endpoint",
            error_type=ValueError,
        )
        _bounded_integer_token(
            self.max_integer,
            maximum_chars=self.max_number_chars,
            label="maximum canonical integer endpoint",
            error_type=ValueError,
        )


@dataclass(frozen=True)
class _EmptyFrozenMutatorTemplate:
    """Local generator witness for a genuine zero-field frozen dataclass."""


def _validate_error_type(error_type: Any) -> type[Exception]:
    """Accept only exception classes whose construction cannot run caller code."""

    if type(error_type) is not type or not issubclass(error_type, Exception):
        raise TypeError("error_type must be one exact Exception class")
    for candidate in type.__getattribute__(error_type, "__mro__"):
        namespace = type.__getattribute__(candidate, "__dict__")
        module_name = type.__getattribute__(candidate, "__module__")
        if type(module_name) is not str:
            raise TypeError("error_type module identity is not exact")
        if module_name == "builtins":
            break
        if "__new__" in namespace or "__init__" in namespace:
            raise TypeError("error_type constructor must not execute caller code")
    return error_type


def _validate_limits_exact(
    limits: Any,
    *,
    error_type: type[Exception],
) -> CanonicalLimits:
    if type(limits) is not CanonicalLimits:
        raise error_type("canonical limits type is not exact")
    try:
        CanonicalLimits.__post_init__(limits)
    except (AttributeError, MemoryError, OverflowError, TypeError, ValueError) as exc:
        raise error_type("canonical limits were forged or mutated") from exc
    return limits


@dataclass(frozen=True, slots=True)
class FrozenMap:
    """An exact string-keyed mapping with immutable, key-sorted storage."""

    entries: tuple[tuple[str, Any], ...]

    def __post_init__(self) -> None:
        entries = object.__getattribute__(self, "entries")
        if type(entries) is not tuple:
            raise ValueError("frozen mapping backing is not an exact tuple")
        prior: str | None = None
        for index, entry in enumerate(entries):
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("frozen mapping entry is not one exact pair")
            key, _value = entry
            if type(key) is not str:
                raise ValueError("frozen mapping key is not an exact string")
            if index and prior is not None and key <= prior:
                raise ValueError("frozen mapping keys are duplicate or unordered")
            prior = key

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "entries"))

    def __iter__(self):
        entries = object.__getattribute__(self, "entries")
        return (key for key, _value in entries)

    def __getitem__(self, key: str) -> Any:
        if type(key) is not str:
            raise KeyError(key)
        entries = object.__getattribute__(self, "entries")
        for candidate, value in entries:
            if candidate == key:
                return value
        raise KeyError(key)

    def items(self) -> tuple[tuple[str, Any], ...]:
        return object.__getattribute__(self, "entries")


@dataclass(frozen=True, slots=True)
class FrozenList:
    """A tuple-backed value that retains the canonical type identity of a list."""

    items: tuple[Any, ...]

    def __post_init__(self) -> None:
        items = object.__getattribute__(self, "items")
        if type(items) is not tuple:
            raise ValueError("frozen list backing is not an exact tuple")

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "items"))

    def __iter__(self):
        return iter(object.__getattribute__(self, "items"))

    def __getitem__(self, index: int) -> Any:
        return object.__getattribute__(self, "items")[index]


_DATACLASS_PARAMS_TYPE = type(CanonicalLimits.__dict__["__dataclass_params__"])
_DATACLASS_PARAMS_SLOT_NAMES = tuple(_DATACLASS_PARAMS_TYPE.__slots__)
_FIELD_SLOT_NAMES = tuple(Field.__slots__)
_DATACLASS_FIELD_SENTINEL = object.__getattribute__(
    CanonicalLimits.__dict__["__dataclass_fields__"]["max_output_bytes"],
    "_field_type",
)
_EMPTY_FIELD_METADATA = object.__getattribute__(
    CanonicalLimits.__dict__["__dataclass_fields__"]["max_output_bytes"],
    "metadata",
)
_ABSENT_CLASS_BINDING = object()
_CANONICAL_LIMIT_FIELD_NAMES = tuple(CanonicalLimits.__dict__["__dataclass_fields__"])
_FIXED_TRUSTED_FROZEN_MUTATORS: dict[
    tuple[str, ...],
    tuple[FunctionType, FunctionType],
] = {
    _CANONICAL_LIMIT_FIELD_NAMES: (
        CanonicalLimits.__dict__["__setattr__"],
        CanonicalLimits.__dict__["__delattr__"],
    ),
    (): (
        _EmptyFrozenMutatorTemplate.__dict__["__setattr__"],
        _EmptyFrozenMutatorTemplate.__dict__["__delattr__"],
    ),
}
_TRUSTED_SLOTTED_FROZEN_STATE_METHODS = (
    ("__getstate__", CanonicalLimits.__dict__["__getstate__"]),
    ("__setstate__", CanonicalLimits.__dict__["__setstate__"]),
)
_TRANSIENT_FROZEN_MUTATOR_WITNESS_GENERATIONS = 0


@dataclass(frozen=True, slots=True)
class _PinnedFieldShape:
    field: Field
    name: str
    state: tuple[tuple[str, Any], ...]
    class_binding: Any


@dataclass(frozen=True, slots=True)
class _PinnedFrozenMutatorShape:
    function: FunctionType
    code: CodeType
    closure: tuple[Any, ...]
    closure_cells: tuple[Any, ...]
    globals_dict: dict[str, Any]
    builtins_dict: dict[str, Any]
    annotations: dict[str, Any]
    function_dict: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _PinnedClassShape:
    value_type: type[Any]
    dataclass_params: Any
    dataclass_param_state: tuple[tuple[str, Any], ...]
    field_table: dict[str, Field]
    fields: tuple[_PinnedFieldShape, ...]
    slotted: bool
    slots_binding: Any
    instance_dict_binding: Any
    setattr_mutator: _PinnedFrozenMutatorShape
    delattr_mutator: _PinnedFrozenMutatorShape


def _require_shape(
    condition: bool,
    message: str,
    *,
    error_type: type[Exception],
) -> None:
    if not condition:
        raise error_type(message)


def _same_exact_string_tuple(current: Any, trusted: Any) -> bool:
    return (
        type(current) is tuple
        and type(trusted) is tuple
        and len(current) == len(trusted)
        and all(type(item) is str for item in current)
        and all(type(item) is str for item in trusted)
        and all(
            str.__eq__(current_item, trusted_item) is True
            for current_item, trusted_item in zip(current, trusted, strict=True)
        )
    )


def _same_exact_code_constants(current: Any, trusted: Any) -> bool:
    if type(current) is not tuple or type(trusted) is not tuple:
        return False
    if len(current) != len(trusted):
        return False
    for current_item, trusted_item in zip(current, trusted, strict=True):
        if current_item is None or trusted_item is None:
            if current_item is not trusted_item:
                return False
        elif type(current_item) is str and type(trusted_item) is str:
            if str.__eq__(current_item, trusted_item) is not True:
                return False
        elif type(current_item) is frozenset and type(trusted_item) is frozenset:
            if (
                not all(type(item) is str for item in current_item)
                or not all(type(item) is str for item in trusted_item)
                or len(current_item) != len(trusted_item)
                or frozenset.__eq__(current_item, trusted_item) is not True
            ):
                return False
        else:
            return False
    return True


def _same_generated_mutator_code(code: CodeType, trusted: CodeType) -> bool:
    if type(code) is not CodeType or type(trusted) is not CodeType:
        return False
    for name in ("co_code", "co_exceptiontable", "co_linetable"):
        current = object.__getattribute__(code, name)
        expected = object.__getattribute__(trusted, name)
        if (
            type(current) is not bytes
            or type(expected) is not bytes
            or bytes.__eq__(current, expected) is not True
        ):
            return False
    for name in ("co_names", "co_varnames", "co_freevars", "co_cellvars"):
        if not _same_exact_string_tuple(
            object.__getattribute__(code, name),
            object.__getattribute__(trusted, name),
        ):
            return False
    for name in (
        "co_argcount",
        "co_posonlyargcount",
        "co_kwonlyargcount",
        "co_nlocals",
        "co_stacksize",
        "co_flags",
    ):
        current = object.__getattribute__(code, name)
        expected = object.__getattribute__(trusted, name)
        if (
            type(current) is not int
            or type(expected) is not int
            or int.__eq__(current, expected) is not True
        ):
            return False
    for name in ("co_filename", "co_name", "co_qualname"):
        current = object.__getattribute__(code, name)
        expected = object.__getattribute__(trusted, name)
        if (
            type(current) is not str
            or type(expected) is not str
            or str.__eq__(current, expected) is not True
        ):
            return False
    return _same_exact_code_constants(
        object.__getattribute__(code, "co_consts"),
        object.__getattribute__(trusted, "co_consts"),
    )


def _trusted_frozen_mutators(
    field_names: tuple[str, ...],
) -> tuple[FunctionType, FunctionType]:
    global _TRANSIENT_FROZEN_MUTATOR_WITNESS_GENERATIONS
    trusted = _FIXED_TRUSTED_FROZEN_MUTATORS.get(field_names)
    if trusted is None:
        witness = make_dataclass(
            "_GeneratedFrozenMutatorWitness",
            tuple((name, Any) for name in field_names),
            frozen=True,
        )
        trusted = (
            witness.__dict__["__setattr__"],
            witness.__dict__["__delattr__"],
        )
        _TRANSIENT_FROZEN_MUTATOR_WITNESS_GENERATIONS += 1
    return trusted


def _is_exact_legacy_slots_replacement(
    value_type: type[Any],
    namespace: MappingProxyType,
    closure_class: Any,
) -> bool:
    """Recognize CPython 3.12/3.13 frozen-slots replacement exactly.

    Older CPython releases generate frozen mutators before ``slots=True``
    replaces the original class.  Their ``cls`` closure therefore binds the
    non-slotted source class, not the returned slotted class.  Accept that
    standard-library shape only when the two complete namespaces have the
    exact copy-and-replace relationship produced by ``dataclasses``.
    """

    if type(closure_class) is not type or closure_class is value_type:
        return False
    try:
        origin_namespace = type.__getattribute__(closure_class, "__dict__")
        value_bases = type.__getattribute__(value_type, "__bases__")
        origin_bases = type.__getattribute__(closure_class, "__bases__")
        value_name = type.__getattribute__(value_type, "__name__")
        origin_name = type.__getattribute__(closure_class, "__name__")
        value_qualname = type.__getattribute__(value_type, "__qualname__")
        origin_qualname = type.__getattribute__(closure_class, "__qualname__")
        value_module = type.__getattribute__(value_type, "__module__")
        origin_module = type.__getattribute__(closure_class, "__module__")
        value_entry_count = len(namespace)
        origin_entry_count = len(origin_namespace)
    except (AttributeError, MemoryError, RuntimeError, TypeError):
        return False
    if (
        type(origin_namespace) is not MappingProxyType
        or type(value_bases) is not tuple
        or type(origin_bases) is not tuple
        or value_bases != (object,)
        or origin_bases != (object,)
        or type(value_name) is not str
        or type(origin_name) is not str
        or str.__eq__(value_name, origin_name) is not True
        or type(value_qualname) is not str
        or type(origin_qualname) is not str
        or value_qualname is not origin_qualname
        or type(value_module) is not str
        or type(origin_module) is not str
        or value_module is not origin_module
        or type(value_entry_count) is not int
        or type(origin_entry_count) is not int
        or value_entry_count > MAX_FROZEN_ARTIFACT_CLASS_BINDINGS
        or origin_entry_count > MAX_FROZEN_ARTIFACT_CLASS_BINDINGS
    ):
        return False
    try:
        value_entries = tuple(namespace.items())
        origin_entries = tuple(origin_namespace.items())
    except (MemoryError, RuntimeError, TypeError):
        return False
    if (
        len(value_entries) != value_entry_count
        or len(origin_entries) != origin_entry_count
        or len(namespace) != value_entry_count
        or len(origin_namespace) != origin_entry_count
        or not all(
            type(entry) is tuple and type(entry[0]) is str for entry in value_entries
        )
        or not all(
            type(entry) is tuple and type(entry[0]) is str for entry in origin_entries
        )
    ):
        return False

    field_table = namespace.get("__dataclass_fields__", _ABSENT_CLASS_BINDING)
    params = namespace.get("__dataclass_params__", _ABSENT_CLASS_BINDING)
    slots_binding = namespace.get("__slots__", _ABSENT_CLASS_BINDING)
    if type(field_table) is not dict or type(params) is not _DATACLASS_PARAMS_TYPE:
        return False
    field_entry_count = len(field_table)
    if (
        type(field_entry_count) is not int
        or field_entry_count > MAX_FROZEN_ARTIFACT_FIELDS
    ):
        return False
    try:
        param_state = {
            name: object.__getattribute__(params, name)
            for name in _DATACLASS_PARAMS_SLOT_NAMES
        }
    except (AttributeError, MemoryError):
        return False
    if (
        param_state.get("frozen") is not True
        or ("slots" in param_state and param_state["slots"] is not True)
        or ("weakref_slot" in param_state and param_state["weakref_slot"] is not False)
    ):
        return False
    try:
        field_names = tuple(field_table)
    except (MemoryError, RuntimeError):
        return False
    if len(field_names) != field_entry_count or len(field_table) != field_entry_count:
        return False
    if (
        not _same_exact_string_tuple(slots_binding, field_names)
        or origin_namespace.get("__slots__", _ABSENT_CLASS_BINDING)
        is not _ABSENT_CLASS_BINDING
        or origin_namespace.get("__dataclass_fields__", _ABSENT_CLASS_BINDING)
        is not field_table
        or origin_namespace.get("__dataclass_params__", _ABSENT_CLASS_BINDING)
        is not params
        or origin_namespace.get("__setattr__", _ABSENT_CLASS_BINDING)
        is not namespace.get("__setattr__", _ABSENT_CLASS_BINDING)
        or origin_namespace.get("__delattr__", _ABSENT_CLASS_BINDING)
        is not namespace.get("__delattr__", _ABSENT_CLASS_BINDING)
    ):
        return False

    origin_instance_dict = origin_namespace.get("__dict__", _ABSENT_CLASS_BINDING)
    origin_weakref = origin_namespace.get("__weakref__", _ABSENT_CLASS_BINDING)
    if (
        type(origin_instance_dict) is not GetSetDescriptorType
        or origin_instance_dict.__objclass__ is not closure_class
        or origin_instance_dict.__name__ != "__dict__"
        or type(origin_weakref) is not GetSetDescriptorType
        or origin_weakref.__objclass__ is not closure_class
        or origin_weakref.__name__ != "__weakref__"
        or "__dict__" in namespace
        or "__weakref__" in namespace
    ):
        return False

    try:
        value_keys = {entry[0] for entry in value_entries}
        origin_keys = {entry[0] for entry in origin_entries}
        expected_value_only = {"__slots__"}
        for field_name in field_names:
            if field_name not in origin_namespace:
                expected_value_only.add(field_name)
        for state_name, trusted_state_method in _TRUSTED_SLOTTED_FROZEN_STATE_METHODS:
            if state_name not in origin_namespace:
                expected_value_only.add(state_name)
                if (
                    namespace.get(state_name, _ABSENT_CLASS_BINDING)
                    is not trusted_state_method
                ):
                    return False
        field_name_set = set(field_names)
        common_keys = value_keys & origin_keys
        value_only_keys = value_keys - origin_keys
        origin_only_keys = origin_keys - value_keys
    except (MemoryError, RuntimeError):
        return False
    if value_only_keys != expected_value_only or origin_only_keys != {
        "__dict__",
        "__weakref__",
    }:
        return False

    for name in common_keys:
        value_binding = namespace[name]
        origin_binding = origin_namespace[name]
        if name in field_name_set:
            if (
                type(value_binding) is not MemberDescriptorType
                or value_binding.__objclass__ is not value_type
                or value_binding.__name__ != name
                or not _is_bounded_inert_scalar_tuple(origin_binding)
            ):
                return False
        elif value_binding is not origin_binding:
            return False
    for field_name in field_names:
        value_binding = namespace.get(field_name, _ABSENT_CLASS_BINDING)
        if (
            type(value_binding) is not MemberDescriptorType
            or value_binding.__objclass__ is not value_type
            or value_binding.__name__ != field_name
        ):
            return False
    return True


def _capture_frozen_mutator_shape(
    value_type: type[Any],
    namespace: MappingProxyType,
    *,
    operation: str,
    trusted_function: FunctionType | None,
    pinned: _PinnedFrozenMutatorShape | None,
    error_type: type[Exception],
) -> _PinnedFrozenMutatorShape:
    function = namespace.get(operation, _ABSENT_CLASS_BINDING)
    _require_shape(
        type(function) is FunctionType,
        f"canonical frozen dataclass {operation} is not one exact function",
        error_type=error_type,
    )
    code = object.__getattribute__(function, "__code__")
    if pinned is None:
        _require_shape(
            type(trusted_function) is FunctionType
            and _same_generated_mutator_code(
                code,
                object.__getattribute__(trusted_function, "__code__"),
            ),
            f"canonical frozen dataclass {operation} lacks generated-code equivalence",
            error_type=error_type,
        )
    else:
        _require_shape(
            trusted_function is None
            and function is pinned.function
            and code is pinned.code,
            f"canonical frozen dataclass {operation} changed after registration",
            error_type=error_type,
        )
    closure = object.__getattribute__(function, "__closure__")
    _require_shape(
        type(closure) is tuple and len(closure) == len(code.co_freevars),
        f"canonical frozen dataclass {operation} closure is malformed",
        error_type=error_type,
    )
    closure_cells: list[Any] = []
    closure_bindings: dict[str, Any] = {}
    try:
        for name, cell in zip(code.co_freevars, closure, strict=True):
            _require_shape(
                type(cell) is CellType,
                f"canonical frozen dataclass {operation} closure cell is not exact",
                error_type=error_type,
            )
            content = cell.cell_contents
            closure_cells.append(content)
            closure_bindings[name] = content
    except ValueError as exc:
        raise error_type(
            f"canonical frozen dataclass {operation} closure cell is empty"
        ) from exc
    closure_class = closure_bindings.get(
        "__class__",
        closure_bindings.get("cls", _ABSENT_CLASS_BINDING),
    )
    _require_shape(
        type(closure_bindings) is dict
        and len(closure_bindings) == 2
        and set(closure_bindings)
        in (
            {"FrozenInstanceError", "__class__"},
            {"FrozenInstanceError", "cls"},
        )
        and closure_bindings["FrozenInstanceError"] is FrozenInstanceError
        and (
            closure_class is value_type
            or _is_exact_legacy_slots_replacement(
                value_type,
                namespace,
                closure_class,
            )
        ),
        f"canonical frozen dataclass {operation} closure binds another class",
        error_type=error_type,
    )
    globals_dict = object.__getattribute__(function, "__globals__")
    builtins_dict = object.__getattribute__(function, "__builtins__")
    annotations = object.__getattribute__(function, "__annotations__")
    function_dict = object.__getattribute__(function, "__dict__")
    _require_shape(
        type(globals_dict) is dict
        and globals_dict.get("type", type) is type
        and globals_dict.get("super", super) is super
        and type(builtins_dict) is dict
        and builtins_dict.get("type") is type
        and builtins_dict.get("super") is super
        and object.__getattribute__(function, "__defaults__") is None
        and object.__getattribute__(function, "__kwdefaults__") is None
        and type(annotations) is dict
        and not annotations
        and type(function_dict) is dict
        and not function_dict,
        f"canonical frozen dataclass {operation} function state is not inert",
        error_type=error_type,
    )
    return _PinnedFrozenMutatorShape(
        function=function,
        code=code,
        closure=closure,
        closure_cells=tuple(closure_cells),
        globals_dict=globals_dict,
        builtins_dict=builtins_dict,
        annotations=annotations,
        function_dict=function_dict,
    )


def _is_bounded_inert_scalar_tuple(value: Any) -> bool:
    """Return whether a default is one bounded exact scalar/tuple tree."""

    stack: list[tuple[Any, int]] = [(value, 0)]
    remaining = MAX_INERT_DEFAULT_NODES
    aggregate_scalar_bytes = 0
    while stack:
        item, depth = stack.pop()
        remaining -= 1
        if remaining < 0 or depth > MAX_INERT_DEFAULT_DEPTH:
            return False
        scalar_bytes = 0
        if item is None:
            continue
        if type(item) is bool:
            scalar_bytes = 1
        if type(item) is int:
            if item.bit_length() > MAX_INERT_DEFAULT_INTEGER_BITS:
                return False
            scalar_bytes = max(1, (item.bit_length() + 7) // 8)
        elif type(item) is float:
            if not math.isfinite(item):
                return False
            scalar_bytes = 8
        elif type(item) is bytes:
            if len(item) > MAX_INERT_DEFAULT_SCALAR_BYTES:
                return False
            scalar_bytes = len(item)
        elif type(item) is str:
            if len(item) > MAX_INERT_DEFAULT_SCALAR_BYTES:
                return False
            octets = 0
            for character in item:
                code_point = ord(character)
                if 0xD800 <= code_point <= 0xDFFF:
                    return False
                octets += (
                    1
                    + (code_point > 0x7F)
                    + (code_point > 0x7FF)
                    + (code_point > 0xFFFF)
                )
                if octets > MAX_INERT_DEFAULT_SCALAR_BYTES:
                    return False
            scalar_bytes = octets
        elif type(item) is tuple:
            if len(item) > MAX_INERT_DEFAULT_NODES:
                return False
            stack.extend((child, depth + 1) for child in item)
            continue
        elif type(item) is not bool:
            return False
        aggregate_scalar_bytes += scalar_bytes
        if aggregate_scalar_bytes > MAX_INERT_DEFAULT_AGGREGATE_SCALAR_BYTES:
            return False
    return True


def _capture_field_shape(
    field_value: Any,
    *,
    class_binding: Any,
    error_type: type[Exception],
) -> _PinnedFieldShape:
    _require_shape(
        type(field_value) is Field,
        "canonical dataclass field object type is not exact",
        error_type=error_type,
    )
    try:
        state = tuple(
            (name, object.__getattribute__(field_value, name))
            for name in _FIELD_SLOT_NAMES
        )
    except AttributeError as exc:
        raise error_type("canonical dataclass field object is incomplete") from exc
    state_by_name = {name: value for name, value in state}
    field_name = state_by_name.get("name")
    _require_shape(
        type(field_name) is str and bool(field_name),
        "canonical dataclass field name is not one exact nonempty string",
        error_type=error_type,
    )
    _require_shape(
        state_by_name.get("metadata") is _EMPTY_FIELD_METADATA,
        "canonical dataclass field metadata must be the exact empty sentinel",
        error_type=error_type,
    )
    return _PinnedFieldShape(
        field=field_value,
        name=field_name,
        state=state,
        class_binding=class_binding,
    )


def _capture_class_shape(
    value_type: Any,
    *,
    error_type: type[Exception],
    pinned: _PinnedClassShape | None = None,
) -> _PinnedClassShape:
    """Capture the exact dataclass surface used by canonical field reads."""

    _require_shape(
        type(value_type) is type,
        "canonical artifact class metaclass is not exact type",
        error_type=error_type,
    )
    try:
        namespace = type.__getattribute__(value_type, "__dict__")
        bases = type.__getattribute__(value_type, "__bases__")
        resolved_getattribute = type.__getattribute__(value_type, "__getattribute__")
    except AttributeError as exc:
        raise error_type("canonical artifact class shape is incomplete") from exc
    _require_shape(
        type(namespace) is MappingProxyType,
        "canonical artifact class namespace is not exact",
        error_type=error_type,
    )
    _require_shape(
        type(bases) is tuple and bases == (object,),
        "canonical artifact class must derive directly from object",
        error_type=error_type,
    )
    _require_shape(
        resolved_getattribute is object.__getattribute__
        and "__getattribute__" not in namespace
        and "__getattr__" not in namespace,
        "canonical artifact class has a dynamic attribute accessor",
        error_type=error_type,
    )

    params = namespace.get("__dataclass_params__")
    _require_shape(
        type(params) is _DATACLASS_PARAMS_TYPE,
        "canonical artifact dataclass parameters are missing or forged",
        error_type=error_type,
    )
    try:
        param_state = tuple(
            (name, object.__getattribute__(params, name))
            for name in _DATACLASS_PARAMS_SLOT_NAMES
        )
    except AttributeError as exc:
        raise error_type(
            "canonical artifact dataclass parameters are incomplete"
        ) from exc
    param_by_name = {name: value for name, value in param_state}
    _require_shape(
        all(type(value) is bool for value in param_by_name.values())
        and param_by_name.get("frozen") is True,
        "canonical artifact must be one exact frozen dataclass",
        error_type=error_type,
    )

    field_table = namespace.get("__dataclass_fields__")
    _require_shape(
        type(field_table) is dict,
        "canonical artifact field table is not an exact dict",
        error_type=error_type,
    )
    _require_shape(
        len(field_table) <= MAX_FROZEN_ARTIFACT_FIELDS,
        "canonical artifact field table exceeds its registration limit",
        error_type=error_type,
    )
    try:
        table_entries = tuple(field_table.items())
    except RuntimeError as exc:
        raise error_type("canonical artifact field table is malformed") from exc
    _require_shape(
        len(table_entries) == len(field_table)
        and all(
            type(entry) is tuple
            and len(entry) == 2
            and type(entry[0]) is str
            and type(entry[1]) is Field
            and object.__getattribute__(entry[1], "_field_type")
            is _DATACLASS_FIELD_SENTINEL
            for entry in table_entries
        ),
        "canonical artifact field table contains a non-field member",
        error_type=error_type,
    )
    artifact_fields = tuple(entry[1] for entry in table_entries)
    for table_entry, field_value in zip(table_entries, artifact_fields, strict=True):
        table_name, table_field = table_entry
        _require_shape(
            type(table_name) is str
            and table_field is field_value
            and object.__getattribute__(field_value, "name") is table_name,
            "canonical artifact field table identity or order is unstable",
            error_type=error_type,
        )
    field_names = tuple(entry[0] for entry in table_entries)
    aggregate_field_name_bytes = 0
    for field_name in field_names:
        aggregate_field_name_bytes += _bounded_utf8_length(
            field_name,
            maximum=MAX_FROZEN_FIELD_NAME_BYTES,
            label="canonical dataclass field name",
            error_type=error_type,
        )
        _require_shape(
            aggregate_field_name_bytes <= MAX_FROZEN_ARTIFACT_FIELD_NAME_BYTES,
            "canonical dataclass field names exceed their aggregate byte limit",
            error_type=error_type,
        )
    if pinned is None:
        trusted_setattr, trusted_delattr = _trusted_frozen_mutators(field_names)
        pinned_setattr = None
        pinned_delattr = None
    else:
        _require_shape(
            _same_exact_string_tuple(
                field_names,
                tuple(field.name for field in pinned.fields),
            ),
            "canonical dataclass field names changed after registration",
            error_type=error_type,
        )
        trusted_setattr = None
        trusted_delattr = None
        pinned_setattr = pinned.setattr_mutator
        pinned_delattr = pinned.delattr_mutator
    setattr_mutator = _capture_frozen_mutator_shape(
        value_type,
        namespace,
        operation="__setattr__",
        trusted_function=trusted_setattr,
        pinned=pinned_setattr,
        error_type=error_type,
    )
    delattr_mutator = _capture_frozen_mutator_shape(
        value_type,
        namespace,
        operation="__delattr__",
        trusted_function=trusted_delattr,
        pinned=pinned_delattr,
        error_type=error_type,
    )

    slots_binding = namespace.get("__slots__", _ABSENT_CLASS_BINDING)
    slotted = slots_binding is not _ABSENT_CLASS_BINDING
    instance_dict_binding: Any = _ABSENT_CLASS_BINDING
    if slotted:
        _require_shape(
            type(slots_binding) is tuple
            and all(type(name) is str for name in slots_binding)
            and slots_binding == field_names
            and "__dict__" not in namespace,
            "canonical slotted artifact has hidden or malformed slots",
            error_type=error_type,
        )
    else:
        instance_dict_binding = namespace.get("__dict__", _ABSENT_CLASS_BINDING)
        _require_shape(
            type(instance_dict_binding) is GetSetDescriptorType
            and instance_dict_binding.__objclass__ is value_type
            and instance_dict_binding.__name__ == "__dict__",
            "canonical non-slot artifact lacks one native instance dict",
            error_type=error_type,
        )

    pinned_fields: list[_PinnedFieldShape] = []
    for field_value in artifact_fields:
        field_name = object.__getattribute__(field_value, "name")
        class_binding = namespace.get(field_name, _ABSENT_CLASS_BINDING)
        if slotted:
            _require_shape(
                type(class_binding) is MemberDescriptorType
                and class_binding.__objclass__ is value_type
                and class_binding.__name__ == field_name,
                "canonical slot field binding is not one exact native descriptor",
                error_type=error_type,
            )
        else:
            _require_shape(
                class_binding is _ABSENT_CLASS_BINDING
                or _is_bounded_inert_scalar_tuple(class_binding),
                "canonical non-slot field binding is not absent or inert",
                error_type=error_type,
            )
        pinned_fields.append(
            _capture_field_shape(
                field_value,
                class_binding=class_binding,
                error_type=error_type,
            )
        )

    return _PinnedClassShape(
        value_type=value_type,
        dataclass_params=params,
        dataclass_param_state=param_state,
        field_table=field_table,
        fields=tuple(pinned_fields),
        slotted=slotted,
        slots_binding=slots_binding,
        instance_dict_binding=instance_dict_binding,
        setattr_mutator=setattr_mutator,
        delattr_mutator=delattr_mutator,
    )


def _same_identity_pairs(
    current: tuple[tuple[Any, Any], ...],
    pinned: tuple[tuple[Any, Any], ...],
) -> bool:
    return len(current) == len(pinned) and all(
        current_key is pinned_key and current_value is pinned_value
        for (current_key, current_value), (pinned_key, pinned_value) in zip(
            current,
            pinned,
            strict=True,
        )
    )


def _same_mutator_shape(
    current: _PinnedFrozenMutatorShape,
    pinned: _PinnedFrozenMutatorShape,
) -> bool:
    return (
        current.function is pinned.function
        and current.code is pinned.code
        and current.closure is pinned.closure
        and current.globals_dict is pinned.globals_dict
        and current.builtins_dict is pinned.builtins_dict
        and current.annotations is pinned.annotations
        and current.function_dict is pinned.function_dict
        and len(current.closure_cells) == len(pinned.closure_cells)
        and all(
            current_value is pinned_value
            for current_value, pinned_value in zip(
                current.closure_cells,
                pinned.closure_cells,
                strict=True,
            )
        )
    )


def _revalidate_class_shape(
    pinned: _PinnedClassShape,
    *,
    error_type: type[Exception],
) -> None:
    current = _capture_class_shape(
        pinned.value_type,
        error_type=error_type,
        pinned=pinned,
    )
    _require_shape(
        current.value_type is pinned.value_type
        and current.dataclass_params is pinned.dataclass_params
        and _same_identity_pairs(
            current.dataclass_param_state,
            pinned.dataclass_param_state,
        )
        and current.field_table is pinned.field_table
        and current.slotted is pinned.slotted
        and current.slots_binding is pinned.slots_binding
        and current.instance_dict_binding is pinned.instance_dict_binding
        and _same_mutator_shape(current.setattr_mutator, pinned.setattr_mutator)
        and _same_mutator_shape(current.delattr_mutator, pinned.delattr_mutator)
        and len(current.fields) == len(pinned.fields),
        "canonical artifact class shape changed after registration",
        error_type=error_type,
    )
    for current_field, pinned_field in zip(
        current.fields,
        pinned.fields,
        strict=True,
    ):
        _require_shape(
            current_field.field is pinned_field.field
            and current_field.name is pinned_field.name
            and current_field.class_binding is pinned_field.class_binding
            and _same_identity_pairs(current_field.state, pinned_field.state),
            "canonical artifact field shape changed after registration",
            error_type=error_type,
        )


def _snapshot_artifact_values(
    value: Any,
    *,
    pinned: _PinnedClassShape,
    error_type: type[Exception],
    revalidate_class: bool = True,
) -> tuple[tuple[_PinnedFieldShape, Any], ...]:
    """Optionally revalidate one class, then read every field exactly once."""

    _require_shape(
        type(value) is pinned.value_type,
        "registered canonical artifact instance type is not exact",
        error_type=error_type,
    )
    if revalidate_class:
        _revalidate_class_shape(pinned, error_type=error_type)
    if not pinned.slotted:
        try:
            instance_dict = object.__getattribute__(value, "__dict__")
            instance_keys = tuple(instance_dict)
        except (AttributeError, RuntimeError, TypeError) as exc:
            raise error_type("canonical artifact instance dict is unavailable") from exc
        field_names = tuple(field.name for field in pinned.fields)
        _require_shape(
            type(instance_dict) is dict
            and len(instance_keys) == len(instance_dict) == len(field_names)
            and all(type(key) is str for key in instance_keys)
            and set(instance_keys) == set(field_names),
            "canonical artifact instance dict keys do not match its pinned fields",
            error_type=error_type,
        )
    snapshots: list[tuple[_PinnedFieldShape, Any]] = []
    try:
        for field_shape in pinned.fields:
            snapshots.append(
                (
                    field_shape,
                    object.__getattribute__(value, field_shape.name),
                )
            )
    except AttributeError as exc:
        raise error_type("canonical artifact field value is unavailable") from exc
    return tuple(snapshots)


@dataclass(frozen=True, slots=True)
class FrozenTypeRegistry(Mapping[type[Any], str]):
    """Tuple-backed registry that pins each canonical dataclass access surface."""

    entries: tuple[tuple[type[Any], str], ...]
    _shapes: tuple[tuple[str, _PinnedClassShape], ...] = dataclass_field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple:
            raise ValueError("frozen type registry backing is not an exact tuple")
        if len(self.entries) > MAX_FROZEN_TYPE_REGISTRY_ENTRIES:
            raise ValueError("frozen type registry exceeds its entry limit")
        seen_types: set[type[Any]] = set()
        seen_ids: set[str] = set()
        shapes: list[tuple[str, _PinnedClassShape]] = []
        total_fields = 0
        total_id_bytes = 0
        for entry in self.entries:
            if (
                type(entry) is not tuple
                or len(entry) != 2
                or type(entry[0]) is not type
                or type(entry[1]) is not str
                or not entry[1]
            ):
                raise ValueError("frozen type registry is malformed or aliased")
            total_id_bytes += _bounded_utf8_length(
                entry[1],
                maximum=MAX_FROZEN_TYPE_ID_BYTES,
                label="frozen type registry identifier",
                error_type=ValueError,
            )
            if total_id_bytes > MAX_FROZEN_TYPE_REGISTRY_ID_BYTES:
                raise ValueError("frozen type registry identifiers exceed their limit")
            if entry[0] in seen_types or entry[1] in seen_ids:
                raise ValueError("frozen type registry is malformed or aliased")
            seen_types.add(entry[0])
            seen_ids.add(entry[1])
            shape = _capture_class_shape(entry[0], error_type=ValueError)
            total_fields += len(shape.fields)
            if total_fields > MAX_FROZEN_TYPE_REGISTRY_FIELDS:
                raise ValueError("frozen type registry exceeds its field limit")
            shapes.append((entry[1], shape))
        object.__setattr__(self, "_shapes", tuple(shapes))

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return (value_type for value_type, _stable_id in self.entries)

    def __getitem__(self, value_type: type[Any]) -> str:
        for candidate, stable_id in self.entries:
            if candidate is value_type:
                return stable_id
        raise KeyError(value_type)

    def revalidated_shape_view(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Return stable IDs and pinned field names after exact revalidation."""

        view: list[tuple[str, tuple[str, ...]]] = []
        for _value_type, stable_id, pinned in _aligned_frozen_registry_entries(
            self,
            error_type=ValueError,
        ):
            _revalidate_class_shape(pinned, error_type=ValueError)
            view.append((stable_id, tuple(field.name for field in pinned.fields)))
        return tuple(view)

    def snapshot_artifact_view(
        self,
        value: Any,
    ) -> tuple[str, tuple[tuple[str, Any], ...]]:
        """Revalidate and snapshot one exactly registered artifact."""

        value_type = type(value)
        selected: tuple[str, _PinnedClassShape] | None = None
        for candidate, stable_id, pinned in _aligned_frozen_registry_entries(
            self,
            error_type=ValueError,
        ):
            if candidate is value_type:
                selected = (stable_id, pinned)
        if selected is None:
            raise ValueError("artifact type is not in the exact frozen registry")
        stable_id, pinned = selected
        snapshot = _snapshot_artifact_values(
            value,
            pinned=pinned,
            error_type=ValueError,
        )
        return (
            stable_id,
            tuple((field.name, field_value) for field, field_value in snapshot),
        )


def _aligned_frozen_registry_entries(
    registry: Any,
    *,
    error_type: type[Exception],
) -> tuple[tuple[type[Any], str, _PinnedClassShape], ...]:
    """Verify registry alignment without revalidating registered classes."""

    if type(registry) is not FrozenTypeRegistry:
        raise error_type("frozen type registry receiver type is not exact")
    try:
        entries = object.__getattribute__(registry, "entries")
        shapes = object.__getattribute__(registry, "_shapes")
    except AttributeError as exc:
        raise error_type("frozen type registry shape snapshot is missing") from exc
    if (
        type(entries) is not tuple
        or type(shapes) is not tuple
        or len(entries) != len(shapes)
        or len(entries) > MAX_FROZEN_TYPE_REGISTRY_ENTRIES
    ):
        raise error_type("frozen type registry shape snapshot changed")
    aligned: list[tuple[type[Any], str, _PinnedClassShape]] = []
    seen_types: set[type[Any]] = set()
    seen_ids: set[str] = set()
    aggregate_id_bytes = 0
    aggregate_fields = 0
    for entry, shape_entry in zip(entries, shapes, strict=True):
        if (
            type(entry) is not tuple
            or len(entry) != 2
            or type(shape_entry) is not tuple
            or len(shape_entry) != 2
            or type(entry[0]) is not type
            or type(entry[1]) is not str
            or not entry[1]
            or shape_entry[0] is not entry[1]
            or type(shape_entry[1]) is not _PinnedClassShape
            or shape_entry[1].value_type is not entry[0]
            or type(shape_entry[1].fields) is not tuple
            or len(shape_entry[1].fields) > MAX_FROZEN_ARTIFACT_FIELDS
            or not all(
                type(field) is _PinnedFieldShape for field in shape_entry[1].fields
            )
        ):
            raise error_type("frozen type registry shape snapshot changed")
        stable_id_bytes = _bounded_utf8_length(
            entry[1],
            maximum=MAX_FROZEN_TYPE_ID_BYTES,
            label="frozen type registry identifier",
            error_type=error_type,
        )
        aggregate_id_bytes += stable_id_bytes
        aggregate_fields += len(shape_entry[1].fields)
        if (
            aggregate_id_bytes > MAX_FROZEN_TYPE_REGISTRY_ID_BYTES
            or aggregate_fields > MAX_FROZEN_TYPE_REGISTRY_FIELDS
            or entry[0] in seen_types
            or entry[1] in seen_ids
        ):
            raise error_type("frozen type registry shape snapshot changed")
        seen_types.add(entry[0])
        seen_ids.add(entry[1])
        aligned.append((entry[0], entry[1], shape_entry[1]))
    return tuple(aligned)


def _bounded_frozen_map_entries(
    value: FrozenMap,
    *,
    maximum_entries: int,
    maximum_key_bytes: int,
    maximum_aggregate_key_bytes: int,
    error_type: type[Exception],
) -> tuple[tuple[str, Any, int], ...]:
    entries = object.__getattribute__(value, "entries")
    if type(entries) is not tuple:
        raise error_type("frozen mapping backing is not an exact tuple")
    if len(entries) > maximum_entries:
        raise error_type("frozen mapping exceeds its entry-count limit")
    validated: list[tuple[str, Any, int]] = []
    aggregate_key_bytes = 0
    for entry in entries:
        if type(entry) is not tuple or len(entry) != 2 or type(entry[0]) is not str:
            raise error_type("frozen mapping contains a malformed exact pair")
        key, child = entry
        key_bytes = _bounded_utf8_length(
            key,
            maximum=maximum_key_bytes,
            label="frozen mapping key",
            error_type=error_type,
        )
        aggregate_key_bytes += key_bytes
        if aggregate_key_bytes > maximum_aggregate_key_bytes:
            raise error_type("frozen mapping keys exceed their aggregate byte limit")
        validated.append((key, child, key_bytes))
    for index in range(1, len(validated)):
        if validated[index - 1][0] >= validated[index][0]:
            raise error_type("frozen mapping keys are duplicate or unordered")
    return tuple(validated)


def _bounded_utf8_length(
    value: Any,
    *,
    maximum: int,
    label: str,
    error_type: type[Exception],
) -> int:
    if type(value) is not str:
        raise error_type(f"{label} type is not exact")
    if len(value) > maximum:
        raise error_type(f"{label} exceeds the UTF-8 limit")
    total = 0
    for character in value:
        code_point = ord(character)
        if 0xD800 <= code_point <= 0xDFFF:
            raise error_type(f"{label} is not a Unicode scalar sequence")
        if code_point <= 0x7F:
            total += 1
        elif code_point <= 0x7FF:
            total += 2
        elif code_point <= 0xFFFF:
            total += 3
        else:
            total += 4
        if total > maximum:
            raise error_type(f"{label} exceeds the UTF-8 limit")
    return total


def _snapshot_type_registry(
    type_ids: Mapping[type[Any], str],
    *,
    limits: CanonicalLimits,
    error_type: type[Exception],
) -> dict[int, tuple[type[Any], str, _PinnedClassShape]]:
    _validate_limits_exact(limits, error_type=error_type)
    if type(type_ids) not in (dict, FrozenTypeRegistry):
        raise error_type("canonical type registry type is not exact")
    frozen_shapes: tuple[tuple[str, _PinnedClassShape], ...] | None = None
    if type(type_ids) is FrozenTypeRegistry:
        try:
            registry_items = object.__getattribute__(type_ids, "entries")
            frozen_shapes = object.__getattribute__(type_ids, "_shapes")
        except AttributeError as exc:
            raise error_type("frozen type registry shape snapshot is missing") from exc
        if type(registry_items) is not tuple or type(frozen_shapes) is not tuple:
            raise error_type("frozen type registry backing is not exact")
        expected_length = len(registry_items)
    else:
        expected_length = len(type_ids)
        try:
            registry_items = tuple(type_ids.items())
        except RuntimeError as exc:
            raise error_type("canonical type registry changed during snapshot") from exc
    if expected_length > min(
        limits.max_nodes,
        MAX_FROZEN_TYPE_REGISTRY_ENTRIES,
    ):
        raise error_type("canonical type registry exceeds its entry limit")
    if len(registry_items) != expected_length or (
        type(type_ids) is dict and len(type_ids) != expected_length
    ):
        raise error_type("canonical type registry changed during snapshot")
    if any(type(entry) is not tuple or len(entry) != 2 for entry in registry_items):
        raise error_type("canonical type registry contains a malformed exact pair")
    if frozen_shapes is not None and len(frozen_shapes) != len(registry_items):
        raise error_type("frozen type registry shape snapshot changed")
    total_registry_bytes = 0
    seen_type_ids: set[int] = set()
    seen_ids: set[str] = set()
    closed_entries: list[tuple[type[Any], str, _PinnedClassShape]] = []
    total_fields = 0
    maximum_artifact_fields = min(
        limits.max_artifact_fields,
        MAX_FROZEN_ARTIFACT_FIELDS,
    )
    for index, (value_type, stable_id) in enumerate(registry_items):
        if type(value_type) is not type or type(stable_id) is not str or not stable_id:
            raise error_type("canonical type registry is malformed or aliased")
        stable_id_bytes = _bounded_utf8_length(
            stable_id,
            maximum=min(limits.max_string_bytes, MAX_FROZEN_TYPE_ID_BYTES),
            label="canonical type registry identifier",
            error_type=error_type,
        )
        if id(value_type) in seen_type_ids or stable_id in seen_ids:
            raise error_type("canonical type registry is malformed or aliased")
        if frozen_shapes is None:
            pinned_shape = _capture_class_shape(value_type, error_type=error_type)
        else:
            shape_entry = frozen_shapes[index]
            if (
                type(shape_entry) is not tuple
                or len(shape_entry) != 2
                or shape_entry[0] is not stable_id
                or type(shape_entry[1]) is not _PinnedClassShape
                or shape_entry[1].value_type is not value_type
                or type(shape_entry[1].fields) is not tuple
                or len(shape_entry[1].fields) > maximum_artifact_fields
                or not all(
                    type(field_shape) is _PinnedFieldShape
                    for field_shape in shape_entry[1].fields
                )
            ):
                raise error_type("frozen type registry shape snapshot changed")
            pinned_shape = shape_entry[1]
        if len(pinned_shape.fields) > maximum_artifact_fields:
            raise error_type("canonical artifact exceeds its field-count limit")
        total_fields += len(pinned_shape.fields)
        if total_fields > MAX_FROZEN_TYPE_REGISTRY_FIELDS:
            raise error_type("canonical type registry exceeds its field limit")
        seen_type_ids.add(id(value_type))
        seen_ids.add(stable_id)
        total_registry_bytes += stable_id_bytes
        if total_registry_bytes > min(
            limits.max_aggregate_scalar_bytes,
            MAX_FROZEN_TYPE_REGISTRY_ID_BYTES,
        ):
            raise error_type("canonical type registry exceeds its aggregate byte limit")
        closed_entries.append((value_type, stable_id, pinned_shape))
    return {
        id(value_type): (value_type, stable_id, pinned_shape)
        for value_type, stable_id, pinned_shape in closed_entries
    }


class _Writer:
    def __init__(
        self,
        *,
        style: Style,
        limits: CanonicalLimits,
        type_ids: Mapping[type[Any], str],
        error_type: type[Exception],
    ) -> None:
        _validate_error_type(error_type)
        _validate_limits_exact(limits, error_type=error_type)
        self.style = style
        self.limits = limits
        self.error_type = error_type
        self.type_ids = _snapshot_type_registry(
            type_ids,
            limits=limits,
            error_type=error_type,
        )
        self.output = bytearray()
        self.remaining_nodes = limits.max_nodes
        self.aggregate_scalar_bytes = 0
        self.active_container_ids: set[int] = set()
        # A class-shape validation result is valid only for this traversal.
        self.revalidated_type_ids: set[int] = set()

    def fail(self, message: str) -> None:
        raise self.error_type(message)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.fail(message)

    def write(self, chunk: bytes) -> None:
        self.require(type(chunk) is bytes, "canonical output chunk type is not exact")
        self.require(
            len(self.output) + len(chunk) <= self.limits.max_output_bytes,
            "canonical JSON exceeds the output-octet limit",
        )
        self.output.extend(chunk)

    def account_node(self, depth: int) -> None:
        self.require(
            depth <= self.limits.max_depth,
            "canonical value exceeds the root-depth-0 nesting limit",
        )
        self.remaining_nodes -= 1
        self.require(
            self.remaining_nodes >= 0,
            "canonical value exceeds the input-node limit",
        )

    def account_scalar_bytes(self, count: int) -> None:
        self.require(count >= 0, "canonical scalar byte count is negative")
        self.aggregate_scalar_bytes += count
        self.require(
            self.aggregate_scalar_bytes <= self.limits.max_aggregate_scalar_bytes,
            "canonical value exceeds the aggregate scalar-byte limit",
        )

    def string_bytes(
        self,
        value: Any,
        *,
        label: str,
        account_scalar: bool = True,
    ) -> bytes:
        self.require(type(value) is str, f"{label} type is not exact")
        self.require(
            len(value) <= self.limits.max_string_bytes,
            f"{label} exceeds the UTF-8 limit",
        )
        utf8_length = 0
        json_length = 2
        self.require(
            len(self.output) + json_length <= self.limits.max_output_bytes,
            "canonical JSON exceeds the output-octet limit",
        )
        for character in value:
            code_point = ord(character)
            self.require(
                not 0xD800 <= code_point <= 0xDFFF,
                f"{label} is not a Unicode scalar sequence",
            )
            if code_point <= 0x7F:
                scalar_bytes = 1
            elif code_point <= 0x7FF:
                scalar_bytes = 2
            elif code_point <= 0xFFFF:
                scalar_bytes = 3
            else:
                scalar_bytes = 4
            utf8_length += scalar_bytes
            if character in {'"', "\\", "\b", "\t", "\n", "\f", "\r"}:
                json_length += 2
            elif code_point < 0x20:
                json_length += 6
            else:
                json_length += scalar_bytes
            self.require(
                utf8_length <= self.limits.max_string_bytes,
                f"{label} exceeds the UTF-8 limit",
            )
            self.require(
                len(self.output) + json_length <= self.limits.max_output_bytes,
                "canonical JSON exceeds the output-octet limit",
            )
        if account_scalar:
            self.account_scalar_bytes(utf8_length)
        try:
            encoded = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (UnicodeEncodeError, ValueError) as exc:
            raise self.error_type(f"{label} is not strict UTF-8 JSON") from exc
        self.require(
            len(encoded) == json_length,
            "canonical string length preflight disagrees with encoder",
        )
        return encoded

    def write_hex(self, value: bytes) -> None:
        projected = 2 * len(value)
        self.require(
            len(self.output) + projected <= self.limits.max_output_bytes,
            "canonical hexadecimal payload exceeds the output-octet limit",
        )
        view = memoryview(value)
        for offset in range(0, len(value), HEX_CHUNK_BYTES):
            chunk = view[offset : offset + HEX_CHUNK_BYTES].hex().encode("ascii")
            self.write(chunk)

    def write_string(
        self,
        value: Any,
        *,
        label: str,
        account_scalar: bool = True,
    ) -> None:
        self.write(
            self.string_bytes(
                value,
                label=label,
                account_scalar=account_scalar,
            )
        )

    def write_integer(self, value: Any) -> None:
        self.require(type(value) is int, "canonical integer type is not exact")
        self.require(
            self.limits.min_integer <= value <= self.limits.max_integer,
            "canonical integer is outside the portable safe range",
        )
        token = _bounded_integer_token(
            value,
            maximum_chars=self.limits.max_number_chars,
            label="canonical integer token",
            error_type=self.error_type,
        )
        self.write(token)

    def write_float(self, value: Any) -> None:
        self.require(
            self.limits.allow_float and type(value) is float and math.isfinite(value),
            "canonical float is unsupported, subclassed, or nonfinite",
        )
        token = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("ascii")
        self.require(
            len(token) <= self.limits.max_number_chars,
            "canonical float token exceeds its lexical limit",
        )
        self.write(token)

    def enter_container(self, value: Any) -> int:
        identity = id(value)
        self.require(
            identity not in self.active_container_ids,
            "canonical value contains a reference cycle",
        )
        self.active_container_ids.add(identity)
        return identity

    def leave_container(self, identity: int) -> None:
        self.active_container_ids.remove(identity)

    def emit_sequence(
        self,
        values: tuple[Any, ...],
        *,
        depth: int,
        prefix: bytes,
        suffix: bytes,
    ) -> None:
        self.require(
            len(values) <= self.limits.max_collection_items,
            "canonical collection exceeds its item-count limit",
        )
        self.write(prefix)
        for index, item in enumerate(values):
            if index:
                self.write(b",")
            self.emit(item, depth=depth + 1)
        self.write(suffix)

    def emit_mapping_entries(
        self,
        entries: tuple[tuple[str, Any, int], ...],
        *,
        depth: int,
        prefix: bytes,
        suffix: bytes,
        tagged_pairs: bool,
    ) -> None:
        self.require(
            len(entries) <= self.limits.max_collection_items,
            "canonical mapping exceeds its entry-count limit",
        )
        self.write(prefix)
        for index, (key, value, _key_bytes) in enumerate(entries):
            if index:
                self.write(b",")
            if tagged_pairs:
                self.write(b"[")
                self.write_string(
                    key,
                    label="canonical mapping key",
                    account_scalar=False,
                )
                self.write(b",")
                self.emit(value, depth=depth + 1)
                self.write(b"]")
            else:
                self.write_string(
                    key,
                    label="canonical mapping key",
                    account_scalar=False,
                )
                self.write(b":")
                self.emit(value, depth=depth + 1)
        self.write(suffix)

    def emit_artifact(
        self,
        *,
        depth: int,
        type_id: str,
        artifact_fields: tuple[tuple[_PinnedFieldShape, Any], ...],
    ) -> None:
        self.require(
            len(artifact_fields) <= self.limits.max_artifact_fields,
            "canonical artifact exceeds its field-count limit",
        )
        if self.style == "bridge":
            self.write(b'{"$bridge_kind":"artifact","fields":[')
            for index, (field_shape, field_value) in enumerate(artifact_fields):
                if index:
                    self.write(b",")
                self.write(b"[")
                self.write_string(
                    field_shape.name,
                    label="canonical artifact field name",
                )
                self.write(b",")
                self.emit(field_value, depth=depth + 1)
                self.write(b"]")
            self.write(b'],"type_ref":')
            self.write_string(type_id, label="canonical artifact type reference")
            self.write(b"}")
            return
        if self.style == "authority":
            self.write(b'{"$ncp_canonical_kind":"artifact","artifact_type":')
            self.write_string(type_id, label="canonical artifact type ID")
            self.write(b',"fields":{')
            ordered = sorted(artifact_fields, key=lambda item: item[0].name)
            for index, (field_shape, field_value) in enumerate(ordered):
                if index:
                    self.write(b",")
                self.write_string(
                    field_shape.name,
                    label="canonical artifact field name",
                )
                self.write(b":")
                self.emit(field_value, depth=depth + 1)
            self.write(b"}}")
            return
        if self.style == "capture_plain":
            self.write(b"{")
            ordered = sorted(artifact_fields, key=lambda item: item[0].name)
            for index, (field_shape, field_value) in enumerate(ordered):
                if index:
                    self.write(b",")
                self.write_string(
                    field_shape.name,
                    label="canonical artifact field name",
                )
                self.write(b":")
                self.emit(field_value, depth=depth + 1)
            self.write(b"}")
            return
        if self.style == "capture_typed":
            self.write(b'["artifact",')
            self.write_string(type_id, label="canonical artifact type ID")
            self.write(b",{")
            ordered = sorted(artifact_fields, key=lambda item: item[0].name)
            for index, (field_shape, field_value) in enumerate(ordered):
                if index:
                    self.write(b",")
                self.write_string(
                    field_shape.name,
                    label="canonical artifact field name",
                )
                self.write(b":")
                self.emit(field_value, depth=depth + 1)
            self.write(b"}]")
            return
        self.fail("canonical JSON profile does not admit dataclasses")

    def emit(self, value: Any, *, depth: int) -> None:
        self.account_node(depth)

        if type(value) is FrozenMap:
            mapping_entries = _bounded_frozen_map_entries(
                value,
                maximum_entries=self.limits.max_collection_items,
                maximum_key_bytes=self.limits.max_string_bytes,
                maximum_aggregate_key_bytes=(
                    self.limits.max_aggregate_scalar_bytes - self.aggregate_scalar_bytes
                ),
                error_type=self.error_type,
            )
            self.account_scalar_bytes(
                sum(key_bytes for _key, _child, key_bytes in mapping_entries)
            )
            identity = self.enter_container(value)
            try:
                if self.style == "bridge":
                    self.emit_mapping_entries(
                        mapping_entries,
                        depth=depth,
                        prefix=b'{"$bridge_kind":"mapping","entries":[',
                        suffix=b"]}",
                        tagged_pairs=True,
                    )
                elif self.style == "authority":
                    self.emit_mapping_entries(
                        mapping_entries,
                        depth=depth,
                        prefix=b'{"$ncp_canonical_kind":"mapping","entries":[',
                        suffix=b"]}",
                        tagged_pairs=True,
                    )
                elif self.style == "capture_typed":
                    self.emit_mapping_entries(
                        mapping_entries,
                        depth=depth,
                        prefix=b'["mapping",[',
                        suffix=b"]]",
                        tagged_pairs=True,
                    )
                else:
                    self.emit_mapping_entries(
                        mapping_entries,
                        depth=depth,
                        prefix=b"{",
                        suffix=b"}",
                        tagged_pairs=False,
                    )
            finally:
                self.leave_container(identity)
            return

        if type(value) is FrozenList:
            frozen_items = object.__getattribute__(value, "items")
            self.require(
                type(frozen_items) is tuple,
                "frozen list backing is not an exact tuple",
            )
            identity = self.enter_container(value)
            try:
                if self.style == "bridge":
                    prefix, suffix = b'{"$bridge_kind":"list","items":[', b"]}"
                elif self.style == "authority":
                    prefix, suffix = (
                        b'{"$ncp_canonical_kind":"list","items":[',
                        b"]}",
                    )
                elif self.style == "capture_typed":
                    prefix, suffix = b'["list",[', b"]]"
                else:
                    prefix, suffix = b"[", b"]"
                self.emit_sequence(
                    frozen_items,
                    depth=depth,
                    prefix=prefix,
                    suffix=suffix,
                )
            finally:
                self.leave_container(identity)
            return

        if type(value) is tuple:
            identity = self.enter_container(value)
            try:
                if self.style == "bridge":
                    prefix, suffix = b'{"$bridge_kind":"tuple","items":[', b"]}"
                elif self.style == "authority":
                    prefix, suffix = (
                        b'{"$ncp_canonical_kind":"tuple","items":[',
                        b"]}",
                    )
                elif self.style == "capture_typed":
                    prefix, suffix = b'["tuple",[', b"]]"
                elif self.style in ("capture_plain", "canonical_json"):
                    prefix, suffix = b"[", b"]"
                else:
                    self.fail("canonical tuple is unsupported in this profile")
                    return
                self.emit_sequence(value, depth=depth, prefix=prefix, suffix=suffix)
            finally:
                self.leave_container(identity)
            return

        if type(value) in (dict, list):
            self.fail(
                "mutable dict/list canonical input is forbidden; freeze caller-owned "
                "authoring data first"
            )

        value_type = type(value)
        type_entry = self.type_ids.get(id(value_type))
        type_id = (
            type_entry[1]
            if type_entry is not None and type_entry[0] is value_type
            else None
        )
        if type_id is not None:
            value_type_id = id(value_type)
            needs_class_revalidation = value_type_id not in self.revalidated_type_ids
            artifact_fields = _snapshot_artifact_values(
                value,
                pinned=type_entry[2],
                error_type=self.error_type,
                revalidate_class=needs_class_revalidation,
            )
            if needs_class_revalidation:
                self.revalidated_type_ids.add(value_type_id)
            identity = self.enter_container(value)
            try:
                self.emit_artifact(
                    depth=depth,
                    type_id=type_id,
                    artifact_fields=artifact_fields,
                )
            finally:
                self.leave_container(identity)
            return

        if value is None:
            self.write(b"null")
            return
        if type(value) is bool:
            self.write(b"true" if value else b"false")
            return
        if type(value) is int:
            self.write_integer(value)
            return
        if type(value) is float:
            self.write_float(value)
            return
        if type(value) is bytes:
            self.require(
                (self.limits.allow_empty_payload or bool(value))
                and len(value) <= self.limits.max_payload_bytes,
                "canonical immutable bytes violate their input limit",
            )
            self.account_scalar_bytes(len(value))
            if self.style in ("capture_plain",):
                self.write(b'{"bytes_hex":"')
                self.write_hex(value)
                self.write(b'"}')
            elif self.style == "capture_typed":
                self.write(b'["bytes","')
                self.write_hex(value)
                self.write(b'"]')
            elif self.style == "bridge":
                self.write(b'{"$bridge_kind":"immutable_bytes","hex":"')
                self.write_hex(value)
                self.write(b'"}')
            elif self.style == "authority":
                self.write(b'{"$ncp_canonical_kind":"bytes","hex":"')
                self.write_hex(value)
                self.write(b'"}')
            else:
                self.fail("canonical JSON profile does not admit raw bytes")
            return
        if type(value) is str:
            self.write_string(value, label="canonical string")
            return
        self.fail("canonical value contains an unsupported or subclassed type")

    def finish(self, value: Any) -> bytes:
        try:
            if self.style == "capture_typed":
                self.write(b'["ncp.b01.typed-canonical.v1",')
                self.emit(value, depth=0)
                self.write(b"]")
            else:
                self.emit(value, depth=0)
            self.require(bool(self.output), "canonical JSON output is empty")
            return bytes(self.output)
        except BaseException:
            self.output.clear()
            raise


def canonical_bytes(
    value: Any,
    *,
    style: Style,
    limits: CanonicalLimits,
    type_ids: Mapping[type[Any], str],
    error_type: type[Exception] = ValueError,
) -> bytes:
    """Encode one immutable value without constructing a normalized object tree."""

    _validate_error_type(error_type)
    _validate_limits_exact(limits, error_type=error_type)
    if type(style) is not str or style not in (
        "bridge",
        "authority",
        "canonical_json",
        "capture_plain",
        "capture_typed",
    ):
        raise error_type("unknown canonical profile")
    return _Writer(
        style=style,
        limits=limits,
        type_ids=type_ids,
        error_type=error_type,
    ).finish(value)


def freeze_owned(
    value: Any,
    *,
    limits: CanonicalLimits,
    error_type: type[Exception] = ValueError,
    allow_dataclasses: bool = True,
    allowed_dataclass_types: Mapping[type[Any], str] | None = None,
    reject_shared_mutable: bool = True,
) -> Any:
    """Freeze a private authoring tree; reject shared/cyclic mutable containers.

    The caller must already own the graph exclusively.  The function's purpose
    is representation closure, not synchronization.
    """

    _validate_error_type(error_type)
    _validate_limits_exact(limits, error_type=error_type)
    if allow_dataclasses:
        if allowed_dataclass_types is None:
            raise error_type("owned dataclasses require one exact closed type registry")
        closed_dataclass_types = _snapshot_type_registry(
            allowed_dataclass_types,
            limits=limits,
            error_type=error_type,
        )
    else:
        closed_dataclass_types = {}
    remaining_nodes = limits.max_nodes
    aggregate_scalar_bytes = 0
    active_mutable_ids: set[int] = set()
    frozen_mutable_by_id: dict[int, Any] = {}
    active_immutable_ids: set[int] = set()
    # Never retain a class-shape validation beyond this owned-value traversal.
    revalidated_dataclass_type_ids: set[int] = set()

    def fail(message: str) -> None:
        raise error_type(message)

    def require(condition: bool, message: str) -> None:
        if not condition:
            fail(message)

    def descend(
        item: Any,
        depth: int,
        *,
        freeze_mutable: bool = True,
    ) -> Any:
        nonlocal aggregate_scalar_bytes, remaining_nodes
        require(
            depth <= limits.max_depth,
            "owned canonical value exceeds the root-depth-0 nesting limit",
        )
        remaining_nodes -= 1
        require(
            remaining_nodes >= 0,
            "owned canonical value exceeds the input-node limit",
        )

        if type(item) is dict:
            require(
                freeze_mutable,
                "frozen dataclass transitively contains a mutable mapping",
            )
            identity = id(item)
            require(
                identity not in active_mutable_ids,
                "owned canonical value contains a cyclic mapping",
            )
            prior_frozen = frozen_mutable_by_id.get(identity)
            if prior_frozen is not None:
                require(
                    not reject_shared_mutable,
                    "owned canonical value contains a shared mapping",
                )
                return prior_frozen
            active_mutable_ids.add(identity)
            require(
                len(item) <= limits.max_collection_items,
                "owned canonical mapping exceeds its entry-count limit",
            )
            keys = tuple(item)
            require(
                len(keys) == len(item) and all(type(key) is str for key in keys),
                "owned canonical mapping key type is not exact",
            )
            try:
                for key in keys:
                    key_bytes = _bounded_utf8_length(
                        key,
                        maximum=limits.max_string_bytes,
                        label="owned canonical mapping key",
                        error_type=error_type,
                    )
                    aggregate_scalar_bytes += key_bytes
                    require(
                        aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
                        "owned value exceeds the aggregate scalar-byte limit",
                    )
                entries: list[tuple[str, Any]] = []
                for key in sorted(keys):
                    entries.append(
                        (
                            key,
                            descend(
                                item[key],
                                depth + 1,
                                freeze_mutable=freeze_mutable,
                            ),
                        )
                    )
                frozen = FrozenMap(tuple(entries))
            finally:
                active_mutable_ids.remove(identity)
            frozen_mutable_by_id[identity] = frozen
            return frozen

        if type(item) is list:
            require(
                freeze_mutable,
                "frozen dataclass transitively contains a mutable list",
            )
            identity = id(item)
            require(
                identity not in active_mutable_ids,
                "owned canonical value contains a cyclic list",
            )
            prior_frozen = frozen_mutable_by_id.get(identity)
            if prior_frozen is not None:
                require(
                    not reject_shared_mutable,
                    "owned canonical value contains a shared list",
                )
                return prior_frozen
            active_mutable_ids.add(identity)
            require(
                len(item) <= limits.max_collection_items,
                "owned canonical list exceeds its item-count limit",
            )
            try:
                frozen = FrozenList(
                    tuple(
                        descend(
                            child,
                            depth + 1,
                            freeze_mutable=freeze_mutable,
                        )
                        for child in item
                    )
                )
            finally:
                active_mutable_ids.remove(identity)
            frozen_mutable_by_id[identity] = frozen
            return frozen

        if type(item) is FrozenMap:
            validated_entries = _bounded_frozen_map_entries(
                item,
                maximum_entries=limits.max_collection_items,
                maximum_key_bytes=limits.max_string_bytes,
                maximum_aggregate_key_bytes=(
                    limits.max_aggregate_scalar_bytes - aggregate_scalar_bytes
                ),
                error_type=error_type,
            )
            identity = id(item)
            require(
                identity not in active_immutable_ids,
                "owned canonical value contains a frozen-mapping cycle",
            )
            active_immutable_ids.add(identity)
            try:
                entries: list[tuple[str, Any]] = []
                for key, child, key_bytes in validated_entries:
                    aggregate_scalar_bytes += key_bytes
                    require(
                        aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
                        "owned value exceeds the aggregate scalar-byte limit",
                    )
                    entries.append(
                        (
                            key,
                            descend(
                                child,
                                depth + 1,
                                freeze_mutable=freeze_mutable,
                            ),
                        )
                    )
                return FrozenMap(tuple(entries))
            finally:
                active_immutable_ids.remove(identity)
        if type(item) is FrozenList:
            frozen_items = object.__getattribute__(item, "items")
            require(
                type(frozen_items) is tuple
                and len(frozen_items) <= limits.max_collection_items,
                "owned frozen list backing is not exact or bounded",
            )
            identity = id(item)
            require(
                identity not in active_immutable_ids,
                "owned canonical value contains a frozen-list cycle",
            )
            active_immutable_ids.add(identity)
            try:
                return FrozenList(
                    tuple(
                        descend(
                            child,
                            depth + 1,
                            freeze_mutable=freeze_mutable,
                        )
                        for child in frozen_items
                    )
                )
            finally:
                active_immutable_ids.remove(identity)
        if type(item) is tuple:
            identity = id(item)
            require(
                identity not in active_immutable_ids,
                "owned canonical value contains a reference cycle",
            )
            active_immutable_ids.add(identity)
            try:
                require(
                    len(item) <= limits.max_collection_items,
                    "owned canonical tuple exceeds its item-count limit",
                )
                return tuple(
                    descend(
                        child,
                        depth + 1,
                        freeze_mutable=freeze_mutable,
                    )
                    for child in item
                )
            finally:
                active_immutable_ids.remove(identity)
        item_type = type(item)
        dataclass_entry = closed_dataclass_types.get(id(item_type))
        if dataclass_entry is not None and dataclass_entry[0] is item_type:
            require(allow_dataclasses, "owned canonical dataclass is forbidden")
            item_type_id = id(item_type)
            needs_class_revalidation = (
                item_type_id not in revalidated_dataclass_type_ids
            )
            artifact_fields = _snapshot_artifact_values(
                item,
                pinned=dataclass_entry[2],
                error_type=error_type,
                revalidate_class=needs_class_revalidation,
            )
            if needs_class_revalidation:
                revalidated_dataclass_type_ids.add(item_type_id)
            require(
                len(artifact_fields) <= limits.max_artifact_fields,
                "owned canonical dataclass exceeds its field-count limit",
            )
            identity = id(item)
            require(
                identity not in active_immutable_ids,
                "owned canonical value contains a dataclass cycle",
            )
            active_immutable_ids.add(identity)
            try:
                for _field_shape, field_value in artifact_fields:
                    descend(
                        field_value,
                        depth + 1,
                        freeze_mutable=False,
                    )
            finally:
                active_immutable_ids.remove(identity)
            return item
        if item is None or type(item) is bool:
            return item
        if type(item) is int:
            require(
                limits.min_integer <= item <= limits.max_integer,
                "owned canonical integer is outside the portable safe range",
            )
            return item
        if type(item) is float:
            require(
                limits.allow_float and math.isfinite(item),
                "owned canonical float is unsupported or nonfinite",
            )
            return item
        if type(item) is str:
            encoded_length = _bounded_utf8_length(
                item,
                maximum=limits.max_string_bytes,
                label="owned canonical string",
                error_type=error_type,
            )
            aggregate_scalar_bytes += encoded_length
            require(
                aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
                "owned value exceeds the aggregate scalar-byte limit",
            )
            return item
        if type(item) is bytes:
            require(
                (limits.allow_empty_payload or bool(item))
                and len(item) <= limits.max_payload_bytes,
                "owned immutable bytes violate their input limit",
            )
            aggregate_scalar_bytes += len(item)
            require(
                aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
                "owned value exceeds the aggregate scalar-byte limit",
            )
            return item
        fail("owned canonical value contains an unsupported or subclassed type")

    return descend(value, 0)


def validate_immutable(
    value: Any,
    *,
    limits: CanonicalLimits,
    type_ids: Mapping[type[Any], str],
    error_type: type[Exception] = ValueError,
) -> None:
    """Validate a transitive immutable graph before hashing or copying it."""

    _validate_error_type(error_type)
    _validate_limits_exact(limits, error_type=error_type)
    closed_type_ids = _snapshot_type_registry(
        type_ids,
        limits=limits,
        error_type=error_type,
    )
    stack: list[tuple[Any, int, bool]] = [(value, 0, False)]
    active_ids: set[int] = set()
    # Never retain a class-shape validation beyond this immutable-value traversal.
    revalidated_type_ids: set[int] = set()
    remaining_nodes = limits.max_nodes
    aggregate_scalar_bytes = 0

    def fail(message: str) -> None:
        raise error_type(message)

    def require(condition: bool, message: str) -> None:
        if not condition:
            fail(message)

    while stack:
        item, depth, leaving = stack.pop()
        identity = id(item)
        if leaving:
            active_ids.remove(identity)
            continue
        require(
            depth <= limits.max_depth,
            "immutable value exceeds the root-depth-0 nesting limit",
        )
        remaining_nodes -= 1
        require(
            remaining_nodes >= 0,
            "immutable value exceeds the input-node limit",
        )

        children: tuple[Any, ...] | None = None
        if type(item) is tuple:
            require(
                len(item) <= limits.max_collection_items,
                "immutable tuple exceeds its item-count limit",
            )
            children = item
        elif type(item) is FrozenList:
            frozen_items = object.__getattribute__(item, "items")
            require(
                type(frozen_items) is tuple
                and len(frozen_items) <= limits.max_collection_items,
                "immutable frozen list exceeds its item-count limit",
            )
            children = frozen_items
        elif type(item) is FrozenMap:
            validated_entries = _bounded_frozen_map_entries(
                item,
                maximum_entries=limits.max_collection_items,
                maximum_key_bytes=limits.max_string_bytes,
                maximum_aggregate_key_bytes=(
                    limits.max_aggregate_scalar_bytes - aggregate_scalar_bytes
                ),
                error_type=error_type,
            )
            for _key, _child, key_bytes in validated_entries:
                aggregate_scalar_bytes += key_bytes
                require(
                    aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
                    "immutable value exceeds the aggregate scalar-byte limit",
                )
            children = tuple(child for _key, child, _bytes in validated_entries)
        elif (
            item_type_entry := closed_type_ids.get(id(type(item)))
        ) is not None and item_type_entry[0] is type(item):
            item_type_id = id(type(item))
            needs_class_revalidation = item_type_id not in revalidated_type_ids
            artifact_fields = _snapshot_artifact_values(
                item,
                pinned=item_type_entry[2],
                error_type=error_type,
                revalidate_class=needs_class_revalidation,
            )
            if needs_class_revalidation:
                revalidated_type_ids.add(item_type_id)
            require(
                len(artifact_fields) <= limits.max_artifact_fields,
                "immutable artifact exceeds its field-count limit",
            )
            children = tuple(field_value for _field, field_value in artifact_fields)
        elif type(item) in (dict, list):
            fail("mutable staged value: exact dict/list")
        elif item is None or type(item) is bool:
            continue
        elif type(item) is int:
            require(
                limits.min_integer <= item <= limits.max_integer,
                "immutable integer is outside the portable safe range",
            )
            continue
        elif type(item) is float:
            require(
                limits.allow_float and math.isfinite(item),
                "immutable float is unsupported or nonfinite",
            )
            continue
        elif type(item) is str:
            encoded_length = _bounded_utf8_length(
                item,
                maximum=limits.max_string_bytes,
                label="immutable string",
                error_type=error_type,
            )
            aggregate_scalar_bytes += encoded_length
            require(
                aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
                "immutable value exceeds the aggregate scalar-byte limit",
            )
            continue
        elif type(item) is bytes:
            require(
                (limits.allow_empty_payload or bool(item))
                and len(item) <= limits.max_payload_bytes,
                "immutable bytes violate their input limit",
            )
            aggregate_scalar_bytes += len(item)
            require(
                aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
                "immutable value exceeds the aggregate scalar-byte limit",
            )
            continue
        else:
            fail("immutable value contains a mutable or unsupported type")

        require(
            aggregate_scalar_bytes <= limits.max_aggregate_scalar_bytes,
            "immutable value exceeds the aggregate scalar-byte limit",
        )
        require(
            identity not in active_ids,
            "immutable value contains a reference cycle",
        )
        active_ids.add(identity)
        stack.append((item, depth, True))
        if children:
            for child in reversed(children):
                stack.append((child, depth + 1, False))


def run_self_test() -> None:
    """Exercise the canonical class-shape and bounded-encoding closure."""

    limits = CanonicalLimits(
        max_output_bytes=4_096,
        max_depth=4,
        max_nodes=128,
        max_collection_items=8,
        max_artifact_fields=8,
        max_string_bytes=64,
        max_payload_bytes=64,
        max_aggregate_scalar_bytes=1_024,
        min_integer=-1_000,
        max_integer=1_000,
        allow_empty_payload=True,
    )

    def require(condition: bool, label: str) -> None:
        if not condition:
            raise RuntimeError(f"bounded canonical self-test failed: {label}")

    def expect_failure(label: str, action: Any) -> None:
        try:
            action()
        except (TypeError, ValueError):
            return
        raise RuntimeError(f"bounded canonical self-test did not reject: {label}")

    def measure_revalidations(action: Any, observed: list[int]) -> Any:
        """Count one self-test action without persistent production state."""

        global _revalidate_class_shape
        require(not observed, "revalidation measurement output was not empty")
        original = _revalidate_class_shape
        calls = 0

        def counted(
            pinned: _PinnedClassShape,
            *,
            error_type: type[Exception],
        ) -> None:
            nonlocal calls
            calls += 1
            original(pinned, error_type=error_type)

        _revalidate_class_shape = counted
        try:
            return action()
        finally:
            _revalidate_class_shape = original
            observed.append(calls)

    @dataclass(frozen=True, slots=True)
    class ValidSlotArtifact:
        alpha: int
        omega: str

    @dataclass(frozen=True)
    class ValidDictArtifact:
        alpha: int
        omega: tuple[Any, ...] = ()

    def make_legacy_slots_test_pair(
        name: str,
    ) -> tuple[type[Any], type[Any]]:
        """Build the exact copy shape emitted by older CPython dataclasses."""

        source = make_dataclass(
            name,
            (("alpha", int), ("omega", str)),
            frozen=True,
        )
        params_witness = make_dataclass(
            f"{name}ParamsWitness",
            (),
            frozen=True,
            slots=True,
        )
        type.__setattr__(
            source,
            "__dataclass_params__",
            params_witness.__dict__["__dataclass_params__"],
        )
        source_namespace = type.__getattribute__(source, "__dict__")
        replacement_namespace = dict(source_namespace)
        field_names = tuple(replacement_namespace["__dataclass_fields__"])
        replacement_namespace["__slots__"] = field_names
        for field_name in field_names:
            replacement_namespace.pop(field_name, None)
        replacement_namespace.pop("__dict__", None)
        replacement_namespace.pop("__weakref__", None)
        replacement = type(source)(
            type.__getattribute__(source, "__name__"),
            type.__getattribute__(source, "__bases__"),
            replacement_namespace,
        )
        installed_namespace = type.__getattribute__(replacement, "__dict__")
        for state_name, state_method in _TRUSTED_SLOTTED_FROZEN_STATE_METHODS:
            if state_name not in installed_namespace:
                type.__setattr__(replacement, state_name, state_method)
        return source, replacement

    legacy_source, legacy_slot_artifact = make_legacy_slots_test_pair(
        "LegacySlotArtifact"
    )
    legacy_registry = FrozenTypeRegistry(
        ((legacy_slot_artifact, "selftest.LegacySlotArtifact@1"),)
    )
    require(
        legacy_registry.snapshot_artifact_view(legacy_slot_artifact(11, "legacy"))
        == (
            "selftest.LegacySlotArtifact@1",
            (("alpha", 11), ("omega", "legacy")),
        ),
        "exact legacy frozen-slots replacement was not portable",
    )
    type.__setattr__(
        legacy_source,
        "__qualname__",
        f"{type.__getattribute__(legacy_source, '__qualname__')}.mutated",
    )
    expect_failure(
        "post-registration legacy source mutation",
        lambda: legacy_registry.snapshot_artifact_view(
            legacy_slot_artifact(11, "legacy")
        ),
    )

    mismatched_fields_source, mismatched_fields_artifact = make_legacy_slots_test_pair(
        "LegacyMismatchedFields"
    )
    type.__setattr__(mismatched_fields_source, "__dataclass_fields__", {})
    expect_failure(
        "legacy frozen-slots source with another field table",
        lambda: FrozenTypeRegistry(
            ((mismatched_fields_artifact, "selftest.LegacyMismatchedFields@1"),)
        ),
    )

    unexpected_slots_source, unexpected_slots_artifact = make_legacy_slots_test_pair(
        "LegacyUnexpectedSlots"
    )
    type.__setattr__(unexpected_slots_source, "__slots__", ())
    expect_failure(
        "legacy frozen-slots source with an unexpected slots marker",
        lambda: FrozenTypeRegistry(
            ((unexpected_slots_artifact, "selftest.LegacyUnexpectedSlots@1"),)
        ),
    )

    _mismatched_namespace_source, mismatched_namespace_artifact = (
        make_legacy_slots_test_pair("LegacyMismatchedNamespace")
    )
    type.__setattr__(mismatched_namespace_artifact, "__doc__", "changed")
    expect_failure(
        "legacy frozen-slots replacement with a divergent namespace",
        lambda: FrozenTypeRegistry(
            (
                (
                    mismatched_namespace_artifact,
                    "selftest.LegacyMismatchedNamespace@1",
                ),
            )
        ),
    )

    oversized_namespace_source, oversized_namespace_artifact = (
        make_legacy_slots_test_pair("LegacyOversizedNamespace")
    )
    for binding_index in range(MAX_FROZEN_ARTIFACT_CLASS_BINDINGS + 1):
        type.__setattr__(
            oversized_namespace_source,
            f"oversized_binding_{binding_index}",
            None,
        )
    expect_failure(
        "legacy frozen-slots source exceeds its namespace-entry limit",
        lambda: FrozenTypeRegistry(
            (
                (
                    oversized_namespace_artifact,
                    "selftest.LegacyOversizedNamespace@1",
                ),
            )
        ),
    )

    oversized_fields_source, oversized_fields_artifact = make_legacy_slots_test_pair(
        "LegacyOversizedFields"
    )
    oversized_field_table = oversized_fields_source.__dict__["__dataclass_fields__"]
    for field_index in range(MAX_FROZEN_ARTIFACT_FIELDS + 1):
        oversized_field_table[f"oversized_field_{field_index}"] = None
    require(
        not _is_exact_legacy_slots_replacement(
            oversized_fields_artifact,
            oversized_fields_artifact.__dict__,
            oversized_fields_source,
        ),
        "legacy frozen-slots helper accepted an oversized field table",
    )

    field_mutation_source, field_mutation_artifact = make_legacy_slots_test_pair(
        "LegacyFieldMutation"
    )
    field_mutation_registry = FrozenTypeRegistry(
        ((field_mutation_artifact, "selftest.LegacyFieldMutation@1"),)
    )
    field_mutation_source.__dict__["__dataclass_fields__"].pop("omega")
    expect_failure(
        "post-registration legacy shared field-table mutation",
        lambda: field_mutation_registry.snapshot_artifact_view(
            field_mutation_artifact(13, "field")
        ),
    )

    params_mutation_source, params_mutation_artifact = make_legacy_slots_test_pair(
        "LegacyParamsMutation"
    )
    params_mutation_registry = FrozenTypeRegistry(
        ((params_mutation_artifact, "selftest.LegacyParamsMutation@1"),)
    )
    object.__setattr__(
        params_mutation_source.__dict__["__dataclass_params__"],
        "frozen",
        False,
    )
    expect_failure(
        "post-registration legacy shared parameter mutation",
        lambda: params_mutation_registry.snapshot_artifact_view(
            params_mutation_artifact(17, "params")
        ),
    )

    registry = FrozenTypeRegistry(
        (
            (ValidSlotArtifact, "selftest.ValidSlotArtifact@1"),
            (ValidDictArtifact, "selftest.ValidDictArtifact@1"),
        )
    )
    slot_value = ValidSlotArtifact(7, "é")
    dict_value = ValidDictArtifact(9)
    observed_revalidations: list[int] = []
    null_bytes = measure_revalidations(
        lambda: canonical_bytes(
            None,
            style="capture_plain",
            limits=limits,
            type_ids=registry,
        ),
        observed_revalidations,
    )
    require(null_bytes == b"null", "unreached registry changed scalar output")
    require(
        observed_revalidations == [0],
        "writer revalidated an unreached registered class",
    )
    observed_revalidations = []
    shape_view = measure_revalidations(
        lambda: registry.revalidated_shape_view(),
        observed_revalidations,
    )
    require(
        shape_view
        == (
            ("selftest.ValidSlotArtifact@1", ("alpha", "omega")),
            ("selftest.ValidDictArtifact@1", ("alpha", "omega")),
        ),
        "revalidated public registry shape view",
    )
    require(
        observed_revalidations == [2],
        "full registry shape view did not revalidate every class",
    )
    observed_revalidations = []
    artifact_view = measure_revalidations(
        lambda: registry.snapshot_artifact_view(slot_value),
        observed_revalidations,
    )
    require(
        artifact_view
        == (
            "selftest.ValidSlotArtifact@1",
            (("alpha", 7), ("omega", "é")),
        ),
        "exact selected artifact snapshot view",
    )
    require(
        observed_revalidations == [1],
        "selected artifact snapshot did not revalidate exactly one class",
    )
    observed_revalidations = []
    measure_revalidations(
        lambda: registry.snapshot_artifact_view(slot_value),
        observed_revalidations,
    )
    require(
        observed_revalidations == [1],
        "selected artifact snapshot retained a cross-call shape result",
    )

    class ValidSlotSubclass(ValidSlotArtifact):
        pass

    expect_failure(
        "subclassed artifact snapshot view",
        lambda: registry.snapshot_artifact_view(ValidSlotSubclass(7, "é")),
    )
    expect_failure(
        "unregistered artifact snapshot view",
        lambda: registry.snapshot_artifact_view(None),
    )

    @dataclass(frozen=True)
    class SelectedSnapshotArtifact:
        value: int

    @dataclass(frozen=True)
    class UnrelatedSnapshotArtifact:
        value: int

    selective_registry = FrozenTypeRegistry(
        (
            (SelectedSnapshotArtifact, "selftest.SelectedSnapshotArtifact@1"),
            (UnrelatedSnapshotArtifact, "selftest.UnrelatedSnapshotArtifact@1"),
        )
    )
    UnrelatedSnapshotArtifact.value = 0
    require(
        selective_registry.snapshot_artifact_view(SelectedSnapshotArtifact(3))
        == (
            "selftest.SelectedSnapshotArtifact@1",
            (("value", 3),),
        ),
        "selected snapshot was blocked by unrelated class mutation",
    )
    expect_failure(
        "selected mutated artifact class",
        lambda: selective_registry.snapshot_artifact_view(UnrelatedSnapshotArtifact(4)),
    )
    selected_value = SelectedSnapshotArtifact(3)
    require(
        canonical_bytes(
            selected_value,
            style="capture_plain",
            limits=limits,
            type_ids=selective_registry,
        )
        == b'{"value":3}',
        "unused mutated class blocked canonical encoding",
    )
    require(
        freeze_owned(
            selected_value,
            limits=limits,
            allowed_dataclass_types=selective_registry,
        )
        is selected_value,
        "unused mutated class blocked owned-value validation",
    )
    validate_immutable(
        selected_value,
        limits=limits,
        type_ids=selective_registry,
    )
    expect_failure(
        "reached mutated class canonical encoding",
        lambda: canonical_bytes(
            UnrelatedSnapshotArtifact(4),
            style="capture_plain",
            limits=limits,
            type_ids=selective_registry,
        ),
    )
    expect_failure(
        "reached mutated class owned-value validation",
        lambda: freeze_owned(
            UnrelatedSnapshotArtifact(4),
            limits=limits,
            allowed_dataclass_types=selective_registry,
        ),
    )
    expect_failure(
        "reached mutated class immutable validation",
        lambda: validate_immutable(
            UnrelatedSnapshotArtifact(4),
            limits=limits,
            type_ids=selective_registry,
        ),
    )
    witness_generations_after_registration = (
        _TRANSIENT_FROZEN_MUTATOR_WITNESS_GENERATIONS
    )
    registry.revalidated_shape_view()
    registry.revalidated_shape_view()
    registry.snapshot_artifact_view(slot_value)
    registry.snapshot_artifact_view(dict_value)
    require(
        _TRANSIENT_FROZEN_MUTATOR_WITNESS_GENERATIONS
        == witness_generations_after_registration,
        "revalidation generated a new frozen mutator witness",
    )
    require(
        canonical_bytes(
            slot_value,
            style="bridge",
            limits=limits,
            type_ids=registry,
        )
        == (
            '{"$bridge_kind":"artifact","fields":[["alpha",7],'
            '["omega","é"]],"type_ref":"selftest.ValidSlotArtifact@1"}'
        ).encode(),
        "valid slot artifact bytes",
    )
    require(
        canonical_bytes(
            dict_value,
            style="authority",
            limits=limits,
            type_ids=registry,
        )
        == (
            b'{"$ncp_canonical_kind":"artifact","artifact_type":'
            b'"selftest.ValidDictArtifact@1","fields":{"alpha":9,'
            b'"omega":{"$ncp_canonical_kind":"tuple","items":[]}}}'
        ),
        "valid native-dict artifact bytes",
    )
    validate_immutable(
        (slot_value, dict_value),
        limits=limits,
        type_ids=registry,
    )

    same_class_values = (ValidDictArtifact(1), ValidDictArtifact(2))
    observed_revalidations = []
    same_class_bytes = measure_revalidations(
        lambda: canonical_bytes(
            same_class_values,
            style="capture_plain",
            limits=limits,
            type_ids=registry,
        ),
        observed_revalidations,
    )
    require(
        same_class_bytes == b'[{"alpha":1,"omega":[]},{"alpha":2,"omega":[]}]',
        "two same-class artifacts changed canonical output",
    )
    require(
        observed_revalidations == [1],
        "writer did not revalidate one reached class exactly once",
    )
    observed_revalidations = []
    repeated_same_class_bytes = measure_revalidations(
        lambda: canonical_bytes(
            same_class_values,
            style="capture_plain",
            limits=limits,
            type_ids=registry,
        ),
        observed_revalidations,
    )
    require(
        repeated_same_class_bytes == same_class_bytes,
        "repeated same-class artifact encoding changed output",
    )
    require(
        observed_revalidations == [1],
        "writer retained a class-shape result across calls",
    )

    observed_revalidations = []
    frozen_same_class_values = measure_revalidations(
        lambda: freeze_owned(
            same_class_values,
            limits=limits,
            allowed_dataclass_types=registry,
        ),
        observed_revalidations,
    )
    require(
        type(frozen_same_class_values) is tuple
        and len(frozen_same_class_values) == 2
        and frozen_same_class_values[0] is same_class_values[0]
        and frozen_same_class_values[1] is same_class_values[1],
        "owned traversal did not preserve validated immutable artifacts",
    )
    require(
        observed_revalidations == [1],
        "owned traversal did not revalidate one reached class exactly once",
    )

    observed_revalidations = []
    measure_revalidations(
        lambda: validate_immutable(
            same_class_values,
            limits=limits,
            type_ids=registry,
        ),
        observed_revalidations,
    )
    require(
        observed_revalidations == [1],
        "immutable traversal did not revalidate one reached class exactly once",
    )

    malformed_second_value = ValidDictArtifact(2)
    object.__setattr__(malformed_second_value, "uncommitted", 3)
    malformed_pair = (ValidDictArtifact(1), malformed_second_value)
    observed_revalidations = []
    expect_failure(
        "writer skipped a later same-class instance snapshot",
        lambda: measure_revalidations(
            lambda: canonical_bytes(
                malformed_pair,
                style="capture_plain",
                limits=limits,
                type_ids=registry,
            ),
            observed_revalidations,
        ),
    )
    require(
        observed_revalidations == [1],
        "writer revalidated a class more than once before instance rejection",
    )
    observed_revalidations = []
    expect_failure(
        "owned traversal skipped a later same-class instance snapshot",
        lambda: measure_revalidations(
            lambda: freeze_owned(
                malformed_pair,
                limits=limits,
                allowed_dataclass_types=registry,
            ),
            observed_revalidations,
        ),
    )
    require(
        observed_revalidations == [1],
        "owned traversal revalidated a class more than once before rejection",
    )
    observed_revalidations = []
    expect_failure(
        "immutable traversal skipped a later same-class instance snapshot",
        lambda: measure_revalidations(
            lambda: validate_immutable(
                malformed_pair,
                limits=limits,
                type_ids=registry,
            ),
            observed_revalidations,
        ),
    )
    require(
        observed_revalidations == [1],
        "immutable traversal revalidated a class more than once before rejection",
    )

    @dataclass(frozen=True)
    class StatefulAccessorArtifact:
        value: int

        def __getattribute__(self, name: str) -> Any:
            current = object.__getattribute__(self, name)
            if name == "value":
                object.__setattr__(self, "value", current + 1)
            return current

    expect_failure(
        "stateful attribute accessor",
        lambda: FrozenTypeRegistry(
            ((StatefulAccessorArtifact, "selftest.StatefulAccessorArtifact@1"),)
        ),
    )

    class HostileDescriptor:
        def __get__(self, _instance: Any, _owner: Any) -> int:
            raise RuntimeError("descriptor executed")

    @dataclass(frozen=True)
    class DescriptorArtifact:
        value: int

    DescriptorArtifact.value = HostileDescriptor()
    expect_failure(
        "non-native field descriptor",
        lambda: FrozenTypeRegistry(
            ((DescriptorArtifact, "selftest.DescriptorArtifact@1"),)
        ),
    )

    class HostileMeta(type):
        pass

    @dataclass(frozen=True)
    class MetaArtifact(metaclass=HostileMeta):
        value: int

    expect_failure(
        "metaclass subclass",
        lambda: FrozenTypeRegistry(((MetaArtifact, "selftest.MetaArtifact@1"),)),
    )

    mutator_calls: list[str] = []

    @dataclass
    class MutableForgedDonor:
        alpha: int

        def __setattr__(self, name: str, value: Any) -> None:
            mutator_calls.append("setattr")
            object.__setattr__(self, name, value)

        def __delattr__(self, name: str) -> None:
            mutator_calls.append("delattr")
            object.__delattr__(self, name)

    MutableForgedDonor.__dataclass_params__ = ValidDictArtifact.__dataclass_params__
    MutableForgedDonor.__dataclass_fields__ = ValidDictArtifact.__dataclass_fields__
    expect_failure(
        "plain mutable dataclass with copied frozen metadata",
        lambda: FrozenTypeRegistry(
            ((MutableForgedDonor, "selftest.MutableForgedDonor@1"),)
        ),
    )
    require(not mutator_calls, "forged mutable donor code executed")

    @dataclass
    class CopiedFrozenMutatorDonor:
        alpha: int
        omega: tuple[Any, ...] = ()

    CopiedFrozenMutatorDonor.__dataclass_params__ = (
        ValidDictArtifact.__dataclass_params__
    )
    CopiedFrozenMutatorDonor.__dataclass_fields__ = (
        ValidDictArtifact.__dataclass_fields__
    )
    CopiedFrozenMutatorDonor.__setattr__ = ValidDictArtifact.__setattr__
    CopiedFrozenMutatorDonor.__delattr__ = ValidDictArtifact.__delattr__
    expect_failure(
        "copied frozen mutator closure bound to donor class",
        lambda: FrozenTypeRegistry(
            ((CopiedFrozenMutatorDonor, "selftest.CopiedFrozenMutatorDonor@1"),)
        ),
    )

    hostile_constant_comparisons: list[str] = []

    class HostileCodeConstant:
        def __eq__(self, _other: Any) -> bool:
            hostile_constant_comparisons.append("eq")
            return True

    @dataclass(frozen=True)
    class HostileCodeConstantArtifact:
        value: int

    original_setattr = HostileCodeConstantArtifact.__setattr__
    original_code = original_setattr.__code__
    hostile_code = original_code.replace(
        co_consts=(HostileCodeConstant(),) + original_code.co_consts[1:]
    )
    HostileCodeConstantArtifact.__setattr__ = FunctionType(
        hostile_code,
        original_setattr.__globals__,
        name="__setattr__",
        closure=original_setattr.__closure__,
    )
    expect_failure(
        "hostile exact-code constant",
        lambda: FrozenTypeRegistry(
            ((HostileCodeConstantArtifact, "selftest.HostileCodeConstant@1"),)
        ),
    )
    require(
        not hostile_constant_comparisons,
        "hostile code constant equality executed",
    )

    @dataclass(frozen=True)
    class OversizedScalarDefault:
        value: int = 1 << (MAX_INERT_DEFAULT_INTEGER_BITS + 1)

    expect_failure(
        "oversized inert scalar default",
        lambda: FrozenTypeRegistry(
            ((OversizedScalarDefault, "selftest.OversizedScalarDefault@1"),)
        ),
    )

    @dataclass(frozen=True)
    class AggregateScalarDefault:
        value: tuple[bytes, bytes] = (
            b"x" * (MAX_INERT_DEFAULT_AGGREGATE_SCALAR_BYTES // 2 + 1),
            b"y" * (MAX_INERT_DEFAULT_AGGREGATE_SCALAR_BYTES // 2 + 1),
        )

    expect_failure(
        "aggregate inert scalar bytes",
        lambda: FrozenTypeRegistry(
            ((AggregateScalarDefault, "selftest.AggregateScalarDefault@1"),)
        ),
    )

    @dataclass(frozen=True)
    class OversizedFieldName:
        value: int

    oversized_field = OversizedFieldName.__dataclass_fields__.pop("value")
    oversized_field_name = "f" * (MAX_FROZEN_FIELD_NAME_BYTES + 1)
    oversized_field.name = oversized_field_name
    OversizedFieldName.__dataclass_fields__[oversized_field_name] = oversized_field
    expect_failure(
        "oversized field name before witness generation",
        lambda: FrozenTypeRegistry(
            ((OversizedFieldName, "selftest.OversizedFieldName@1"),)
        ),
    )

    @dataclass(frozen=True)
    class PostRegistryClassMutation:
        value: int

    mutated_class_registry = FrozenTypeRegistry(
        ((PostRegistryClassMutation, "selftest.PostRegistryClassMutation@1"),)
    )
    mutation_value = PostRegistryClassMutation(1)
    require(
        canonical_bytes(
            mutation_value,
            style="capture_plain",
            limits=limits,
            type_ids=mutated_class_registry,
        )
        == b'{"value":1}',
        "pre-mutation canonical class baseline",
    )
    require(
        freeze_owned(
            mutation_value,
            limits=limits,
            allowed_dataclass_types=mutated_class_registry,
        )
        is mutation_value,
        "pre-mutation owned class baseline",
    )
    validate_immutable(
        mutation_value,
        limits=limits,
        type_ids=mutated_class_registry,
    )
    PostRegistryClassMutation.value = 0
    expect_failure(
        "post-success class mutation in a later writer call",
        lambda: canonical_bytes(
            mutation_value,
            style="bridge",
            limits=limits,
            type_ids=mutated_class_registry,
        ),
    )
    expect_failure(
        "post-success class mutation in a later owned traversal",
        lambda: freeze_owned(
            mutation_value,
            limits=limits,
            allowed_dataclass_types=mutated_class_registry,
        ),
    )
    expect_failure(
        "post-success class mutation in a later immutable traversal",
        lambda: validate_immutable(
            mutation_value,
            limits=limits,
            type_ids=mutated_class_registry,
        ),
    )

    @dataclass(frozen=True)
    class PostRegistryFieldMutation:
        value: int

    mutated_field_registry = FrozenTypeRegistry(
        ((PostRegistryFieldMutation, "selftest.PostRegistryFieldMutation@1"),)
    )
    PostRegistryFieldMutation.__dataclass_fields__["value"].name = "changed"
    expect_failure(
        "post-registry dataclasses.Field mutation",
        lambda: canonical_bytes(
            PostRegistryFieldMutation(1),
            style="bridge",
            limits=limits,
            type_ids=mutated_field_registry,
        ),
    )

    @dataclass(frozen=True)
    class CustomFieldMetadata:
        value: int = dataclass_field(metadata={"purpose": "not-canonical"})

    expect_failure(
        "custom field metadata",
        lambda: FrozenTypeRegistry(
            ((CustomFieldMetadata, "selftest.CustomFieldMetadata@1"),)
        ),
    )

    metadata_calls: list[str] = []

    class HostileMetadata(Mapping[Any, Any]):
        def __len__(self) -> int:
            metadata_calls.append("len")
            return 0

        def __iter__(self):
            metadata_calls.append("iter")
            return iter(())

        def __getitem__(self, key: Any) -> Any:
            metadata_calls.append("getitem")
            raise KeyError(key)

    @dataclass(frozen=True)
    class HostileFieldMetadata:
        value: int = dataclass_field(metadata=HostileMetadata())

    expect_failure(
        "hostile field metadata wrapper",
        lambda: FrozenTypeRegistry(
            ((HostileFieldMetadata, "selftest.HostileFieldMetadata@1"),)
        ),
    )
    require(not metadata_calls, "hostile field metadata code executed")

    forged_registry = object.__new__(FrozenTypeRegistry)
    object.__setattr__(
        forged_registry,
        "entries",
        ((ValidSlotArtifact, "selftest.Forged@1"),),
    )
    expect_failure(
        "forged registry without pinned shapes",
        lambda: canonical_bytes(
            slot_value,
            style="bridge",
            limits=limits,
            type_ids=forged_registry,
        ),
    )
    expect_failure(
        "forged registry artifact snapshot view",
        lambda: forged_registry.snapshot_artifact_view(slot_value),
    )

    mutated_backing_registry = FrozenTypeRegistry(
        ((ValidSlotArtifact, "selftest.BackingMutation@1"),)
    )
    object.__setattr__(
        mutated_backing_registry,
        "entries",
        ((ValidSlotArtifact, "selftest.BackingMutation@2"),),
    )
    expect_failure(
        "post-registration stable-ID backing mutation",
        lambda: canonical_bytes(
            None,
            style="capture_plain",
            limits=limits,
            type_ids=mutated_backing_registry,
        ),
    )
    expect_failure(
        "post-registration stable-ID snapshot mutation",
        lambda: mutated_backing_registry.snapshot_artifact_view(slot_value),
    )

    mutated_shape_backing_registry = FrozenTypeRegistry(
        ((ValidSlotArtifact, "selftest.ShapeBackingMutation@1"),)
    )
    object.__setattr__(
        mutated_shape_backing_registry,
        "_shapes",
        (("selftest.ShapeBackingMutation@1", object()),),
    )
    expect_failure(
        "post-registration pinned-shape backing mutation",
        lambda: canonical_bytes(
            None,
            style="capture_plain",
            limits=limits,
            type_ids=mutated_shape_backing_registry,
        ),
    )

    class StringAlias(str):
        pass

    expect_failure(
        "stable type ID subclass",
        lambda: FrozenTypeRegistry(
            ((ValidSlotArtifact, StringAlias("selftest.Alias@1")),)
        ),
    )
    expect_failure(
        "oversized stable type ID before hashing",
        lambda: FrozenTypeRegistry(
            ((ValidSlotArtifact, "i" * (MAX_FROZEN_TYPE_ID_BYTES + 1)),)
        ),
    )
    expect_failure(
        "style selector subclass",
        lambda: canonical_bytes(
            slot_value,
            style=StringAlias("bridge"),
            limits=limits,
            type_ids=registry,
        ),
    )

    extra_key_value = ValidDictArtifact(1)
    object.__setattr__(extra_key_value, "uncommitted", 2)
    expect_failure(
        "native instance dict extra key",
        lambda: canonical_bytes(
            extra_key_value,
            style="bridge",
            limits=limits,
            type_ids=registry,
        ),
    )
    missing_key_value = ValidDictArtifact(1)
    del missing_key_value.__dict__["omega"]
    expect_failure(
        "native instance dict missing key",
        lambda: canonical_bytes(
            missing_key_value,
            style="bridge",
            limits=limits,
            type_ids=registry,
        ),
    )

    unicode_map = FrozenMap((("a", "é"), ("z", 1)))
    require(
        canonical_bytes(
            unicode_map,
            style="capture_plain",
            limits=limits,
            type_ids=FrozenTypeRegistry(()),
        )
        == '{"a":"é","z":1}'.encode(),
        "exact map order and Unicode scalar encoding",
    )
    expect_failure(
        "unordered exact map",
        lambda: FrozenMap((("z", 1), ("a", 2))),
    )
    expect_failure(
        "non-scalar Unicode map key",
        lambda: canonical_bytes(
            FrozenMap((("\ud800", 1),)),
            style="capture_plain",
            limits=limits,
            type_ids=FrozenTypeRegistry(()),
        ),
    )
    canonical_bytes(
        FrozenMap((("k" * limits.max_string_bytes, 1),)),
        style="capture_plain",
        limits=limits,
        type_ids=FrozenTypeRegistry(()),
    )
    expect_failure(
        "map key UTF-8 limit plus one",
        lambda: canonical_bytes(
            FrozenMap((("k" * (limits.max_string_bytes + 1), 1),)),
            style="capture_plain",
            limits=limits,
            type_ids=FrozenTypeRegistry(()),
        ),
    )
    canonical_bytes(
        FrozenMap(tuple((f"k{index}", index) for index in range(8))),
        style="capture_plain",
        limits=limits,
        type_ids=FrozenTypeRegistry(()),
    )
    expect_failure(
        "map entry limit plus one",
        lambda: canonical_bytes(
            FrozenMap(tuple((f"k{index}", index) for index in range(9))),
            style="capture_plain",
            limits=limits,
            type_ids=FrozenTypeRegistry(()),
        ),
    )

    exact_depth: Any = 0
    for _index in range(limits.max_depth):
        exact_depth = (exact_depth,)
    canonical_bytes(
        exact_depth,
        style="capture_plain",
        limits=limits,
        type_ids=FrozenTypeRegistry(()),
    )
    expect_failure(
        "root-depth-0 limit plus one",
        lambda: canonical_bytes(
            (exact_depth,),
            style="capture_plain",
            limits=limits,
            type_ids=FrozenTypeRegistry(()),
        ),
    )
    expect_failure(
        "recursion configuration ceiling",
        lambda: CanonicalLimits(
            max_output_bytes=4_096,
            max_depth=MAX_CANONICAL_RECURSION_DEPTH + 1,
            max_nodes=MAX_CANONICAL_RECURSION_DEPTH + 2,
            max_collection_items=8,
            max_artifact_fields=8,
            max_string_bytes=64,
            max_payload_bytes=64,
            max_aggregate_scalar_bytes=1_024,
            min_integer=-1,
            max_integer=1,
        ),
    )

    writer = _Writer(
        style="capture_plain",
        limits=limits,
        type_ids=FrozenTypeRegistry(()),
        error_type=ValueError,
    )
    expect_failure(
        "partial output cleanup",
        lambda: writer.finish(FrozenList((1, object()))),
    )
    require(not writer.output, "partial output was not cleared")
    require(not writer.active_container_ids, "container state was not unwound")
    require(
        len(_FIXED_TRUSTED_FROZEN_MUTATORS) == 2,
        "arbitrary generated mutator witnesses were retained",
    )

    error_constructor_calls: list[str] = []

    class HostileError(ValueError):
        def __init__(self, message: str) -> None:
            error_constructor_calls.append(message)
            super().__init__(message)

    expect_failure(
        "hostile public error constructor",
        lambda: canonical_bytes(
            None,
            style="capture_plain",
            limits=limits,
            type_ids=FrozenTypeRegistry(()),
            error_type=HostileError,
        ),
    )
    require(not error_constructor_calls, "hostile error constructor executed")


if __name__ == "__main__":
    run_self_test()
    print("bounded canonical self-test: PASS")
