# Multi-agent benchmark

How NCP 2 behaves when one program works with many others:

- **Part F, one host and many owners.** A controller sends one request to each of up to 256 owner programs per step and waits for all responses.
- **Part R, many agents and one owner in rounds.** Up to 256 agents share one simulated world, which applies one request of each agent per round, in a fixed order ([rounds profile](../../spec/NCP-2-ROUNDS.md)).
- **Part M, an MPI program as the owner.** An owner made of 1 to 8 MPI processes serves one session from its first process, rank 0.

The [protocol](PROTOCOL.md) was fixed before the runs. It states the questions, the programs, the configurations, the hypotheses with their decision rules, and what the results do not show.

## Results

The runs of the protocol have not finished yet.

## Run it

```sh
python3 benchmarks/multi-agent/run.py RESULTS_DIR --python python3.15 --mpi-env CONDA_ENV
```

The runner needs cargo, a Python 3.11 or later for parts F and R, and a conda environment with Open MPI, mpi4py, and numpy for part M (`CONDA_ENV/bin/python` and `CONDA_ENV/bin/mpirun`).
It builds the harness and the clock probe of the NEST campaign, runs the validity checks of the protocol, writes the schedule, and then runs three blocks of 125 configurations, waiting before each run for the conditions of [`../conditions.py`](../conditions.py) (macOS).
It appends each run to `RESULTS_DIR/runs.jsonl`; when it stops, the same command resumes it.
Put `RESULTS_DIR` outside the repository: the runner builds its programs in `RESULTS_DIR/.work`.
