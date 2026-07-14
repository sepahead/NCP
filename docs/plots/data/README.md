# Benchmark data audit trail

> These files and fallback constants are historical developer evidence. They are not
> bound to the unreleased NCP `1.0.0-rc.1` artifact set and do not satisfy the
> release performance/resource gate. A certification run must retain raw data,
> source/package/config/toolchain/environment digests, and uncertainty.

This directory holds machine-generated JSON results from the NCP benchmark
scripts. `scripts/plot_perf.py` reads them (when present) to generate the
performance figures in `docs/plots/`, creating a provenance chain:

```
bench_*.py --out docs/plots/data/<name>.json  →  plot_perf.py  →  docs/plots/*.svg
```

When the JSON files are absent (e.g. NEST is not installed), `plot_perf.py`
falls back to hardcoded constants transcribed from `PERFORMANCE.md` and
`NEST_REALTIME.md`, so SVG generation never breaks.

## Regenerating the audit trail

```bash
# Real-time factor sweep (requires NEST)
python3 scripts/bench_realtime.py --out docs/plots/data/realtime.json \
    --n 10000 50000 100000 200000 --threads 1 2 4 8 16 --reps 3

# GIL overlap (requires NEST + a C compiler for the ctypes native lib)
python3 scripts/bench_gil_overlap.py --out docs/plots/data/gil_overlap.json

# Overlap ceiling (requires NEST)
python3 scripts/bench_overlap.py --out docs/plots/data/overlap.json

# Chunk overhead (requires NEST)
python3 scripts/bench_chunk_overhead.py --out docs/plots/data/chunk_overhead.json

# Regenerate the SVGs (picks up the data files automatically)
python3 -m venv .venv-plot
.venv-plot/bin/pip install -r scripts/requirements-plot.txt
.venv-plot/bin/python scripts/plot_perf.py
.venv-plot/bin/python scripts/plot_perf.py --check
```

The generator uses fixed Matplotlib/NumPy versions, a fixed SVG hash salt, and no
wall-clock metadata. Its strict input reader rejects duplicate keys, partial grids,
non-finite values, and data whose configuration would contradict the figure
caption. Exact SVG reproduction is documentation hygiene, not performance
certification.

## File format

Each JSON file is the direct output of the corresponding benchmark script's
`--out` flag — the same JSON that is also printed to stdout. The schema is
script-specific (see each script's docstring), but all include a `nest_version`
field for reproducibility.
