"""Smoke calibration of the drive (not a result): mean rate per neuron for candidate parameters."""
import json
import sys

import nest

import common

for rate, w_in, w_rec in [(6000.0, 10.2, 2.0), (6000.0, 10.4, 2.0), (6000.0, 10.6, 2.0), (6000.0, 10.8, 2.0)]:
    common.PARAMS.update({"drive_rate_hz": rate, "drive_weight_pa": w_in, "rec_weight_pa": w_rec})
    common.configure(nest)
    _, rec = common.build(nest, 1.0)
    nest.Simulate(1000.0)
    print(json.dumps({"rate_hz": rate, "w_in": w_in, "w_rec": w_rec, "mean_rate": rec.n_events / 1000.0}), flush=True)
