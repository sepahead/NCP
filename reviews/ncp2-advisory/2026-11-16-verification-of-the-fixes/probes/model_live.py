"""Liveness after one fault in model/lockstep.py of revision 6 (advisory; certifies nothing).

Usage: python3 -I -B model_live.py SNAP

Counts the terminal worlds (no free transition left) by L's phase, by the kind of the one fault,
and by whether a time limit expired, and prints one trace for each stuck kind without a time limit.
The world gets a ghost `fault_kind`, so the world counts differ slightly from the shipped search.
"""

from __future__ import annotations

import collections
import os
import sys
import types

SNAP = sys.argv[1]
PATH = os.path.join(SNAP, "model", "lockstep.py")
source = open(PATH, encoding="utf-8").read()


def patch(old: str, new: str) -> None:
    global source
    assert source.count(old) == 1, f"patch does not apply once: {old[:80]!r}"
    source = source.replace(old, new)


patch(
    "    taken: tuple = ()  # ghost: sorted (opening, (the clock, current) when the take of that opening ran)\n",
    "    taken: tuple = ()  # ghost: sorted (opening, (the clock, current) when the take of that opening ran)\n"
    "    fault_kind: str = ''  # probe ghost\n",
)
patch(
    "                if not w.faults and not w.timed and not free:\n",
    "                if not free:\n"
    "                    key = (w.stepper.phase, w.fault_kind or 'no fault', 'timed' if w.timed else 'no time limit')\n"
    "                    COUNT[key] += 1\n"
    "                    if key[0] != 'done' and not w.timed and key[1] not in TRACES:\n"
    "                        trace, k = [], w\n"
    "                        while parents.get(k) is not None:\n"
    "                            k, label = parents[k]\n"
    "                            trace.append(label)\n"
    "                        TRACES[key[1]] = ' -> '.join(reversed(trace)) + f'  [index {w.stepper.index}, done {w.stepper.done}, ran {len(w.ran)}]'\n"
    "                if not w.faults and not w.timed and not free:\n",
)
patch(
    "            for label, nxt in successors:\n"
    "                transitions += 1\n",
    "            for number, (label, nxt) in enumerate(successors):\n"
    "                if number >= free:\n"
    "                    nxt = dataclasses.replace(nxt, fault_kind=label)\n"
    "                transitions += 1\n",
)

module = types.ModuleType("lockstep_live")
module.__file__ = PATH
module.COUNT = collections.Counter()
module.TRACES = {}
sys.modules["lockstep_live"] = module
exec(compile(source, PATH + " (patched)", "exec"), module.__dict__)

for same in (False, True):
    for shape in ("stream", "zenoh"):
        module.COUNT.clear()
        module.TRACES.clear()
        label = f"{shape}, {'one session identifier' if same else 'new session identifiers'}"
        worlds, _ = module.Search(shape, 1, None, same, 60_000_000).run()
        print(f"== {label}: {worlds} worlds")
        for key in sorted(module.COUNT):
            print(f"    {key}: {module.COUNT[key]}")
        for kind, trace in sorted(module.TRACES.items()):
            print(f"  stuck without a time limit after '{kind}':\n      {trace}")
