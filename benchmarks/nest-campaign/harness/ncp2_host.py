"""Python host for the NCP 2 arms: drives the NEST owner of ncp2_owner.py.

Usage: ncp2_host.py {count|spikes} NETWORK N THREADS DELTA_MS SEED
The NCP 2 Python SDK is the `ncp` package on PYTHONPATH; the owner uses the same one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import ncp
from common import T_BIO_MS, emit, load1, now, spec_from

HERE = Path(__file__).resolve().parent
CONTRACT = ncp.Contract.load(HERE / "ncp2_contract.json")


def main() -> None:
    payload, spec = sys.argv[1], spec_from(sys.argv[2:])
    channel, process = ncp.spawn([sys.executable, "-s", str(HERE / "ncp2_owner.py")], cwd=str(HERE))
    client = ncp.Client(channel, application=CONTRACT.application, contract=CONTRACT.identity, timeout=300)
    client.open()
    client.call("prepare", {**spec, "payload": payload})
    steps = round(T_BIO_MS / spec["delta_ms"])
    load = load1()
    spikes = 0
    t0 = now()
    for _ in range(steps):
        body = client.call("step", {"stimulus": 0}).body
        spikes += body["count"] if payload == "count" else body["senders"].shape[0]
    t1 = now()
    finished = client.call("finish", {}).body
    client.close()
    code = process.wait(timeout=120)
    emit(
        {
            "arm": f"ncp2-py-{payload}",
            **spec,
            "wall_s": t1 - t0,
            "spikes": spikes,
            "recorded": finished["recorded"],
            "exchanges": steps,
            "load1": load,
            "child_exit": code,
        }
    )


if __name__ == "__main__":
    main()
