#!/usr/bin/env python3
"""Record the computer and software that the NEST benchmarks ran on.

Writes environment.json and one conda explicit package list per environment into
this directory. The record names the hardware, operating system, power state,
compiler toolchain, MPI, MUSIC, NEST build and every conda package with its build
string and MD5 digest. It leaves out serial numbers, hardware UUIDs, user names and
home-directory paths: an environment prefix is written as <env:NAME>.

Run it on the benchmark computer, with the environments that the runs used:

    python3 capture_environment.py --env nest-3.10.0=/path/to/env \\
        [--env nest-3.9.0-control=/path/to/other/env]

macOS only (system_profiler, sysctl, pmset, xcrun). Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
HIDDEN = re.compile(r"serial|uuid|provisioning|activation|user name|computer name|host name", re.I)


def out(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip()


def profiler(data_type: str) -> dict[str, str]:
    """Return the 'Key: value' lines of one system_profiler section, without identifiers."""
    fields = {}
    for line in out(["system_profiler", data_type]).splitlines():
        key, sep, value = line.strip().partition(": ")
        if sep and value and not HIDDEN.search(key):
            fields.setdefault(key, value)
    return fields


def sysctl(name: str) -> str:
    return out(["sysctl", "-n", name])


def environment(name: str, prefix: Path) -> dict:
    py = str(prefix / "bin" / "python")
    probe = (
        "import json, sys, numpy, nest\n"
        "b = getattr(nest, 'build_info', None) or {}\n"
        "print(json.dumps({'python': sys.version.split()[0], 'numpy': numpy.__version__,\n"
        "  'nest': nest.__version__,\n"
        "  'build_info': {k: b[k] for k in ('have_mpi', 'have_music', 'threads_model') if k in b}}))\n"
    )
    nest = json.loads(out(["env", "PYNEST_QUIET=1", py, "-c", probe]).splitlines()[-1])
    explicit = out(["conda", "list", "--explicit", "--md5", "-p", str(prefix)])
    explicit = explicit.replace(str(prefix), f"<env:{name}>") + "\n"
    lock = HERE / f"{name}.conda-explicit.txt"
    lock.write_text(explicit)
    music = prefix / "bin" / "music"
    return {
        "prefix": f"<env:{name}>",
        **nest,
        "mpi": out([str(prefix / "bin" / "mpiexec"), "--version"]).splitlines()[0],
        "music": out([str(music), "--version"]).splitlines()[0] if music.exists() else None,
        "cmake": (out([str(prefix / "bin" / "cmake"), "--version"]).splitlines() or [None])[0],
        "conda_packages": sum(1 for line in explicit.splitlines() if line.startswith(("http", "file"))),
        "conda_explicit_list": lock.name,
        "conda_explicit_list_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", action="append", default=[], metavar="NAME=PREFIX")
    args = parser.parse_args()
    hardware = profiler("SPHardwareDataType")
    software = profiler("SPSoftwareDataType")
    gpu = profiler("SPDisplaysDataType")
    batt = out(["pmset", "-g", "batt"]).splitlines()
    record = {
        "schema": "sepahead.benchmark-environment.v1",
        "captured_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "computer": {
            "model_name": hardware.get("Model Name"),
            "model_identifier": hardware.get("Model Identifier"),
            "model_number": hardware.get("Model Number"),
            "system_firmware": hardware.get("System Firmware Version"),
            "chip": hardware.get("Chip"),
            "cpu_cores": hardware.get("Total Number of Cores"),
            "performance_cores": int(sysctl("hw.perflevel0.physicalcpu")),
            "efficiency_cores": int(sysctl("hw.perflevel1.physicalcpu")),
            "l2_cache_bytes_per_performance_cluster": int(sysctl("hw.perflevel0.l2cachesize")),
            "l2_cache_bytes_efficiency_cluster": int(sysctl("hw.perflevel1.l2cachesize")),
            "cache_line_bytes": int(sysctl("hw.cachelinesize")),
            "page_bytes": int(sysctl("hw.pagesize")),
            "gpu": gpu.get("Chipset Model"),
            "gpu_cores": gpu.get("Total Number of Cores"),
            "metal": gpu.get("Metal Support"),
            "memory": hardware.get("Memory"),
            "memory_bytes": int(sysctl("hw.memsize")),
            "storage": out(["diskutil", "info", "/"]).split("Disk Size:")[1].split("(")[0].strip(),
            "file_system": "APFS" if "APFS" in out(["diskutil", "info", "/"]) else None,
        },
        "operating_system": {
            "system_version": software.get("System Version"),
            "kernel": software.get("Kernel Version"),
            "kernel_release": platform.version(),
            "system_integrity_protection": software.get("System Integrity Protection"),
        },
        "power_at_capture": {"source": batt[0] if batt else None,
                             "power_mode": out(["pmset", "-g"]).split("powermode")[-1].split()[0]
                             if "powermode" in out(["pmset", "-g"]) else None},
        "toolchain": {
            "xcode": " ".join(out(["xcodebuild", "-version"]).split()),
            "clang": out(["/usr/bin/clang", "--version"]).splitlines()[0],
            "macos_sdk": out(["xcrun", "--show-sdk-version"]),
        },
        "environments": {},
    }
    for item in args.env:
        name, _, prefix = item.partition("=")
        record["environments"][name] = environment(name, Path(prefix))
    (HERE / "environment.json").write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
