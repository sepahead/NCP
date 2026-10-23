"""Firing rates of each network for a short run (calibration only; not a result).

Usage: calibrate.py NETWORK N THREADS DELTA_MS [AEIF_DRIVE_NS]
"""
import json
import sys
import time

import nest

import networks

network, n, threads, delta = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
if len(sys.argv) > 5:
    networks.AEIF_DRIVE_NS = float(sys.argv[5])
networks.configure(nest, threads, 20261023)
neurons, recorder = networks.build(nest, network, n, delta)
t0 = time.perf_counter()
nest.Simulate(500.0)
wall = time.perf_counter() - t0
print(json.dumps({"network": network, "n": n, "threads": threads, "delta": delta,
                  "rate_hz": recorder.n_events / n / 0.5, "wall_s_500ms": round(wall, 3),
                  "connections": nest.num_connections}))
