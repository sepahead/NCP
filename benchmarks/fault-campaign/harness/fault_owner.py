"""Python echo owner with injectable faults (see ../PROTOCOL.md).

Usage: fault_owner.py BINDING_JSON
Environment:
  FAULT_DELAY_S      seconds that each step sleeps before it returns (default 0)
  FAULT_STALL_STEP   step number that sleeps FAULT_STALL_S seconds (default none)
  FAULT_OVERSIZE_STEP step number whose result exceeds the frame limit (default none)
  FAULT_RAISE_STEP   step number whose backend raises (default none)
  FAULT_MARKER       file that retire() writes, to show that the owner retired
"""
from __future__ import annotations

import json
import os
import sys
import time

from ncp_local import LocalBinding, LocalOwner, serve_local


def env_int(name: str) -> int | None:
    value = os.environ.get(name)
    return int(value) if value else None


class FaultBackend:
    def __init__(self) -> None:
        self.steps = 0
        self.delay = float(os.environ.get("FAULT_DELAY_S", "0"))
        self.stall_step, self.stall_s = env_int("FAULT_STALL_STEP"), float(os.environ.get("FAULT_STALL_S", "0"))
        self.oversize_step = env_int("FAULT_OVERSIZE_STEP")
        self.raise_step = env_int("FAULT_RAISE_STEP")
        self.marker = os.environ.get("FAULT_MARKER")

    def validate(self, operation, body) -> None:
        pass

    def execute(self, operation, body):
        if operation != "step":
            return {"ok": True}
        self.steps += 1
        if self.delay:
            time.sleep(self.delay)
        if self.steps == self.stall_step:
            time.sleep(self.stall_s)
        if self.steps == self.raise_step:
            raise RuntimeError("injected backend failure")
        if self.steps == self.oversize_step:
            return {"blob": "x" * 70_000}
        return {"count": 13, "step": self.steps}

    def retire(self) -> None:
        if self.marker:
            with open(self.marker, "a") as handle:
                handle.write(json.dumps({"retired_after_steps": self.steps}) + "\n")


def main() -> None:
    binding = LocalBinding.from_dict(json.loads(sys.argv[1]))
    serve_local(LocalOwner(binding, FaultBackend()), sys.stdin.buffer, os.fdopen(1, "wb", buffering=0))


if __name__ == "__main__":
    main()
