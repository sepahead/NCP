"""Deterministic spike body shared by the Python client checks and the Python owner."""
from __future__ import annotations


def spikes(n: int) -> dict:
    state = 0x2545F4914F6CDD1D
    senders, times = [], []
    for _ in range(n):
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        senders.append((state >> 33) % 1000 + 1)
        times.append(((state >> 20) % 100) / 10.0 + 0.1)
    return {"senders": senders, "times": times}
