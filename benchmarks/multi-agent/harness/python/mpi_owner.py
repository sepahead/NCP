"""The rank-0 owner of part M of the multi-agent benchmark (../../PROTOCOL.md; spec section 16).

Usage: mpirun -n RANKS python mpi_owner.py PATH
       python mpi_owner.py PATH --no-mpi

Rank 0 serves one NCP 2 session on a Unix domain socket at PATH and prints "ready PATH". For each
`spikes` request {"n": S}, rank 0 sends S to every rank with an MPI broadcast; each rank makes
its share of the S spikes, and rank 0 collects the shares with MPI gathers and responds with two
arrays: senders (u32) and times (f64). Spike i of a call comes from sender i mod 1000 + 1 at
time (i mod 100) / 10 + 0.1 ms, whichever rank made it, so the client can check every spike.
With --no-mpi, one process makes all spikes, without MPI. Needs numpy and, with MPI, mpi4py.
"""

from __future__ import annotations

import os
import socket
import sys
from typing import Any

import ncp
import numpy as np

SPIKES = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"spikes","version":"1","operations":{"spikes":{}},"streams":{}}'
)
MAX_SPIKES = 1 << 22
BOUND = 4 << 20


def share(start: int, count: int) -> tuple[np.ndarray, np.ndarray]:
    """Spikes start to start + count - 1."""
    index = np.arange(start, start + count, dtype=np.int64)
    return (index % 1000 + 1).astype("<u4"), ((index % 100) / 10.0 + 0.1).astype("<f8")


def layout(total: int, size: int) -> tuple[list[int], list[int]]:
    """How many spikes each rank makes, and where its share starts."""
    counts = [total // size + (1 if rank < total % size else 0) for rank in range(size)]
    starts = [sum(counts[:rank]) for rank in range(size)]
    return counts, starts


class Handler:
    def __init__(self, comm: Any) -> None:
        self.comm = comm

    def validate(self, op: str, body: Any) -> None:
        if type(body) is not dict or type(body.get("n")) is not int or not 0 <= body["n"] <= MAX_SPIKES:
            raise ncp.BodyInvalid(f"n must be an integer from 0 to {MAX_SPIKES}")

    def execute(self, op: str, body: Any) -> Any:
        total = body["n"]
        if self.comm is None:
            senders, times = share(0, total)
        else:
            self.comm.bcast(total, root=0)
            senders, times = gather(self.comm, total)
        return {"senders": ncp.Array.from_numpy(senders), "times": ncp.Array.from_numpy(times)}


def gather(comm: Any, total: int) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Each rank makes its share; rank 0 receives all shares, in rank order."""
    from mpi4py import MPI

    rank, size = comm.Get_rank(), comm.Get_size()
    counts, starts = layout(total, size)
    senders, times = share(starts[rank], counts[rank])
    if rank == 0:
        all_senders = np.empty(total, dtype="<u4")
        all_times = np.empty(total, dtype="<f8")
        comm.Gatherv(senders, [all_senders, counts, starts, MPI.UINT32_T], root=0)
        comm.Gatherv(times, [all_times, counts, starts, MPI.DOUBLE], root=0)
        return all_senders, all_times
    comm.Gatherv(senders, None, root=0)
    comm.Gatherv(times, None, root=0)
    return None, None


def main() -> None:
    path = sys.argv[1]
    comm = None
    if "--no-mpi" not in sys.argv[2:]:
        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        if comm.Get_rank() != 0:
            while True:  # the other ranks follow rank 0's requests until it sends None
                total = comm.bcast(None, root=0)
                if total is None:
                    return
                gather(comm, total)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)
    print(f"ready {path}", flush=True)
    connection, _ = listener.accept()
    listener.close()
    owner = ncp.Owner("spikes", SPIKES.identity, Handler(comm), ["spikes"], max_bound=BOUND)
    ncp.serve(owner, ncp.StreamChannel.from_socket(connection))  # until the client closes
    if comm is not None:
        comm.bcast(None, root=0)
    os.unlink(path)


if __name__ == "__main__":
    main()
