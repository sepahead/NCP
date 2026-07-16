#!/usr/bin/env python3
"""Generate the reviewed Markdown views of the NCP 1.0 task ledger."""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from check_implementation_ledger import (
    INDEPENDENT_REVIEWER_MINIMUM,
    LEDGER,
    REQUIRED_EXTERNAL_GATES,
    ROOT,
    LedgerError,
    _task_reached_minimum,
    load,
)


LEDGER_VIEW = ROOT / "docs" / "implementation" / "NCP_1_0_TASK_LEDGER.md"
RESUMPTION_VIEW = ROOT / "docs" / "implementation" / "NCP_1_0_RESUMPTION.md"


def _cell(value: object) -> str:
    text = str(value).replace("\n", " ")
    for character in ("\\", "`", "*", "_", "[", "]", "|"):
        text = text.replace(character, f"\\{character}")
    return html.escape(text, quote=False)


def _short(commit: str | None) -> str:
    return commit[:12] if commit else "—"


def _next_tasks(data: dict[str, object]) -> list[str]:
    tasks = data["tasks"]
    assert isinstance(tasks, list)
    by_id = {task["id"]: task for task in tasks}
    return [
        task["id"]
        for task in tasks
        if task["status"] == "OPEN"
        and all(
            by_id[dependency]["status"]
            in {"LOCAL_PASS", "EXTERNAL_PASS", "INDEPENDENT_PASS", "COMPLETE"}
            and _task_reached_minimum(by_id[dependency])
            for dependency in task["dependencies"]
        )
    ]


def render_ledger(data: dict[str, object]) -> str:
    tasks = data["tasks"]
    repositories = data["repositories"]
    perspectives = data["perspective_mapping"]
    lenses = data["lens_mapping"]
    assert isinstance(tasks, list)
    assert isinstance(repositories, list)
    assert isinstance(perspectives, list)
    assert isinstance(lenses, list)
    counts = {
        status: sum(task["status"] == status for task in tasks)
        for status in (
            "OPEN",
            "IN_PROGRESS",
            "BLOCKED",
            "LOCAL_PASS",
            "EXTERNAL_PASS",
            "INDEPENDENT_PASS",
            "COMPLETE",
        )
    }
    active_tasks = [
        task for task in tasks if task["status"] in {"IN_PROGRESS", "BLOCKED"}
    ]
    active = [task["id"] for task in active_tasks]
    lines = [
        "# NCP 1.0 implementation task ledger",
        "",
        "> **Generated file — do not edit.** Edit",
        "> [`task-ledger.v1.json`](../../evidence/implementation/task-ledger.v1.json), run",
        "> `python3 scripts/generate_implementation_ledger.py --write`, then run the checker.",
        "> This is evidence bookkeeping, not release authorization or certification.",
        "",
        f"Blueprint SHA-256: `{data['blueprint']['sha256']}`.",
        "",
        f"Can this ledger grant release authorization? **{str(data['ledger_grants_release_authorization']).lower()}**.",
        "",
        "## Current decision",
        "",
        "The candidate remains **NO_GO**. A local pass means only that a bounded",
        "repository-local acceptance slice passed. External and independent obligations remain",
        "separate, and publication tasks cannot start through a status edit.",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| `{status}` | {count} |" for status, count in counts.items())
    lines.extend(
        [
            "",
            f"Active tasks: {', '.join(f'`{task}`' for task in active) if active else 'none'}.",
            "",
            f"Dependency-ready open tasks: {', '.join(f'`{task}`' for task in _next_tasks(data)) or 'none'}.",
        ]
    )
    if active_tasks:
        lines.extend(["", "## Active task recovery checkpoints"])
        for task in active_tasks:
            checkpoint = task["reviewer_comment"] or (
                "No detailed checkpoint is recorded; inspect the task transition history and "
                "repository status before resuming."
            )
            lines.extend(
                [
                    "",
                    f"### `{task['id']}` — {task['title']}",
                    "",
                    checkpoint,
                    "",
                    "Current residual risks:",
                    "",
                ]
            )
            lines.extend(f"- {risk}" for risk in task["residual_risks"])
    lines.extend(
        [
            "",
            "## Three required review perspectives",
            "",
            "| ID | Perspective | Blueprint lenses | Required question |",
            "|---|---|---|---|",
        ]
    )
    for perspective in perspectives:
        lines.append(
            f"| `{_cell(perspective['id'])}` | {_cell(perspective['name'])} | "
            f"{', '.join(f'`{lens}`' for lens in perspective['lens_ids'])} | "
            f"{_cell(perspective['required_question'])} |"
        )
    lines.extend(
        [
            "",
            "Every task must also pass all ten blueprint lenses. `NOT_APPLICABLE` requires a",
            "specific rationale and reviewer; it is not an omitted review.",
            "",
            "## Evidence floors and checked gate names",
            "",
            "`LOCAL` is bounded repository evidence only. `EXTERNAL` additionally requires the",
            "checked live/owner/platform gate names below. `INDEPENDENT` additionally requires",
            "the checked number of distinct non-owner reviewer identities. Reopening a passing",
            "task starts a new evidence generation; evidence from an older generation does not",
            "satisfy the floor.",
            "",
            "| External-floor task | Required checked gate ID |",
            "|---|---|",
        ]
    )
    for task_id, gate_ids in REQUIRED_EXTERNAL_GATES.items():
        lines.append(f"| `{task_id}` | {', '.join(f'`{gate}`' for gate in gate_ids)} |")
    lines.extend(
        [
            "",
            "| Independent-floor task | Minimum distinct independent identities |",
            "|---|---:|",
        ]
    )
    for task_id, minimum in INDEPENDENT_REVIEWER_MINIMUM.items():
        lines.append(f"| `{task_id}` | {minimum} |")
    lines.extend(
        [
            "",
            "## Intake repository snapshot",
            "",
            "| Repository | Branch | HEAD | Tree | Dirty paths | Intake disposition |",
            "|---|---|---|---|---:|---|",
        ]
    )
    for repository in repositories:
        lines.append(
            f"| {_cell(repository['name'])} | `{_cell(repository['branch'])}` | "
            f"`{_short(repository['head'])}` | `{_short(repository['tree'])}` | "
            f"{repository['changed_paths']} | {_cell(repository['intake_disposition'])} |"
        )
    lines.extend(
        [
            "",
            "## Ten-lens mapping to the prior twenty-lens review",
            "",
            "| Lens | Name | Prior lenses | Stricter rule |",
            "|---|---|---|---|",
        ]
    )
    for lens in lenses:
        lines.append(
            f"| `{lens['id']}` | {_cell(lens['name'])} | "
            f"{', '.join(f'`{old}`' for old in lens['max_effort_lenses'])} | "
            f"{_cell(lens['stricter_rule'])} |"
        )
    lines.extend(
        [
            "",
            "## Dependency-ordered tasks",
            "",
            "| Task | Status | Claim tier | Required evidence class | Scope | Dependencies | Repository | Source commit | Residual risks |",
            "|---|---|---|---|---|---|---|---|---:|",
        ]
    )
    for task in tasks:
        dependencies = (
            ", ".join(f"`{dependency}`" for dependency in task["dependencies"]) or "—"
        )
        lines.append(
            f"| `{task['id']}` | `{task['status']}` | `{task['claim_tier']}` | "
            f"`{task['minimum_terminal_class']}` | {_cell(task['title'])} | "
            f"{dependencies} | {_cell(task['repository'])} | `{_short(task['source_commit'])}` | "
            f"{len(task['residual_risks'])} |"
        )
    lines.extend(
        [
            "",
            "## Status-change receipts",
            "",
            "| Task | From | To | Timestamp (UTC) | Correlation ID | Receipt |",
            "|---|---|---|---|---|---|",
        ]
    )
    found_transition = False
    for task in tasks:
        for transition in task["transitions"]:
            found_transition = True
            receipt = transition["receipt"]
            if receipt is None:
                receipt_text = "initial start; receipt not required"
            elif receipt["kind"] == "coordination":
                receipt_text = (
                    f"coordination receipt at `{_short(receipt['source_commit'])}`"
                )
            else:
                receipt_text = (
                    f"passing receipt for commit `{_short(receipt['commit'])}`"
                )
            lines.append(
                f"| `{task['id']}` | `{transition['from']}` | `{transition['to']}` | "
                f"`{transition['timestamp_utc']}` | `{_cell(transition['correlation_id'])}` | {receipt_text} |"
            )
    if not found_transition:
        lines.append("| — | — | — | — | — | no transitions recorded |")
    lines.extend(
        [
            "",
            "## Update and verification",
            "",
            "```bash",
            "python3 scripts/check_implementation_ledger.py --self-test",
            "python3 scripts/generate_implementation_ledger.py --check",
            "scripts/check.sh",
            "```",
            "",
            "Raw logs referenced by future receipts must be bounded, repository-relative, and",
            "content-addressed. Credentials, private keys, absolute workstation paths, mutable",
            "source refs, missing outputs, unexplained skips, and self-review cannot be evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def render_resumption(data: dict[str, object]) -> str:
    tasks = data["tasks"]
    repositories = data["repositories"]
    assert isinstance(tasks, list)
    assert isinstance(repositories, list)
    active = [task for task in tasks if task["status"] in {"IN_PROGRESS", "BLOCKED"}]
    dirty = [repository for repository in repositories if repository["dirty"]]
    next_tasks = _next_tasks(data)
    lines = [
        "# Mandatory NCP 1.0 agent resumption brief",
        "",
        "> **STOP: every agent working on NCP or an NCP consumer must read this entire file,**",
        "> the linked live ledger, the blueprint, and that repository's instructions before",
        "> resuming. This generated brief records coordination state; it is not authority to",
        "> tag, publish, certify, rewrite another agent's changes, or clear an external gate.",
        "",
        "## What the prior work actually established",
        "",
        "The prior pass produced a deep, implementation-grade audit and dependency DAG. It",
        "did **not** implement the 17 identified architectural defects, migrate the consumers,",
        "or make NCP 1.0 releasable. Treating blueprint completion as product completion was the",
        "central imperfection. The live ledger now makes that distinction executable.",
        "",
        "The candidate remains unreleased and **NO_GO**. The immutable `v0.8.0` release is a",
        "different wire. No local test, copied mirror, branch pin, model review, or generated",
        "document can substitute for installed-peer, live security, physical-boundary,",
        "independent-review, clean-room, signing, publication, or consumer-role evidence.",
        "",
        "## Mandatory reading order",
        "",
        "1. The repository's `AGENTS.md` and any scoped nested instructions.",
        "2. [`NCP_1_0_TASK_LEDGER.md`](NCP_1_0_TASK_LEDGER.md) and its JSON source.",
        "3. [`NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md`](../handoff/NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md).",
        "4. NCP `README.md`, `NEURO_CYBERNETIC_PROTOCOL.md`, `docs/1.0-scope.md`,",
        "   `SECURITY.md`, and `RELEASE_READINESS.md` before a protocol-facing change.",
        "5. The target consumer's owning runtime, security, scientific, and integration docs.",
        "",
        "## Provisional topology boundary — ratify ADR-011 before code",
        "",
        "- NCP is a project-neutral protocol/provider, not an application orchestrator and not",
        "  a dependency on any consumer application.",
        "- Crebain remains standalone and is the sole plant body/actuator authority when its",
        "  optional NCP adapter is enabled. It issues epochs, leases and dispositions.",
        "- Engram's simulation responder and plant commander are separate optional roles with",
        "  disjoint types, principals, manifests, endpoints and state. Simulation grants never",
        "  satisfy plant authority.",
        "- Direct Engram command and Haldir-gated command are mutually exclusive for one",
        "  plant/session term. In gated mode Engram sends a Haldir-local signed intent; Haldir",
        "  creates a new NCP command under its own principal and obtains Crebain's lease.",
        "- Galadriel's NCP observer is read-only. A separate default-off registered assessor",
        "  extension may push only record-only or deny-tightening evidence to Haldir under a",
        "  distinct principal. It can remove permission, never grant it or actuate.",
        "- Prisoma is a workspace-excluded read-only capture/offline-analysis consumer and is",
        "  never in the control path. Missing evidence is recorded, never interpolated.",
        "- pid-rs remains a protocol-neutral leaf library. Galadriel/Prisoma may depend on it",
        "  through exact optional consumer-owned adapters; pid-rs never depends on NCP or an",
        "  application, and no PID result/log grants identity, capability or authority.",
        "",
        "The complete build/start/runtime/trust matrix, orthogonal deployment state, handover",
        "sequence, monotonicity proof and failure campaign are in blueprint section 7.15. This",
        "boundary is proposed design input, not accepted protocol or implementation evidence.",
        "",
        "## Current coordination state",
        "",
        f"Blueprint SHA-256: `{data['blueprint']['sha256']}`.",
        "",
        f"Can this ledger grant release authorization? **{str(data['ledger_grants_release_authorization']).lower()}**.",
        "",
        "| Task | State | Repository | Resume condition |",
        "|---|---|---|---|",
    ]
    if active:
        for task in active:
            lines.append(
                f"| `{task['id']}` | `{task['status']}` | {_cell(task['repository'])} | "
                f"{_cell(task['rollback_or_recovery'])} |"
            )
    else:
        lines.append(
            "| — | no active or blocked task | — | start only a dependency-ready task |"
        )
    if active:
        lines.extend(["", "### Active recovery checkpoint"])
        for task in active:
            checkpoint = task["reviewer_comment"] or (
                "No detailed checkpoint is recorded; inspect the task transition history and "
                "repository status before resuming."
            )
            lines.extend(
                [
                    "",
                    f"#### `{task['id']}` — {task['title']}",
                    "",
                    checkpoint,
                    "",
                    "Current residual risks:",
                    "",
                ]
            )
            lines.extend(f"- {risk}" for risk in task["residual_risks"])
    lines.extend(
        [
            "",
            f"Dependency-ready open tasks: {', '.join(f'`{task}`' for task in next_tasks) or 'none'}.",
            "",
            "Do not start a descendant merely because its files are convenient. Provider changes",
            "land and pass first; consumers then bind exact immutable provider commits. Cross-repo",
            "work is never one atomic Git transaction.",
            "",
            "## Preserved stopped-agent state",
            "",
            "| Repository | Branch | HEAD | Dirty paths | Required handling |",
            "|---|---|---|---:|---|",
        ]
    )
    for repository in repositories:
        handling = repository["intake_disposition"]
        lines.append(
            f"| {_cell(repository['name'])} | `{_cell(repository['branch'])}` | "
            f"`{repository['head']}` | {repository['changed_paths']} | {_cell(handling)} |"
        )
    if dirty:
        lines.extend(
            [
                "",
                "Dirty repositories are inherited work. Do not stash, reset, clean, bulk-format,",
                "checkout over, or stage unrelated paths. Re-inventory immediately before editing",
                "because this table is an intake snapshot, not a lock.",
            ]
        )
    lines.extend(
        [
            "",
            "## Three perspectives required for every change",
            "",
            "1. **Protocol/security correctness:** exact semantics, verified actor, authority,",
            "   session/stream fencing, fail-closed unknowns, bounded parsing, and plant hazards.",
            "2. **Consumer/runtime usability:** independent implementation, hard-to-misuse APIs,",
            "   migration, recovery, observability, backpressure, packaging, and operator workflow.",
            "3. **Operational/scientific evidence:** honest simulation/PID/calibration boundaries,",
            "   reproducible tests, independent review, retained artifacts, lifecycle ownership,",
            "   and explicit `NOT_RUN` external gates.",
            "",
            "These perspectives summarize—not replace—the blueprint's mandatory ten-lens review.",
            "",
            "## Required resume sequence",
            "",
            "1. Fetch remote state read-only and re-record branch, HEAD, tree, status, submodules,",
            "   toolchain, and ownership instructions for every repository in scope.",
            "2. Run the ledger self-test and generated-view check before changing status.",
            "3. Add a characterization/negative test before a new accept path and a positive test",
            "   before a new fail-closed path where practical.",
            "4. Change sources and generators; never hand-edit generated schemas, bindings,",
            "   manifests, mirrors, diagrams, plots, or baselines.",
            "5. Run focused gates, inspect the whole diff, then run each repository's complete",
            "   applicable gate. A skip or missing tool is not a pass.",
            "6. Retain structured tool versions and bounded command-output artifacts; every",
            "   passing command and remote-ref verification must name a content-checked artifact.",
            "7. Commit one coherent passing slice with a professional message, push immediately,",
            "   verify the remote object, then add its exact receipt and regenerate this brief.",
            "8. Stop on ambiguity, counterexamples, unsafe downgrade, private forks, dirty-file",
            "   overlap, irreproducible generation, or rollback failure. Record the blocker.",
            "",
            "## Commands before handoff",
            "",
            "```bash",
            "python3 scripts/check_implementation_ledger.py --self-test",
            "python3 scripts/generate_implementation_ledger.py --check",
            "python3 scripts/check_markdown_links.py",
            "scripts/check.sh",
            "```",
            "",
            "The final handoff must state exactly what is locally established, externally",
            "established, independently reproduced, blocked, and not run. Never call NCP perfect,",
            "eternal, production-safe, physically certified, or scientifically validated.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_or_check(path: Path, content: str, *, write: bool) -> None:
    encoded = content.encode("utf-8")
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded)
        print(f"WROTE {path.relative_to(ROOT)}")
        return
    try:
        current = path.read_bytes()
    except FileNotFoundError as error:
        raise LedgerError(
            f"generated view is missing: {path.relative_to(ROOT)}"
        ) from error
    if current != encoded:
        raise LedgerError(
            f"generated view is stale: {path.relative_to(ROOT)}; run "
            "python3 scripts/generate_implementation_ledger.py --write"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        data = load(LEDGER)
        _write_or_check(LEDGER_VIEW, render_ledger(data), write=args.write)
        _write_or_check(RESUMPTION_VIEW, render_resumption(data), write=args.write)
        if not args.write:
            print("OK generated implementation ledger and mandatory resumption brief")
        return 0
    except (OSError, LedgerError) as error:
        print(f"ERROR implementation ledger generation: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
