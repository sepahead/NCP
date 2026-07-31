#!/usr/bin/env python3
"""Load the repository bounded-JSON implementation from one pinned snapshot."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from source_inventory import read_bounded_relative_file

REPOSITORY = Path(__file__).resolve().parents[2]
BOUNDED_JSON_RELATIVE_PATH = "scripts/bounded_json.py"
BOUNDED_JSON_SUPPORT_PATHS = (BOUNDED_JSON_RELATIVE_PATH,)
MAX_BOUNDED_JSON_IMPLEMENTATION_BYTES = 131_072
_MODULE_NAME = "bounded_json"


def _load_bounded_json() -> ModuleType:
    if _MODULE_NAME in sys.modules:
        raise RuntimeError("bounded-JSON private module name was prepopulated")
    content = read_bounded_relative_file(
        REPOSITORY,
        BOUNDED_JSON_RELATIVE_PATH,
        maximum_bytes=MAX_BOUNDED_JSON_IMPLEMENTATION_BYTES,
        label="bounded-JSON support implementation",
    )
    module = ModuleType(_MODULE_NAME)
    module.__file__ = str(REPOSITORY / BOUNDED_JSON_RELATIVE_PATH)
    module.__package__ = ""
    sys.modules[_MODULE_NAME] = module
    try:
        code = compile(
            content,
            module.__file__,
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(code, module.__dict__)  # noqa: S102
    except BaseException:
        sys.modules.pop(_MODULE_NAME, None)
        raise
    if (
        type(module.BoundedJsonError) is not type
        or not issubclass(module.BoundedJsonError, ValueError)
        or module.BoundedJsonError.__module__ != _MODULE_NAME
        or type(module.JsonLimits) is not type
        or module.JsonLimits.__module__ != _MODULE_NAME
        or not callable(module.parse_json_bytes)
        or module.parse_json_bytes.__module__ != _MODULE_NAME
    ):
        sys.modules.pop(_MODULE_NAME, None)
        raise RuntimeError("bounded-JSON support exports are not the exact module")
    return module


_bounded_json = _load_bounded_json()
BoundedJsonError: type[ValueError] = _bounded_json.BoundedJsonError
JsonLimits: Any = _bounded_json.JsonLimits
parse_json_bytes = _bounded_json.parse_json_bytes
