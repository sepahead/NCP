#!/usr/bin/env python3
"""Analyze the runs of the multi-agent benchmark (see PROTOCOL.md).

Usage: analyze.py RESULTS_DIR

Reads schedule.json, validity.json, and runs.jsonl, applies the decision rules of PROTOCOL.md,
section 10, and writes analysis.json and summary.md to RESULTS_DIR. Standard library only.

The final row of a block and configuration is its last attempt without an error (section 6:
the analysis uses the last attempt of a disturbed run). A final row that is still disturbed
after three attempts is reported and left out of the statistics. Rows with an error count
against R1 and M1, repeats included (section 10).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HOSTS = ("rust", "python")
SESSIONS = (1, 4, 16, 64, 256)
RANKS = (1, 2, 4, 8)


def measure(row: dict) -> float | None:
    stats = row["result"].get("round") or row["result"].get("call") or {}
    return stats.get("median_us")


def final_rows(rows: list[dict]) -> tuple[dict[tuple[int, str], dict], list[dict]]:
    """The final row of each (block, configuration), and the final rows left out because they
    were still disturbed after three attempts."""
    final: dict[tuple[int, str], dict] = {}
    for row in rows:
        if row["returncode"] == 0:
            final[(row["block"], row["config"])] = row  # later attempts replace earlier ones
    disturbed = [row for row in final.values() if row.get("disturbed")]
    for row in disturbed:
        del final[(row["block"], row["config"])]
    return final, disturbed


def main() -> None:
    results = Path(sys.argv[1])
    schedule = json.loads((results / "schedule.json").read_text())
    validity = json.loads((results / "validity.json").read_text())
    rows = [json.loads(line) for line in (results / "runs.jsonl").read_text().splitlines() if line.strip()]
    final, still_disturbed = final_rows(rows)

    configs: dict[str, dict] = {}
    for (block, name), row in sorted(final.items()):
        entry = configs.setdefault(
            name, {k: v for k, v in row.items() if k in ("part", "host", "mode", "n", "wait_us", "ranks", "spikes")}
        )
        entry.setdefault("blocks", {})[str(block)] = row
    for entry in configs.values():
        values = [measure(row) for row in entry["blocks"].values()]
        values = [v for v in values if v is not None]
        entry["measures_us"] = values
        if values:
            entry["statistic_us"] = statistics.median(values)
            entry["range_us"] = [min(values), max(values)]
            p95 = [
                row["result"].get("round", row["result"].get("call", {})).get("p95_us")
                for row in entry["blocks"].values()
            ]
            entry["p95_statistic_us"] = statistics.median([v for v in p95 if v is not None])

    def stat(name: str) -> float | None:
        return configs.get(name, {}).get("statistic_us")

    def f(host: str, mode: str, n: int, wait_us: int) -> float | None:
        return stat(f"F-{host}-{mode}-n{n}-w{wait_us}")

    hypotheses: dict[str, dict] = {}

    def decide(name: str, checks: list[tuple[str, bool | None]]) -> None:
        """A check of None needs a configuration without a result: the hypothesis does not hold."""
        hypotheses[name] = {
            "holds": all(result is True for _, result in checks),
            "checks": [{"check": text, "holds": result} for text, result in checks],
        }

    def below(a: float | None, b: float | None) -> bool | None:
        return None if a is None or b is None else a < b

    # F1
    decide(
        "F1", [(f"{h} all N=64 W=0 = {f(h, 'all', 64, 0)} < 1000", below(f(h, "all", 64, 0), 1000.0)) for h in HOSTS]
    )
    # F2
    checks = []
    for h in HOSTS:
        a, s = f(h, "all", 64, 1000), f(h, "sequential", 64, 1000)
        checks.append((f"{h} all {a} < 0.1 x sequential {s}", below(a, None if s is None else 0.1 * s)))
    decide("F2", checks)
    # F3
    checks = []
    for h in HOSTS:
        for n in (4, 16, 64, 256):
            for other in ("pool", "sequential"):
                a, b = f(h, "all", n, 0), f(h, other, n, 0)
                checks.append((f"{h} N={n}: all {a} < {other} {b}", below(a, b)))
    decide("F3", checks)
    # F4
    checks = []
    for h in HOSTS:
        a256, r256, a1, r1 = f(h, "all", 256, 0), f(h, "raw", 256, 0), f(h, "all", 1, 0), f(h, "raw", 1, 0)
        if None in (a256, r256, a1, r1):
            checks.append((f"{h}: a configuration has no result", None))
            continue
        per_session, single = (a256 - r256) / 256, a1 - r1
        checks.append(
            (
                f"{h}: (all - raw) / 256 at N=256 = {per_session:.2f} < (all - raw) at N=1 = {single:.2f}",
                per_session < single,
            )
        )
    decide("F4", checks)
    # F5
    rs, ra, ps, pa = (
        f("rust", "split", 256, 0),
        f("rust", "all", 256, 0),
        f("python", "split", 256, 0),
        f("python", "all", 256, 0),
    )
    decide("F5", [(f"rust split {rs} < all {ra}", below(rs, ra)), (f"python split {ps} > all {pa}", below(pa, ps))])

    # Part R
    r_rows = [row for row in rows if row["part"] == "R"]
    rounds_rows = [row for row in r_rows if row["mode"] == "rounds"]
    failed_rounds = [row for row in rounds_rows if row["returncode"] != 0]
    checks = [
        (f"{len(failed_rounds)} of {len(rounds_rows)} recorded rounds runs ended with an error", not failed_rounds)
    ]
    for n in SESSIONS:
        for block, row in sorted(configs.get(f"R-rounds-n{n}", {}).get("blocks", {}).items()):
            result = row["result"]
            total = result["rounds"] + result["warmup"]
            fine = (
                result.get("states_agree") is True
                and result.get("records_checked") == n * total
                and result.get("owner", {}).get("excluded") == []
            )
            checks.append(
                (
                    f"N={n} block {block}: states agree, {result.get('records_checked')} records checked, "
                    "none excluded",
                    fine,
                )
            )
    decide("R1", checks)
    checks = []
    for n in SESSIONS:
        blocks = configs.get(f"R-rounds-n{n}", {}).get("blocks", {})
        states = {row["result"].get("owner", {}).get("final_state") for row in blocks.values()}
        checks.append(
            (f"N={n}: {len(blocks)} runs, {len(states)} final state(s)", len(blocks) == 3 and len(states) == 1)
        )
        if n >= 4:
            for block, row in sorted(blocks.items()):
                owner = row["result"].get("owner", {})
                out, recorded = owner.get("rounds_out_of_member_order"), owner.get("rounds_recorded")
                ok = None if out is None or not recorded else out >= recorded / 2
                checks.append((f"N={n} block {block}: {out} of {recorded} rounds out of member order", ok))
    decide("R2", checks)
    checks = []
    for n in SESSIONS[1:]:
        blocks = configs.get(f"R-arrival-n{n}", {}).get("blocks", {})
        states = {row["result"].get("owner", {}).get("final_state") for row in blocks.values()}
        checks.append((f"N={n}: {len(blocks)} runs, {len(states)} final states", len(blocks) == 3 and len(states) >= 2))
    decide("R3", checks)
    checks = []
    for n in SESSIONS:
        rounds, arrival = stat(f"R-rounds-n{n}"), stat(f"R-arrival-n{n}")
        limit = 3.0 if n == 256 else 2.0
        if rounds is None or arrival is None:
            checks.append((f"N={n}: a configuration has no result", None))
        else:
            checks.append((f"N={n}: rounds / arrival = {rounds / arrival:.2f} <= {limit}", rounds / arrival <= limit))
    decide("R4", checks)
    decide("R5", [(f"rounds N=64 = {stat('R-rounds-n64')} < 5000", below(stat("R-rounds-n64"), 5000.0))])

    # Part M
    m_rows = [row for row in rows if row["part"] == "M"]
    failed_m = [row for row in m_rows if row["returncode"] != 0]
    decide("M1", [(f"{len(failed_m)} of {len(m_rows)} recorded runs of part M ended with an error", not failed_m)])
    checks = []
    for ranks in RANKS:
        for spikes in (0, 1788):
            a, b = stat(f"M-ranks{ranks}-spikes{spikes}"), stat(f"M-ranks0-spikes{spikes}")
            checks.append((f"R={ranks} S={spikes}: {a} - {b} <= 30", None if a is None or b is None else a - b <= 30.0))
    decide("M2", checks)
    checks = []
    base = stat("M-ranks0-spikes87381")
    for ranks in RANKS:
        a = stat(f"M-ranks{ranks}-spikes87381")
        checks.append((f"R={ranks}: {a} <= 1.2 x {base}", None if a is None or base is None else a <= 1.2 * base))
    decide("M3", checks)

    # Exploratory: what NCP 2 adds per session, and from which N split is faster than all.
    exploratory: dict = {"added_per_session_us": {}, "split_faster_than_all": {}}
    for h in HOSTS:
        for w in (0, 1000):
            for n in SESSIONS:
                a, r = f(h, "all", n, w), f(h, "raw", n, w)
                if a is not None and r is not None:
                    exploratory["added_per_session_us"][f"{h}-w{w}-n{n}"] = round((a - r) / n, 3)
                s = f(h, "split", n, w)
                if a is not None and s is not None:
                    exploratory["split_faster_than_all"][f"{h}-w{w}-n{n}"] = s < a

    finished = [row["finished_utc"] for row in rows]
    analysis = {
        "context": {
            "protocol": schedule["protocol"],
            "protocol_sha256": schedule["protocol_sha256"],
            "commit": schedule["commit"],
            "worktree_clean": schedule["worktree_clean"],
            "environment": validity["environment"],
            "validity": {k: v["returncode"] for k, v in validity.items() if k != "environment"},
            "runs_recorded": len(rows),
            "runs_scheduled": len(schedule["order"]),
            "failed_rows": [
                {"block": r["block"], "config": r["config"], "retry": r["retry"], "stderr_tail": r["stderr_tail"]}
                for r in rows
                if r["returncode"]
            ],
            "disturbed_attempts": sum(bool(r.get("disturbed")) for r in rows),
            "still_disturbed": [{"block": r["block"], "config": r["config"]} for r in still_disturbed],
            "missing": sorted(
                {f"{e['block']}:{e['config']}" for e in schedule["order"]} - {f"{b}:{c}" for (b, c) in final}
            ),
            "started_utc": min(r["started_utc"] for r in rows) if rows else None,
            "finished_utc": max(finished) if finished else None,
            "waited_s": round(sum(r.get("waited_s", 0) for r in rows), 1),
        },
        "configurations": {
            name: {k: v for k, v in entry.items() if k != "blocks"} | {"blocks": sorted(entry["blocks"])}
            for name, entry in sorted(configs.items())
        },
        "hypotheses": hypotheses,
        "exploratory": exploratory,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    (results / "summary.md").write_text(summary(analysis))
    for name, entry in hypotheses.items():
        print(f"{name}: {'holds' if entry['holds'] else 'does not hold'}")


def cell(entry: dict | None) -> str:
    if not entry or "statistic_us" not in entry:
        return "–"
    low, high = entry["range_us"]
    return f"{entry['statistic_us']:,.1f} ({low:,.1f}–{high:,.1f})"


def summary(analysis: dict) -> str:
    configs = analysis["configurations"]
    lines = ["# Multi-agent benchmark: summary", ""]
    context = analysis["context"]
    lines += [
        f"Protocol digest `{context['protocol_sha256'][:12]}`, NCP commit `{context['commit'][:7]}`, "
        f"clean worktree: {context['worktree_clean']}. Runs recorded: {context['runs_recorded']} of "
        f"{context['runs_scheduled']} scheduled; disturbed attempts: {context['disturbed_attempts']}; "
        f"failed rows: {len(context['failed_rows'])}; missing: {len(context['missing'])}.",
        "",
        "Medians of the block medians in µs, with the range of the block medians.",
        "",
    ]
    for wait_us in (0, 1000):
        lines += [f"## Part F, owners that wait {wait_us} µs", ""]
        for host in HOSTS:
            lines += [
                f"{host.capitalize()} host:",
                "",
                "| N | all | pool | split | sequential | raw |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            for n in SESSIONS:
                cells = [
                    cell(configs.get(f"F-{host}-{mode}-n{n}-w{wait_us}"))
                    for mode in ("all", "pool", "split", "sequential", "raw")
                ]
                lines.append(f"| {n} | " + " | ".join(cells) + " |")
            lines.append("")
    lines += ["## Part R", "", "| N | rounds | arrival | rounds / arrival |", "| --- | --- | --- | --- |"]
    for n in SESSIONS:
        r, a = configs.get(f"R-rounds-n{n}"), configs.get(f"R-arrival-n{n}")
        ratio = (
            f"{r['statistic_us'] / a['statistic_us']:.2f}"
            if r and a and "statistic_us" in r and "statistic_us" in a
            else "–"
        )
        lines.append(f"| {n} | {cell(r)} | {cell(a)} | {ratio} |")
    lines += ["", "## Part M", "", "| Ranks | 0 spikes | 1788 spikes | 87381 spikes |", "| --- | --- | --- | --- |"]
    for ranks in (0, 1, 2, 4, 8):
        label = "no MPI" if ranks == 0 else str(ranks)
        cells = [cell(configs.get(f"M-ranks{ranks}-spikes{s}")) for s in (0, 1788, 87381)]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Hypotheses", "", "| # | Holds | Checks |", "| --- | --- | --- |"]
    for name, entry in analysis["hypotheses"].items():
        failed = [c["check"] for c in entry["checks"] if c["holds"] is not True]
        detail = "all checks hold" if not failed else "fails: " + "; ".join(failed)
        lines.append(f"| {name} | {'yes' if entry['holds'] else 'no'} | {detail} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
