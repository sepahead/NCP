"""Python host of content protocol 3 (see ../PROTOCOL-CONTENT-3.md), on revision 7 of the SDKs.

Usage: ncp2_host7.py NETWORK N THREADS DELTA_MS SEED OUT
Starts the NEST owner ncp2_owner7.py as a child, prepares the network, advances 2 s of simulated
time in steps of DELTA_MS, and finishes. Writes every received event to OUT as JSON and prints one
JSON line. The NCP 2 Python SDK is the `ncp` package on PYTHONPATH; the owner uses the same one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import ncp
from common import T_BIO_MS, emit, spec_from
from networks7 import ARRAYS

HERE = Path(__file__).resolve().parent
CONTRACT = ncp.Contract.load(HERE / "ncp2_contract.json")


def main() -> None:
    spec, out = spec_from(sys.argv[1:6]), Path(sys.argv[6])
    channel = ncp.spawn([sys.executable, "-s", str(HERE / "ncp2_owner7.py")], cwd=str(HERE))
    client = ncp.Client(channel, CONTRACT, timeout=600)
    client.open()
    first = client.call("prepare", spec).body["first"]
    steps = round(T_BIO_MS / spec["delta_ms"])
    collected: dict[str, list] = {name: [] for name, _, _ in ARRAYS}
    for _ in range(steps):
        body = client.call("step", {}).body
        for name, dtype, _ in ARRAYS:
            value = body[name]
            if not isinstance(value, ncp.Array) or value.dtype != dtype or len(value.shape) != 1:
                raise SystemExit(f"step: {name} is not a one-dimensional {dtype} array")
            collected[name] += value.tolist()
    finished = client.call("finish", {}).body
    client.close()
    channel.close()
    code = channel.process.wait(timeout=120)
    out.write_text(json.dumps({"first": first, **collected}))
    emit(
        {
            "arm": "ncp2-py",
            **spec,
            "exchanges": steps,
            "spikes": len(collected["senders"]),
            "vm": len(collected["vm_values"]),
            "owner_sent": finished,
            "child_exit": code,
        }
    )


if __name__ == "__main__":
    main()
