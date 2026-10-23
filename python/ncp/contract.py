"""Application contracts and the multi-session host helper (sections 11 and 15)."""
from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Sequence

from .exchange import Client, Ended, Rejected, Result


@dataclass(frozen=True)
class Contract:
    """A contract document and its identity: the SHA-256 digest of its exact bytes."""

    data: bytes
    identity: str
    application: str
    version: str
    operations: frozenset[str]
    streams: frozenset[str]

    @classmethod
    def from_bytes(cls, data: bytes) -> "Contract":
        document = json.loads(data.decode("utf-8"))
        if (type(document) is not dict or document.get("ncp_contract") != 1
                or type(document.get("application")) is not str or not 1 <= len(document["application"]) <= 128
                or type(document.get("version")) is not str or type(document.get("operations")) is not dict
                or type(document.get("streams")) is not dict):
            raise ValueError("not an NCP contract")
        return cls(data, hashlib.sha256(data).hexdigest(), document["application"], document["version"],
                   frozenset(document["operations"]), frozenset(document["streams"]))

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "Contract":
        with open(path, "rb") as handle:
            return cls.from_bytes(handle.read())


def call_all(clients: Sequence[Client], op: str, bodies: Sequence[Any], *,
             executor: ThreadPoolExecutor | None = None) -> list[Result | Exception]:
    """Send one request to each session and wait for all responses (section 15).

    Sessions are independent: an exception of one session is returned in its place and does
    not stop the others.
    """
    if len(clients) != len(bodies):
        raise ValueError("one body for each client")

    def one(index: int) -> Result | Exception:
        try:
            return clients[index].call(op, bodies[index])
        except (Rejected, Ended, OSError, EOFError) as error:
            return error

    if executor is None:
        with ThreadPoolExecutor(max_workers=min(64, len(clients)) or 1) as pool:
            return list(pool.map(one, range(len(clients))))
    return list(executor.map(one, range(len(clients))))
