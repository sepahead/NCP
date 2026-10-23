"""NEST without coupling. Usage: local_arm.py {mono|chunked|chunked-spikes} NETWORK N THREADS DELTA_MS SEED

`chunked` reads the spike count after each interval; `chunked-spikes` reads the new spikes."""
from __future__ import annotations

import shutil
import sys
import tempfile

import nest

import networks
from common import T_BIO_MS, emit, load1, now, spec_from


def main() -> None:
    mode, spec = sys.argv[1], spec_from(sys.argv[2:])
    networks.configure(nest, spec["threads"], spec["seed"])
    spike_files = tempfile.mkdtemp(prefix="ncp-nest-spikes-") if mode == "chunked-spikes" else None
    _, recorder = networks.build(nest, spec["network"], spec["n"], spec["delta_ms"], spike_files)
    reader = networks.Reader(nest, spike_files)
    load = load1()
    nest.Prepare()
    steps = round(T_BIO_MS / spec["delta_ms"])
    spikes = 0
    t0 = now()
    if mode == "mono":
        nest.Run(T_BIO_MS)
        spikes = reader.count()
    elif mode == "chunked":
        for _ in range(steps):
            nest.Run(spec["delta_ms"])
            spikes += reader.count()
    else:
        for _ in range(steps):
            nest.Run(spec["delta_ms"])
            spikes += len(reader.take()[0])
    t1 = now()
    recorded = int(recorder.n_events)
    nest.Cleanup()
    if spike_files:
        shutil.rmtree(spike_files, ignore_errors=True)
    emit({"arm": mode, **spec, "wall_s": t1 - t0, "spikes": spikes, "recorded": recorded, "exchanges": steps,
          "load1": load})


if __name__ == "__main__":
    main()
