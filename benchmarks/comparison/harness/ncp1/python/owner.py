"""Echo owner for the local Python SDK (see ../../PROTOCOL.md).

Usage: owner.py BINDING_JSON. Serves one generation on the inherited pipes.
"""
from __future__ import annotations

import json
import os
import sys

from ncp_local import LocalBinding, LocalOwner, serve_local

from spikes import spikes


class Echo:
    """Builds the spike body once in prepare, as every arm of benchmarks/comparison does."""

    def __init__(self) -> None:
        self.n = 0
        self.body: dict = {}

    def validate(self, operation, body) -> None:
        pass

    def execute(self, operation, body):
        if operation == "prepare":
            self.n = body["n"]
            self.body = {"count": 13} if self.n == 0 else spikes(self.n)
            return {"prepared": True}
        if operation == "step":
            return self.body
        return {"finished": True}

    def retire(self) -> None:
        pass


def main() -> None:
    binding = LocalBinding.from_dict(json.loads(sys.argv[1]))
    serve_local(LocalOwner(binding, Echo()), sys.stdin.buffer, os.fdopen(1, "wb", buffering=0))


if __name__ == "__main__":
    main()
