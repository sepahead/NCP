#!/usr/bin/env python3
"""Subprocess worker for crash and concurrent replay-store tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prototype.replay import PinnedReplayState, ReplayKey, ReplayStore
from prototype.strict import PrototypeError


def main() -> int:
    request = json.loads(sys.stdin.read())
    pinned = PinnedReplayState(
        request["store_id"],
        request["recovery_epoch"],
    )
    key = ReplayKey(**request["key"])
    with ReplayStore.open(Path(request["path"]), pinned) as store:
        try:
            store._commit_sequence(
                key,
                request["sequence"],
                failpoint=request.get("failpoint"),
            )
        except PrototypeError as error:
            print(json.dumps({"accepted": False, "code": error.code}))
            return 3
    marker = request.get("consumer_marker")
    if marker:
        Path(marker).write_text("consumed\n", encoding="utf-8")
    print(json.dumps({"accepted": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
