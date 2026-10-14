"""NEST alone, no exchange. Usage: arm_local.py {mono|chunked|chunked-spikes} DELTA_MS

chunked reads only the spike count after each chunk; chunked-spikes reads the new spikes
themselves with the n_events-delta readback."""
from __future__ import annotations

import json
import sys

import nest

from common import T_BIO_MS, Reader, build, configure, load1, now


def main() -> None:
    mode, delta = sys.argv[1], float(sys.argv[2])
    configure(nest)
    _, recorder = build(nest, delta)
    reader = Reader(recorder)
    load = load1()
    nest.Prepare()
    spikes = 0
    if mode == "mono":
        t0 = now()
        nest.Run(T_BIO_MS)
        senders, _ = reader.take()
        t1 = now()
        spikes = len(senders)
    elif mode == "chunked":
        steps = round(T_BIO_MS / delta)
        seen = 0
        t0 = now()
        for _ in range(steps):
            nest.Run(delta)
            n = recorder.n_events
            spikes += n - seen
            seen = n
        t1 = now()
    else:
        steps = round(T_BIO_MS / delta)
        t0 = now()
        for _ in range(steps):
            nest.Run(delta)
            senders, _ = reader.take()
            spikes += len(senders)
        t1 = now()
    nest.Cleanup()
    print(json.dumps({"arm": mode, "delta_ms": delta, "wall_s": t1 - t0, "spikes": spikes, "load1": load}))


if __name__ == "__main__":
    main()
