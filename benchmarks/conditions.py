"""The conditions of a timed run on the benchmark computer (macOS), as NEST protocol 5 defines them.

Before a run, a runner waits until the computer draws power from its adapter, its thermal pressure
is nominal (level 0), a core runs at CLOCK_MIN_GHZ or more, and the one-minute load average is
below LOAD_LIMIT. After the run, the run is disturbed when the computer slept for more than
SLEEP_LIMIT_S, or when it no longer meets the conditions, with END_CLOCK_MIN_GHZ as the clock limit
and without the load limit. A disturbed run is repeated, at most MAX_ATTEMPTS times in all.

The clock comes from the probe of nest-campaign/harness/ncp2-rust/src/bin/clock-probe.rs.
nest-campaign/run4.py keeps its own copy of these rules, used for the recorded runs of protocols 4
and 5; comparison/run.py uses this module for its protocol 2.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

LOAD_LIMIT = 8.0  # half of the 16 cores of the computer
CLOCK_MIN_GHZ = 4.0  # an M4 Max performance core runs at up to 4.5 GHz, and at about 3.1 GHz when limited
END_CLOCK_MIN_GHZ = 3.8  # NEST protocol 5: readings just below 4.0 GHz after a long run are normal
MAX_ATTEMPTS = 3
SLEEP_LIMIT_S = 0.5


def _out(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def read(probe: Path) -> dict:
    """Power source, thermal pressure (0 is nominal), clock of a core, and the one-minute load average.
    The clock is the larger of two probes, in case the scheduler puts one on an efficiency core."""
    power = _out(["pmset", "-g", "batt"]).splitlines()[0]
    thermal = _out(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"]).split()[-1]
    clock = max(float(_out([str(probe)])) for _ in range(2))
    return {
        "ac_power": "AC Power" in power,
        "thermal_pressure": int(thermal),
        "clock_ghz": clock,
        "load1": round(os.getloadavg()[0], 2),
    }


def steady(now: dict, clock_min_ghz: float = CLOCK_MIN_GHZ) -> bool:
    return now["ac_power"] and now["thermal_pressure"] == 0 and now["clock_ghz"] >= clock_min_ghz


def wait(probe: Path) -> tuple[dict, float]:
    """Wait until the conditions before a run hold. Returns them and the seconds waited."""
    started = reported = time.monotonic()
    while True:
        now = read(probe)
        if steady(now) and now["load1"] < LOAD_LIMIT:
            return now, time.monotonic() - started
        if time.monotonic() - reported > 300:
            print(f"waiting: {now}", flush=True)
            reported = time.monotonic()
        time.sleep(5)


def clocks() -> tuple[float, float]:
    """CLOCK_MONOTONIC counts time asleep on macOS; CLOCK_UPTIME_RAW does not."""
    return time.clock_gettime(time.CLOCK_MONOTONIC), time.clock_gettime(time.CLOCK_UPTIME_RAW)


def disturbed(before_clocks: tuple[float, float], after_clocks: tuple[float, float], after: dict) -> tuple[bool, float]:
    """Whether a run was disturbed, and how long the computer slept during it, in seconds."""
    slept = (after_clocks[0] - before_clocks[0]) - (after_clocks[1] - before_clocks[1])
    return slept > SLEEP_LIMIT_S or not steady(after, END_CLOCK_MIN_GHZ), slept
