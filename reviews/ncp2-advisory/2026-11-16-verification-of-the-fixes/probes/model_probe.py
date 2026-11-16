"""Investigations of model/lockstep.py of revision 6 (advisory; certifies nothing).

Usage: python3 -I -B model_probe.py SNAP MODE [--faults N] [--shape stream|zenoh|both]

The probe reads SNAP/model/lockstep.py, applies exact text patches (each must match once), and runs
the patched search in this process. Nothing in SNAP is written.

MODE
  count        the shipped properties, with counters: how often each check has a non-trivial premise
  precise      S4 with a precise excuse (the owner's state at the take is neither L's known state
               nor that state plus L's uncertain step, or the state was replaced), and S6 without
               the excuse w.other
  own          mutant: a client that gives no verdict unless the request it knew is one of its own
               (shipped excuses)
  own-precise  the same mutant, with the precise S4
"""

from __future__ import annotations

import collections
import os
import sys
import types

SNAP, MODE = sys.argv[1], sys.argv[2]
FAULTS = int(sys.argv[sys.argv.index("--faults") + 1]) if "--faults" in sys.argv else 1
SHAPE = sys.argv[sys.argv.index("--shape") + 1] if "--shape" in sys.argv else "both"
PATH = os.path.join(SNAP, "model", "lockstep.py")
source = open(PATH, encoding="utf-8").read()


def patch(old: str, new: str) -> None:
    global source
    assert source.count(old) == 1, f"patch does not apply once: {old[:80]!r} ({source.count(old)})"
    source = source.replace(old, new)


# Ghosts: what L's known clock is in terms of the owner's state (the steps in it), and a state epoch
# that a restart with another state raises.
patch(
    "    opening: int | None = None  # ghost: the opening of its current session\n",
    "    opening: int | None = None  # ghost: the opening of its current session\n"
    "    known_current: tuple = ()  # probe ghost: the steps in the owner's state that L's known clock describes\n"
    "    known_epoch: int = 0  # probe ghost\n",
)
patch(
    "    taken: tuple = ()  # ghost: sorted (opening, (the clock, current) when the take of that opening ran)\n",
    "    taken: tuple = ()  # ghost: sorted (opening, (the clock, current) when the take of that opening ran)\n"
    "    epoch: int = 0  # probe ghost: raised by a restart with another state\n"
    "    step_ghost: tuple = ()  # probe ghost: (identity, (current after it, epoch))\n",
)
patch(
    "opening: (clock, w.current)}.items()))",
    "opening: (clock, w.current, w.epoch)}.items()))",
)
patch(
    "            changes[\"current\"] = w.current + (identity,)\n",
    "            changes[\"current\"] = w.current + (identity,)\n"
    "            changes[\"step_ghost\"] = w.step_ghost + ((identity, (w.current + (identity,), w.epoch)),)\n",
)
# L learns a clock from a take: record which state it describes.
patch(
    "                return dataclasses.replace(w, stepper=dataclasses.replace(s, known=taken, phase=phase, holds=True))\n",
    "                at = dict(w.taken)[s.opening]\n"
    "                return dataclasses.replace(w, stepper=dataclasses.replace(s, known=taken, phase=phase, holds=True,\n"
    "                                                                          known_current=at[1], known_epoch=at[2]))\n",
)
# ... and from the ok of a step.
patch(
    "            s = dataclasses.replace(s, known=(member[\"tick\"], member[\"state\"], member[\"request\"]), done=done,\n"
    "                                    phase=\"done\" if done >= STEPS else \"step\")\n",
    "            g = dict(w.step_ghost)[identity]\n"
    "            s = dataclasses.replace(s, known=(member[\"tick\"], member[\"state\"], member[\"request\"]), done=done,\n"
    "                                    phase=\"done\" if done >= STEPS else \"step\", known_current=g[0], known_epoch=g[1])\n",
)
patch(
    "                rewound = dataclasses.replace(restarted, rewound=True, current=(),\n",
    "                rewound = dataclasses.replace(restarted, rewound=True, current=(), epoch=w.epoch + 1,\n",
)
# The verdict: counters, the mutant, and the precise S4.
patch(
    "        verdict = self.judge(s.known, s.uncertain, taken)\n"
    "        if verdict is ncp.Executed.UNKNOWN:\n"
    "            if w.other or w.rewound or w.older:\n",
    "        verdict = self.judge(s.known, s.uncertain, taken)\n"
    "        if PROBE['own'] and s.known[2] is not None and s.known[2] not in own_steps(w):\n"
    "            verdict = ncp.Executed.UNKNOWN  # mutant: no verdict unless L made the request it knew\n"
    "        at = dict(w.taken).get(s.opening)\n"
    "        clean = at is not None and at[2] == s.known_epoch and at[1] in (s.known_current, s.known_current + (identity,))\n"
    "        COUNT['verdicts'] += 1\n"
    "        COUNT[f'verdict {verdict.value}'] += 1\n"
    "        if verdict is ncp.Executed.UNKNOWN:\n"
    "            COUNT['unknown, clean (a verdict was possible)' if clean else 'unknown, not clean'] += 1\n"
    "            for flag in ('other', 'rewound', 'older'):\n"
    "                if getattr(w, flag):\n"
    "                    COUNT[f'unknown excused by w.{flag}'] += 1\n"
    "        if verdict is ncp.Executed.NO and w.older and identity in w.ran:\n"
    "            COUNT['S1 weakened branch used: no for a step that ran before an older restart'] += 1\n"
    "        if verdict is ncp.Executed.UNKNOWN and PROBE['precise']:\n"
    "            if not clean:\n"
    "                return w, dataclasses.replace(s, uncertain=None)\n"
    "            raise Violation('S4', f'precise: no verdict although the state at the take was clean: {taken}, L knew {s.known}')\n"
    "        if verdict is ncp.Executed.UNKNOWN:\n"
    "            if w.other or w.rewound or w.older:\n",
)
patch(
    "            require(w.other or (at_take is not None and at_take[0][1:3] == s.known[1:3]), \"S6\",\n",
    "            require((w.other and not PROBE['precise']) or (at_take is not None and at_take[0][1:3] == s.known[1:3]), \"S6\",\n",
)
patch(
    "                if not w.faults and not w.timed and not free:\n",
    "                if not free:\n"
    "                    COUNT[f'terminal worlds, phase {w.stepper.phase}, faults {w.faults}'] += 1\n"
    "                if not w.faults and not w.timed and not free:\n"
    "                    COUNT['progress checked'] += 1\n",
)

module = types.ModuleType("lockstep_probe")
module.__file__ = PATH
module.COUNT = collections.Counter()
module.PROBE = {"precise": MODE in ("precise", "own-precise"), "own": MODE in ("own", "own-precise")}


def own_steps(w):
    F = module.F
    ids = set()
    for _key, frame in w.sent:
        decoded = F.decode(frame, F.MAX_BOUND)
        if decoded.message.get("op") == "step":
            ids.add(decoded.identity)
    return ids


module.own_steps = own_steps
sys.modules["lockstep_probe"] = module
exec(compile(source, PATH + " (patched)", "exec"), module.__dict__)

shapes = ("stream", "zenoh") if SHAPE == "both" else (SHAPE,)
status = 0
for same in (False, True):
    for shape in shapes:
        module.COUNT.clear()
        label = f"{shape}, {'one session identifier' if same else 'new session identifiers'}"
        try:
            worlds, transitions = module.Search(shape, FAULTS, None, same, 60_000_000).run()
            print(f"{label}: {worlds} worlds, every property holds")
        except module.Violation as violation:
            print(f"{label}: VIOLATION {violation}")
            status = 1
        for key in sorted(module.COUNT):
            print(f"    {key}: {module.COUNT[key]}")
sys.exit(status)
