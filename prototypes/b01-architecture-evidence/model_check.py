#!/usr/bin/env python3
"""Bounded preliminary counterexample discovery for the proposed B01 ADRs.

This is deliberately not the canonical TLA+/Kani/refinement program.  It checks a
small, explicit abstraction and a mutation kill matrix so reviewers can challenge
the proposed handover and deny-lifecycle semantics before ratification.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

GENERATION_LABELS = ("g2", "g0", "g1")
GENERATION_RANK = {"g0": 0, "g1": 1, "g2": 2}
STREAM_LABELS = ("e2", "e0", "e1")
DIRECT = "DIRECT_ENGRAM"
GATED = "GATED_HALDIR"
ACTIVE = "ACTIVE"
TRANSFER = "HOLD_TRANSFER"
RESTART = "HOLD_RESTART"
EXPIRED = "HOLD_EXPIRED"
TRANSFER_NONE = "NONE"
TRANSFER_REQUESTED = "REQUESTED"
TRANSFER_QUIESCED = "QUIESCED"
TRANSFER_RETIRED = "RETIRED"
TRANSFER_TERM_PERSISTED = "TERM_PERSISTED"
TRANSFER_COMPLETE = "COMPLETE"
IN_PROGRESS_TRANSFER_PHASES = (
    TRANSFER_REQUESTED,
    TRANSFER_QUIESCED,
    TRANSFER_RETIRED,
    TRANSFER_TERM_PERSISTED,
)
ENGRAM = "engram"
HALDIR = "haldir"
V08_WIRE = "wire-0.8"
V10_WIRE = "wire-1.0"
V08_ACTIVE = "V08_ACTIVE"
CUTOVER_TO_V10 = "QUIESCING_TO_V10"
V10_ACTIVE = "V10_ACTIVE"
ROLLBACK_TO_V08 = "QUIESCING_TO_V08"
V08_ROLLBACK = "V08_ROLLBACK"
V08_INCARNATIONS = ("v08-i2", "v08-i0", "v08-i1")
V08_INCARNATION_RANK = {"v08-i0": 0, "v08-i1": 1, "v08-i2": 2}
V10_INCARNATIONS = ("v10-i1", "v10-i0")


class ModelError(RuntimeError):
    """One bounded model, invariant, non-vacuity, or coverage failure."""

    def __init__(self, message: str, trace: list[str]) -> None:
        super().__init__(message)
        self.trace = trace


@dataclass(frozen=True, order=True, slots=True)
class Command:
    command_id: int
    origin: str
    issuer: str
    domain: str
    term: int
    generation: str
    epoch: str


@dataclass(frozen=True, slots=True)
class CompositionState:
    phase: str = ACTIVE
    mode: str = DIRECT
    term: int = 0
    generation_step: int = 0
    stream_step: int = 0
    holders: tuple[str, ...] = (ENGRAM,)
    pending: tuple[Command, ...] = ()
    issued: int = 0
    applied: tuple[int, ...] = ()
    rejected: tuple[int, ...] = ()
    handover_done: bool = False
    transfer_phase: str = TRANSFER_NONE
    transfer_source: str | None = None
    transfer_target: str | None = None
    transfer_base_generation_step: int | None = None
    transfer_base_term: int | None = None
    transfer_base_stream_step: int | None = None

    @property
    def generation(self) -> str:
        return GENERATION_LABELS[self.generation_step]

    @property
    def epoch(self) -> str:
        return STREAM_LABELS[self.stream_step]

    @property
    def expected_holder(self) -> str:
        return ENGRAM if self.mode == DIRECT else HALDIR


@dataclass(frozen=True, slots=True)
class DenyState:
    local_allow: bool = True
    deny_active: bool = False
    qualified_profile_active: bool = False
    removal_requested: bool = False
    recovery_dwell_complete: bool = False
    policy_revision: int = 0
    blocked_attempt_seen: bool = False
    authenticated_widen_seen: bool = False

    @property
    def effective_allow(self) -> bool:
        return self.local_allow and not self.deny_active


@dataclass(frozen=True, order=True, slots=True)
class MigrationCommand:
    command_id: int
    origin: str
    wire: str
    incarnation: str


@dataclass(frozen=True, slots=True)
class MigrationState:
    phase: str = V08_ACTIVE
    deployment_term: int = 0
    v08_incarnation_step: int = 0
    v10_incarnation_step: int = 0
    v08_admission_open: bool = True
    v10_admission_open: bool = False
    cutover_quiesced: bool = False
    rollback_quiesced: bool = False
    pending: tuple[MigrationCommand, ...] = ()
    issued: int = 0
    applied: tuple[int, ...] = ()
    rejected: tuple[int, ...] = ()
    cutover_done: bool = False
    rollback_done: bool = False

    @property
    def v08_incarnation(self) -> str:
        return V08_INCARNATIONS[self.v08_incarnation_step]

    @property
    def v10_incarnation(self) -> str:
        return V10_INCARNATIONS[self.v10_incarnation_step]


@dataclass(frozen=True, slots=True)
class Edge:
    action: str
    next_state: Any
    metadata: dict[str, Any]


def _trace(
    parents: dict[Any, tuple[Any | None, str]],
    state: Any,
    action: str | None = None,
) -> list[str]:
    output: list[str] = []
    cursor: Any | None = state
    while cursor is not None:
        parent, incoming = parents[cursor]
        if incoming:
            output.append(incoming)
        cursor = parent
    output.reverse()
    if action is not None:
        output.append(action)
    return output


def _command(
    state: CompositionState,
    *,
    origin: str,
    issuer: str,
    domain: str = "plant",
    term: int | None = None,
    generation: str | None = None,
    epoch: str | None = None,
) -> Command:
    return Command(
        command_id=state.issued,
        origin=origin,
        issuer=issuer,
        domain=domain,
        term=state.term if term is None else term,
        generation=state.generation if generation is None else generation,
        epoch=state.epoch if epoch is None else epoch,
    )


def _append_command(state: CompositionState, command: Command) -> CompositionState:
    return replace(
        state,
        pending=tuple(sorted((*state.pending, command))),
        issued=state.issued + 1,
    )


def _spec_admits(state: CompositionState, command: Command) -> bool:
    return (
        state.phase == ACTIVE
        and command.domain == "plant"
        and command.term == state.term
        and command.generation == state.generation
        and command.epoch == state.epoch
        and command.issuer == state.expected_holder
        and command.issuer in state.holders
        and len(state.holders) == 1
    )


def _implementation_admits(
    state: CompositionState,
    command: Command,
    mutation: str | None,
) -> bool:
    if mutation == "omit_generation":
        generation_ok = True
    elif mutation == "ordered_generation":
        generation_ok = (
            GENERATION_RANK[command.generation] >= GENERATION_RANK[state.generation]
        )
    else:
        generation_ok = command.generation == state.generation
    return (
        state.phase == ACTIVE
        and (mutation == "simulation_as_plant" or command.domain == "plant")
        and (mutation == "omit_term" or command.term == state.term)
        and generation_ok
        and (mutation == "omit_epoch" or command.epoch == state.epoch)
        and (
            mutation == "omit_holder"
            or (
                command.issuer == state.expected_holder
                and command.issuer in state.holders
                and len(state.holders) == 1
            )
        )
    )


def _opposite_holder(holder: str) -> str:
    return HALDIR if holder == ENGRAM else ENGRAM


def _holder_mode(holder: str) -> str:
    return DIRECT if holder == ENGRAM else GATED


def _begin_transfer(state: CompositionState) -> CompositionState:
    source = state.expected_holder
    return replace(
        state,
        phase=TRANSFER,
        holders=(),
        transfer_phase=TRANSFER_REQUESTED,
        transfer_source=source,
        transfer_target=_opposite_holder(source),
        transfer_base_generation_step=state.generation_step,
        transfer_base_term=state.term,
        transfer_base_stream_step=state.stream_step,
    )


def _complete_transfer(
    state: CompositionState,
    *,
    holder: str | None = None,
    overlap: bool = False,
) -> CompositionState:
    target = state.transfer_target
    source = state.transfer_source
    if target is None or source is None:
        raise ModelError("transfer completion lacks durable source or target", [])
    completed_holder = target if holder is None else holder
    holders = (
        tuple(sorted((source, completed_holder))) if overlap else (completed_holder,)
    )
    return replace(
        state,
        phase=ACTIVE,
        mode=_holder_mode(completed_holder),
        stream_step=state.stream_step + 1,
        holders=holders,
        handover_done=True,
        transfer_phase=TRANSFER_COMPLETE,
    )


def _mutated_restart(
    state: CompositionState,
    mutation: str | None,
) -> CompositionState:
    target = replace(
        state,
        phase=RESTART,
        generation_step=(
            state.generation_step
            if state.transfer_phase in IN_PROGRESS_TRANSFER_PHASES
            else state.generation_step + 1
        ),
        holders=(),
    )
    if mutation == "restart_loses_requested_latch" and (
        state.transfer_phase == TRANSFER_REQUESTED
    ):
        return replace(
            target,
            transfer_phase=TRANSFER_NONE,
            transfer_source=None,
            transfer_target=None,
            transfer_base_generation_step=None,
            transfer_base_term=None,
            transfer_base_stream_step=None,
        )
    if mutation == "restart_loses_quiesced_latch" and (
        state.transfer_phase == TRANSFER_QUIESCED
    ):
        return replace(target, transfer_phase=TRANSFER_REQUESTED)
    if mutation == "restart_loses_retired_latch" and (
        state.transfer_phase == TRANSFER_RETIRED
    ):
        return replace(target, transfer_phase=TRANSFER_QUIESCED)
    if mutation == "restart_loses_term_persisted_latch" and (
        state.transfer_phase == TRANSFER_TERM_PERSISTED
    ):
        return replace(
            target,
            term=state.transfer_base_term
            if state.transfer_base_term is not None
            else state.term,
            transfer_phase=TRANSFER_RETIRED,
        )
    return target


def _composition_transition_error(
    state: CompositionState,
    edge: Edge,
) -> str | None:
    target = edge.next_state
    if edge.action == "begin_handover":
        if (
            state.phase != ACTIVE
            or state.transfer_phase != TRANSFER_NONE
            or target != _begin_transfer(state)
        ):
            return "handover request did not durably bind its exact source and target"
    elif edge.action == "quiesce_handover":
        if (
            state.phase != TRANSFER
            or state.transfer_phase != TRANSFER_REQUESTED
            or target != replace(state, transfer_phase=TRANSFER_QUIESCED)
        ):
            return "handover advanced without completing requested-phase quiescence"
    elif edge.action == "retire_handover":
        if (
            state.phase != TRANSFER
            or state.transfer_phase != TRANSFER_QUIESCED
            or target != replace(state, transfer_phase=TRANSFER_RETIRED)
        ):
            return "handover retired authority before exact quiescence"
    elif edge.action == "persist_handover_term":
        if (
            state.phase != TRANSFER
            or state.transfer_phase != TRANSFER_RETIRED
            or target
            != replace(
                state,
                term=state.term + 1,
                transfer_phase=TRANSFER_TERM_PERSISTED,
            )
        ):
            return "handover term was not persisted strictly after retirement"
    elif edge.action == "finish_handover":
        if (
            state.phase != TRANSFER
            or state.transfer_phase != TRANSFER_TERM_PERSISTED
            or target != _complete_transfer(state)
        ):
            return "handover completed prematurely or under the wrong holder"
    elif edge.action == "restart_body":
        expected = replace(
            state,
            phase=RESTART,
            generation_step=(
                state.generation_step
                if state.transfer_phase in IN_PROGRESS_TRANSFER_PHASES
                else state.generation_step + 1
            ),
            holders=(),
        )
        if target != expected:
            return "body restart lost or rolled back durable transfer state"
    elif edge.action == "resume_transfer":
        if (
            state.phase != RESTART
            or state.transfer_phase not in IN_PROGRESS_TRANSFER_PHASES
            or target != replace(state, phase=TRANSFER, holders=())
        ):
            return "body restart did not resume the exact latched transfer phase"
    elif edge.action == "recover_body":
        if (
            state.phase not in {RESTART, EXPIRED}
            or state.transfer_phase not in {TRANSFER_NONE, TRANSFER_COMPLETE}
            or target
            != replace(
                state,
                phase=ACTIVE,
                term=state.term + 1,
                stream_step=state.stream_step + 1,
                holders=(state.expected_holder,),
            )
        ):
            return "ordinary recovery reactivated authority during a latched transfer"
    return None


def _composition_edges(
    state: CompositionState,
    mutation: str | None,
) -> Iterable[Edge]:
    if state.issued < 2 and state.phase == ACTIVE:
        if state.mode == DIRECT:
            command = _command(
                state,
                origin="issue_direct",
                issuer=ENGRAM,
            )
            yield Edge(
                "issue_direct",
                _append_command(state, command),
                {"created": command},
            )
        else:
            command = _command(
                state,
                origin="issue_haldir",
                issuer=ENGRAM if mutation == "wrong_haldir_principal" else HALDIR,
            )
            yield Edge(
                "issue_haldir",
                _append_command(state, command),
                {"created": command},
            )

        command = _command(
            state,
            origin="inject_wrong_holder",
            issuer=HALDIR if state.expected_holder == ENGRAM else ENGRAM,
        )
        yield Edge(
            "inject_wrong_holder",
            _append_command(state, command),
            {"created": command},
        )
        command = _command(
            state,
            origin="inject_simulation",
            issuer=state.expected_holder,
            domain="simulation",
        )
        yield Edge(
            "inject_simulation",
            _append_command(state, command),
            {"created": command},
        )
        if state.term > 0:
            command = _command(
                state,
                origin="inject_wrong_term",
                issuer=state.expected_holder,
                term=state.term - 1,
            )
            yield Edge(
                "inject_wrong_term",
                _append_command(state, command),
                {"created": command},
            )
        if state.generation_step > 0:
            command = _command(
                state,
                origin="inject_wrong_generation",
                issuer=state.expected_holder,
                generation=GENERATION_LABELS[state.generation_step - 1],
            )
            yield Edge(
                "inject_wrong_generation",
                _append_command(state, command),
                {"created": command},
            )
        if state.stream_step > 0:
            command = _command(
                state,
                origin="inject_wrong_epoch",
                issuer=state.expected_holder,
                epoch=STREAM_LABELS[state.stream_step - 1],
            )
            yield Edge(
                "inject_wrong_epoch",
                _append_command(state, command),
                {"created": command},
            )

    if (
        state.phase == ACTIVE
        and not state.handover_done
        and state.transfer_phase == TRANSFER_NONE
        and state.term < 3
        and state.stream_step < len(STREAM_LABELS) - 1
    ):
        yield Edge(
            "begin_handover",
            _begin_transfer(state),
            {},
        )

    if state.phase == TRANSFER and state.transfer_phase == TRANSFER_REQUESTED:
        yield Edge(
            "quiesce_handover",
            replace(state, transfer_phase=TRANSFER_QUIESCED),
            {},
        )
    if state.phase == TRANSFER and state.transfer_phase == TRANSFER_QUIESCED:
        yield Edge(
            "retire_handover",
            replace(state, transfer_phase=TRANSFER_RETIRED),
            {},
        )
    if state.phase == TRANSFER and state.transfer_phase == TRANSFER_RETIRED:
        yield Edge(
            "persist_handover_term",
            replace(
                state,
                term=state.term + 1,
                transfer_phase=TRANSFER_TERM_PERSISTED,
            ),
            {},
        )
    if state.phase == TRANSFER and state.transfer_phase == TRANSFER_TERM_PERSISTED:
        completed_holder = (
            state.transfer_source
            if mutation == "complete_to_old_holder"
            else state.transfer_target
        )
        yield Edge(
            "finish_handover",
            _complete_transfer(
                state,
                holder=completed_holder,
                overlap=mutation == "overlap_handover",
            ),
            {},
        )

    premature_phase = {
        "complete_from_requested": TRANSFER_REQUESTED,
        "complete_from_quiesced": TRANSFER_QUIESCED,
        "complete_from_retired": TRANSFER_RETIRED,
    }.get(mutation)
    if state.phase == TRANSFER and state.transfer_phase == premature_phase:
        premature = state
        if state.transfer_base_term is not None:
            premature = replace(
                state,
                term=state.transfer_base_term + 1,
            )
        yield Edge(
            "finish_handover",
            _complete_transfer(premature),
            {},
        )

    if state.generation_step < len(GENERATION_LABELS) - 1:
        yield Edge(
            "restart_body",
            _mutated_restart(state, mutation),
            {},
        )

    if state.phase == RESTART and state.transfer_phase in IN_PROGRESS_TRANSFER_PHASES:
        yield Edge(
            "resume_transfer",
            replace(state, phase=TRANSFER, holders=()),
            {},
        )

    if (
        state.phase in {RESTART, EXPIRED}
        and state.transfer_phase in {TRANSFER_NONE, TRANSFER_COMPLETE}
        and state.term < 3
        and state.stream_step < len(STREAM_LABELS) - 1
    ):
        yield Edge(
            "recover_body",
            replace(
                state,
                phase=ACTIVE,
                term=state.term + 1,
                stream_step=state.stream_step + 1,
                holders=(state.expected_holder,),
            ),
            {},
        )

    if state.phase == ACTIVE and state.stream_step < len(STREAM_LABELS) - 1:
        yield Edge(
            "restart_stream",
            replace(state, stream_step=state.stream_step + 1),
            {},
        )

    if state.phase == ACTIVE:
        yield Edge(
            "expire_lease",
            replace(state, phase=EXPIRED, holders=()),
            {},
        )

    for command in state.pending:
        admitted = _implementation_admits(state, command, mutation)
        pending = tuple(item for item in state.pending if item != command)
        target = replace(
            state,
            pending=pending,
            applied=(
                tuple(sorted((*state.applied, command.command_id)))
                if admitted
                else state.applied
            ),
            rejected=(
                state.rejected
                if admitted
                else tuple(sorted((*state.rejected, command.command_id)))
            ),
        )
        yield Edge(
            f"deliver:{command.command_id}:{command.origin}",
            target,
            {
                "admitted": admitted,
                "spec_admitted": _spec_admits(state, command),
                "command": command,
                "pending_before": len(state.pending),
            },
        )


def _composition_invariant(state: CompositionState) -> str | None:
    transfer_fields = (
        state.transfer_source,
        state.transfer_target,
        state.transfer_base_generation_step,
        state.transfer_base_term,
        state.transfer_base_stream_step,
    )
    if state.transfer_phase == TRANSFER_NONE:
        if transfer_fields != (None, None, None, None, None) or state.handover_done:
            return "empty transfer state retained a latch or completion claim"
    elif state.transfer_phase in {
        *IN_PROGRESS_TRANSFER_PHASES,
        TRANSFER_COMPLETE,
    }:
        if (
            state.transfer_source not in {ENGRAM, HALDIR}
            or state.transfer_target not in {ENGRAM, HALDIR}
            or state.transfer_source == state.transfer_target
            or state.transfer_base_generation_step is None
            or state.transfer_base_term is None
            or state.transfer_base_stream_step is None
            or not 0 <= state.transfer_base_generation_step < len(GENERATION_LABELS)
            or state.transfer_base_term < 0
            or not 0 <= state.transfer_base_stream_step < len(STREAM_LABELS) - 1
        ):
            return "durable transfer latch has an invalid source, target, or base fence"
    else:
        return "transfer phase is unknown"
    if state.transfer_phase in IN_PROGRESS_TRANSFER_PHASES:
        expected_term = (
            state.transfer_base_term + 1
            if state.transfer_phase == TRANSFER_TERM_PERSISTED
            else state.transfer_base_term
        )
        if (
            state.phase not in {TRANSFER, RESTART}
            or state.expected_holder != state.transfer_source
            or state.generation_step != state.transfer_base_generation_step
            or state.term != expected_term
            or state.stream_step != state.transfer_base_stream_step
            or state.handover_done
        ):
            return "in-progress transfer lost its source, phase, or exact fences"
    if state.transfer_phase == TRANSFER_COMPLETE:
        if (
            state.phase == TRANSFER
            or state.expected_holder != state.transfer_target
            or state.term < state.transfer_base_term + 1
            or state.stream_step < state.transfer_base_stream_step + 1
            or not state.handover_done
        ):
            return (
                "completed transfer did not activate the exact target and higher term"
            )
    if state.phase == TRANSFER and (
        state.transfer_phase not in IN_PROGRESS_TRANSFER_PHASES
    ):
        return "transfer lifecycle has no in-progress durable phase"
    if len(state.holders) > 1:
        return "more than one live holder exists"
    if state.phase == ACTIVE and state.holders != (state.expected_holder,):
        return "active state lacks the exact mode holder"
    if state.phase != ACTIVE and state.holders:
        return "non-active state retained a live holder"
    if len(state.applied) != len(set(state.applied)):
        return "a command was applied more than once"
    if set(state.applied) & set(state.rejected):
        return "a command is both applied and rejected"
    for command in state.pending:
        if command.origin == "issue_haldir" and command.issuer != HALDIR:
            return "Haldir constructed a command under a non-Haldir principal"
    return None


def check_composition(mutation: str | None = None) -> dict[str, Any]:
    initial = CompositionState()
    parents: dict[CompositionState, tuple[CompositionState | None, str]] = {
        initial: (None, "")
    }
    depths = {initial: 0}
    queue: deque[CompositionState] = deque([initial])
    coverage: Counter[str] = Counter()
    witnesses: set[str] = set()
    transitions = 0
    while queue:
        state = queue.popleft()
        if len(parents) > 250_000:
            raise ModelError("composition state bound exceeded", _trace(parents, state))
        for edge in _composition_edges(state, mutation):
            transitions += 1
            action_class = edge.action.split(":", 1)[0]
            coverage[action_class] += 1
            transition_error = _composition_transition_error(state, edge)
            if transition_error is not None:
                raise ModelError(
                    transition_error,
                    _trace(parents, state, edge.action),
                )
            invariant = _composition_invariant(edge.next_state)
            if invariant is not None:
                raise ModelError(invariant, _trace(parents, state, edge.action))
            metadata = edge.metadata
            if "admitted" in metadata:
                command: Command = metadata["command"]
                if metadata["admitted"] and not metadata["spec_admitted"]:
                    raise ModelError(
                        f"hostile or stale command {command.origin} was admitted",
                        _trace(parents, state, edge.action),
                    )
                if metadata["spec_admitted"] and metadata["admitted"]:
                    witnesses.add("fresh_command_applied")
                if not metadata["spec_admitted"] and not metadata["admitted"]:
                    witnesses.add("hostile_or_stale_command_rejected")
                    other_pending = tuple(
                        item for item in state.pending if item != command
                    )
                    if command.origin in {"issue_direct", "issue_haldir"} and any(
                        _spec_admits(state, item) for item in other_pending
                    ):
                        witnesses.add(
                            "delayed_stale_rejected_while_fresh_command_pending"
                        )
                    if command.domain == "simulation":
                        witnesses.add("simulation_command_rejected")
                    if command.origin == "inject_wrong_generation":
                        witnesses.add("wrong_generation_rejected")
                    if command.origin == "inject_wrong_term":
                        witnesses.add("wrong_term_rejected")
                    if command.origin == "inject_wrong_epoch":
                        witnesses.add("wrong_epoch_rejected")
                    if command.origin == "inject_wrong_holder":
                        witnesses.add("wrong_holder_rejected")
            if len(edge.next_state.pending) == 2:
                witnesses.add("two_commands_in_flight")
            if edge.action == "finish_handover" and edge.next_state.mode == GATED:
                witnesses.add("direct_to_gated_handover_completed")
            if (
                edge.action == "restart_body"
                and state.phase == TRANSFER
                and state.transfer_phase in IN_PROGRESS_TRANSFER_PHASES
            ):
                witnesses.add(
                    f"restart_preserved_{state.transfer_phase.lower()}_transfer"
                )
            if (
                edge.action == "resume_transfer"
                and state.transfer_phase in IN_PROGRESS_TRANSFER_PHASES
            ):
                witnesses.add(
                    f"restart_resumed_{state.transfer_phase.lower()}_transfer"
                )
            if edge.action == "recover_body":
                witnesses.add("restart_or_expiry_recovered")
                if state.phase == RESTART and state.transfer_phase == TRANSFER_NONE:
                    witnesses.add("clean_restart_recovered_current_holder")
                if state.phase == RESTART and state.transfer_phase == TRANSFER_COMPLETE:
                    witnesses.add("completed_transfer_restart_recovered_current_holder")
            if edge.next_state not in parents:
                parents[edge.next_state] = (state, edge.action)
                depths[edge.next_state] = depths[state] + 1
                queue.append(edge.next_state)

    required_actions = {
        "issue_direct",
        "issue_haldir",
        "inject_wrong_holder",
        "inject_simulation",
        "inject_wrong_term",
        "inject_wrong_generation",
        "inject_wrong_epoch",
        "begin_handover",
        "quiesce_handover",
        "retire_handover",
        "persist_handover_term",
        "finish_handover",
        "restart_body",
        "resume_transfer",
        "recover_body",
        "restart_stream",
        "expire_lease",
        "deliver",
    }
    missing_actions = sorted(required_actions - set(coverage))
    if missing_actions:
        raise ModelError(
            f"composition actions were unreachable: {missing_actions}",
            [],
        )
    required_witnesses = {
        "fresh_command_applied",
        "hostile_or_stale_command_rejected",
        "delayed_stale_rejected_while_fresh_command_pending",
        "simulation_command_rejected",
        "wrong_generation_rejected",
        "wrong_term_rejected",
        "wrong_epoch_rejected",
        "wrong_holder_rejected",
        "two_commands_in_flight",
        "direct_to_gated_handover_completed",
        "restart_or_expiry_recovered",
        "restart_preserved_requested_transfer",
        "restart_resumed_requested_transfer",
        "restart_preserved_quiesced_transfer",
        "restart_resumed_quiesced_transfer",
        "restart_preserved_retired_transfer",
        "restart_resumed_retired_transfer",
        "restart_preserved_term_persisted_transfer",
        "restart_resumed_term_persisted_transfer",
        "clean_restart_recovered_current_holder",
        "completed_transfer_restart_recovered_current_holder",
    }
    missing_witnesses = sorted(required_witnesses - witnesses)
    if missing_witnesses:
        raise ModelError(
            f"composition non-vacuity witnesses were absent: {missing_witnesses}",
            [],
        )
    return {
        "states": len(parents),
        "transitions": transitions,
        "maximum_depth": max(depths.values()),
        "action_counts": dict(sorted(coverage.items())),
        "witnesses": sorted(witnesses),
    }


def _deny_edges(state: DenyState, mutation: str | None) -> Iterable[Edge]:
    if not state.qualified_profile_active and state.policy_revision < 2:
        yield Edge(
            "install_qualified_haldir_profile",
            replace(
                state,
                qualified_profile_active=True,
                policy_revision=state.policy_revision + 1,
            ),
            {
                "authenticated": True,
                "independent_profile_issuer": True,
                "qualification_valid": True,
            },
        )

    hostile_deny_attempts = (
        (
            "producer_requested_deny",
            "producer_request_applies",
            {
                "authenticated": True,
                "profile_authenticated": False,
                "independent_profile_issuer": True,
                "qualification_valid": True,
                "evidence_eligible": True,
                "causally_later": True,
            },
        ),
        (
            "assessor_profile_attempt",
            "assessor_profile_applies",
            {
                "authenticated": True,
                "profile_authenticated": True,
                "independent_profile_issuer": False,
                "qualification_valid": True,
                "evidence_eligible": True,
                "causally_later": True,
            },
        ),
        (
            "missing_qualification_attempt",
            "missing_qualification_applies",
            {
                "authenticated": True,
                "profile_authenticated": True,
                "independent_profile_issuer": True,
                "qualification_valid": False,
                "evidence_eligible": True,
                "causally_later": True,
            },
        ),
        (
            "ineligible_verdict_attempt",
            "ineligible_verdict_applies",
            {
                "authenticated": True,
                "profile_authenticated": True,
                "independent_profile_issuer": True,
                "qualification_valid": True,
                "evidence_eligible": False,
                "causally_later": True,
            },
        ),
        (
            "abstained_evidence_attempt",
            "abstention_applies",
            {
                "authenticated": True,
                "profile_authenticated": True,
                "independent_profile_issuer": True,
                "qualification_valid": True,
                "evidence_eligible": False,
                "causally_later": True,
            },
        ),
        (
            "same_causal_revision_attempt",
            "same_causal_revision_applies",
            {
                "authenticated": True,
                "profile_authenticated": True,
                "independent_profile_issuer": True,
                "qualification_valid": True,
                "evidence_eligible": True,
                "causally_later": False,
            },
        ),
        (
            "unauthenticated_deny_attempt",
            "unauthenticated_deny_applies",
            {
                "authenticated": False,
                "profile_authenticated": True,
                "independent_profile_issuer": True,
                "qualification_valid": True,
                "evidence_eligible": True,
                "causally_later": True,
            },
        ),
    )
    for action, mutant, metadata in hostile_deny_attempts:
        target = state
        if mutation == mutant and not state.deny_active:
            target = replace(state, deny_active=True)
        yield Edge(action, target, metadata)

    if state.qualified_profile_active and not state.deny_active:
        yield Edge(
            "apply_profile_admitted_deny",
            replace(
                state,
                deny_active=True,
                removal_requested=False,
                recovery_dwell_complete=False,
            ),
            {
                "authenticated": True,
                "profile_authenticated": True,
                "independent_profile_issuer": True,
                "qualification_valid": True,
                "evidence_eligible": True,
                "causally_later": True,
            },
        )

    record_target = state
    if mutation == "record_only_clears" and state.deny_active:
        record_target = replace(
            state,
            deny_active=False,
            removal_requested=False,
            recovery_dwell_complete=False,
        )
    yield Edge(
        "record_only",
        record_target,
        {"authenticated": False},
    )

    if state.deny_active:
        for action, mutant in (
            ("expire", "expiry_clears"),
            ("retract", "retraction_clears"),
            ("disable", "disable_clears"),
        ):
            target = (
                replace(
                    state,
                    deny_active=False,
                    removal_requested=False,
                    recovery_dwell_complete=False,
                )
                if mutation == mutant
                else replace(
                    state,
                    removal_requested=True,
                    recovery_dwell_complete=False,
                )
            )
            yield Edge(action, target, {"authenticated": False})

        target = (
            replace(
                state,
                deny_active=False,
                removal_requested=False,
                recovery_dwell_complete=False,
            )
            if mutation == "restart_drops"
            else state
        )
        yield Edge("restart", target, {"authenticated": False})

        target = (
            replace(
                state,
                deny_active=False,
                removal_requested=False,
                recovery_dwell_complete=False,
            )
            if mutation == "unauthenticated_clear"
            else replace(state, blocked_attempt_seen=True)
        )
        yield Edge("unauthenticated_clear", target, {"authenticated": False})

        if state.removal_requested and not state.recovery_dwell_complete:
            early_target = state
            if mutation == "recovery_dwell_bypass":
                early_target = replace(
                    state,
                    deny_active=False,
                    removal_requested=False,
                    recovery_dwell_complete=False,
                    policy_revision=state.policy_revision + 1,
                    authenticated_widen_seen=True,
                )
            yield Edge(
                "early_authenticated_recovery_attempt",
                early_target,
                {
                    "authenticated": True,
                    "recovery_dwell_complete": False,
                },
            )
            yield Edge(
                "complete_recovery_dwell",
                replace(state, recovery_dwell_complete=True),
                {"authenticated": True},
            )

        if (
            state.removal_requested
            and state.recovery_dwell_complete
            and state.policy_revision < 2
            and mutation != "authenticated_widen_disabled"
        ):
            yield Edge(
                "authenticated_widen",
                replace(
                    state,
                    deny_active=False,
                    removal_requested=False,
                    recovery_dwell_complete=False,
                    policy_revision=state.policy_revision + 1,
                    authenticated_widen_seen=True,
                ),
                {
                    "authenticated": True,
                    "recovery_dwell_complete": True,
                },
            )

    if state.local_allow:
        yield Edge(
            "base_policy_deny",
            replace(state, local_allow=False),
            {"authenticated": False},
        )
    else:
        if state.policy_revision < 2:
            yield Edge(
                "authenticated_base_widen",
                replace(
                    state,
                    local_allow=True,
                    policy_revision=state.policy_revision + 1,
                    authenticated_widen_seen=True,
                ),
                {"authenticated": True},
            )
        yield Edge(
            "unauthenticated_base_widen",
            replace(state, blocked_attempt_seen=True),
            {"authenticated": False},
        )

    assessor_target = state
    if mutation == "assessor_allows" and not state.local_allow:
        assessor_target = replace(state, local_allow=True)
    yield Edge("assessor_allow_attempt", assessor_target, {"authenticated": False})


def check_deny_lifecycle(mutation: str | None = None) -> dict[str, Any]:
    initial = DenyState()
    parents: dict[DenyState, tuple[DenyState | None, str]] = {initial: (None, "")}
    depths = {initial: 0}
    queue: deque[DenyState] = deque([initial])
    coverage: Counter[str] = Counter()
    witnesses: set[str] = set()
    transitions = 0
    while queue:
        state = queue.popleft()
        for edge in _deny_edges(state, mutation):
            transitions += 1
            coverage[edge.action] += 1
            before = state.effective_allow
            after = edge.next_state.effective_allow
            deny_activated = not state.deny_active and edge.next_state.deny_active
            if deny_activated and not all(
                edge.metadata.get(field) is True
                for field in (
                    "authenticated",
                    "profile_authenticated",
                    "independent_profile_issuer",
                    "qualification_valid",
                    "evidence_eligible",
                    "causally_later",
                )
            ):
                raise ModelError(
                    "raw producer evidence changed policy without exact independent "
                    "Haldir admission",
                    _trace(parents, state, edge.action),
                )
            if not before and after:
                authenticated = edge.metadata["authenticated"]
                if (
                    not authenticated
                    or edge.next_state.policy_revision <= state.policy_revision
                ):
                    raise ModelError(
                        "permission widened without an authenticated monotonic "
                        "policy transition",
                        _trace(parents, state, edge.action),
                    )
                if (
                    state.deny_active
                    and not edge.next_state.deny_active
                    and edge.metadata.get("recovery_dwell_complete") is not True
                ):
                    raise ModelError(
                        "applied deny widened before authenticated recovery dwell",
                        _trace(parents, state, edge.action),
                    )
            if (
                edge.action == "install_qualified_haldir_profile"
                and edge.next_state.qualified_profile_active
                and edge.next_state.policy_revision > state.policy_revision
            ):
                witnesses.add("independent_qualified_profile_installed")
            if (
                edge.action == "apply_profile_admitted_deny"
                and edge.next_state.deny_active
            ):
                witnesses.add("profile_admitted_deny_applied")
            if (
                edge.action
                in {
                    "producer_requested_deny",
                    "assessor_profile_attempt",
                    "missing_qualification_attempt",
                    "ineligible_verdict_attempt",
                    "abstained_evidence_attempt",
                    "same_causal_revision_attempt",
                    "unauthenticated_deny_attempt",
                }
                and edge.next_state == state
            ):
                witnesses.add(f"{edge.action}_blocked")
            if (
                edge.action in {"expire", "retract", "disable"}
                and edge.next_state.deny_active
                and edge.next_state.removal_requested
            ):
                witnesses.add(f"{edge.action}_remains_non_widening")
            if edge.action == "restart" and edge.next_state.deny_active:
                witnesses.add("restart_preserved_applied_deny")
            if (
                edge.action
                in {
                    "unauthenticated_clear",
                    "unauthenticated_base_widen",
                    "assessor_allow_attempt",
                }
                and edge.next_state == state
            ):
                witnesses.add("unauthenticated_widen_blocked")
            if edge.action == "authenticated_widen" and after:
                witnesses.add("authenticated_deny_removal_succeeded")
            if edge.action == "authenticated_base_widen" and after:
                witnesses.add("authenticated_base_widen_succeeded")
            if edge.action == "record_only" and edge.next_state == state:
                witnesses.add("record_only_is_identity")
            if (
                edge.action == "early_authenticated_recovery_attempt"
                and edge.next_state == state
            ):
                witnesses.add("early_recovery_blocked")
            if (
                edge.action == "complete_recovery_dwell"
                and edge.next_state.recovery_dwell_complete
            ):
                witnesses.add("recovery_dwell_completed")
            if edge.next_state not in parents:
                parents[edge.next_state] = (state, edge.action)
                depths[edge.next_state] = depths[state] + 1
                queue.append(edge.next_state)

    required_actions = {
        "install_qualified_haldir_profile",
        "apply_profile_admitted_deny",
        "producer_requested_deny",
        "assessor_profile_attempt",
        "missing_qualification_attempt",
        "ineligible_verdict_attempt",
        "abstained_evidence_attempt",
        "same_causal_revision_attempt",
        "unauthenticated_deny_attempt",
        "record_only",
        "expire",
        "retract",
        "disable",
        "restart",
        "unauthenticated_clear",
        "early_authenticated_recovery_attempt",
        "complete_recovery_dwell",
        "authenticated_widen",
        "base_policy_deny",
        "authenticated_base_widen",
        "unauthenticated_base_widen",
        "assessor_allow_attempt",
    }
    missing_actions = sorted(required_actions - set(coverage))
    if missing_actions:
        raise ModelError(f"deny actions were unreachable: {missing_actions}", [])
    required_witnesses = {
        "independent_qualified_profile_installed",
        "profile_admitted_deny_applied",
        "producer_requested_deny_blocked",
        "assessor_profile_attempt_blocked",
        "missing_qualification_attempt_blocked",
        "ineligible_verdict_attempt_blocked",
        "abstained_evidence_attempt_blocked",
        "same_causal_revision_attempt_blocked",
        "unauthenticated_deny_attempt_blocked",
        "expire_remains_non_widening",
        "retract_remains_non_widening",
        "disable_remains_non_widening",
        "restart_preserved_applied_deny",
        "unauthenticated_widen_blocked",
        "authenticated_deny_removal_succeeded",
        "authenticated_base_widen_succeeded",
        "record_only_is_identity",
        "early_recovery_blocked",
        "recovery_dwell_completed",
    }
    missing_witnesses = sorted(required_witnesses - witnesses)
    if missing_witnesses:
        raise ModelError(
            f"deny non-vacuity witnesses were absent: {missing_witnesses}",
            [],
        )
    return {
        "states": len(parents),
        "transitions": transitions,
        "maximum_depth": max(depths.values()),
        "action_counts": dict(sorted(coverage.items())),
        "witnesses": sorted(witnesses),
    }


def _migration_command(
    state: MigrationState,
    *,
    origin: str,
    wire: str,
    incarnation: str,
) -> MigrationCommand:
    return MigrationCommand(
        command_id=state.issued,
        origin=origin,
        wire=wire,
        incarnation=incarnation,
    )


def _append_migration_command(
    state: MigrationState,
    command: MigrationCommand,
) -> MigrationState:
    return replace(
        state,
        pending=tuple(sorted((*state.pending, command))),
        issued=state.issued + 1,
    )


def _migration_spec_admits(
    state: MigrationState,
    command: MigrationCommand,
) -> bool:
    if state.phase in {V08_ACTIVE, V08_ROLLBACK}:
        return (
            state.v08_admission_open
            and not state.v10_admission_open
            and command.wire == V08_WIRE
            and command.incarnation == state.v08_incarnation
        )
    if state.phase == V10_ACTIVE:
        return (
            state.v10_admission_open
            and not state.v08_admission_open
            and command.wire == V10_WIRE
            and command.incarnation == state.v10_incarnation
        )
    return False


def _migration_implementation_admits(
    state: MigrationState,
    command: MigrationCommand,
    mutation: str | None,
) -> bool:
    if (
        mutation == "accept_v08_in_v10"
        and state.phase == V10_ACTIVE
        and command.wire == V08_WIRE
    ):
        return True
    if state.phase in {V08_ACTIVE, V08_ROLLBACK}:
        if mutation == "ordered_v08_incarnation":
            incarnation_ok = (
                V08_INCARNATION_RANK[command.incarnation]
                >= V08_INCARNATION_RANK[state.v08_incarnation]
            )
        else:
            incarnation_ok = command.incarnation == state.v08_incarnation
        return (
            state.v08_admission_open
            and not state.v10_admission_open
            and command.wire == V08_WIRE
            and incarnation_ok
        )
    if state.phase == V10_ACTIVE:
        return (
            state.v10_admission_open
            and not state.v08_admission_open
            and command.wire == V10_WIRE
            and command.incarnation == state.v10_incarnation
        )
    return False


def _migration_edges(
    state: MigrationState,
    mutation: str | None,
) -> Iterable[Edge]:
    if state.issued < 4:
        if state.phase == V08_ACTIVE:
            command = _migration_command(
                state,
                origin="issue_v08_pre_cutover",
                wire=V08_WIRE,
                incarnation=state.v08_incarnation,
            )
            yield Edge(
                "issue_v08_pre_cutover",
                _append_migration_command(state, command),
                {"created": command},
            )
        elif state.phase == V10_ACTIVE:
            command = _migration_command(
                state,
                origin="issue_v10",
                wire=V10_WIRE,
                incarnation=state.v10_incarnation,
            )
            yield Edge(
                "issue_v10",
                _append_migration_command(state, command),
                {"created": command},
            )
        elif state.phase == V08_ROLLBACK:
            command = _migration_command(
                state,
                origin="issue_v08_rollback",
                wire=V08_WIRE,
                incarnation=state.v08_incarnation,
            )
            yield Edge(
                "issue_v08_rollback",
                _append_migration_command(state, command),
                {"created": command},
            )

    if state.phase == V08_ACTIVE and not state.cutover_done:
        yield Edge(
            "begin_cutover",
            replace(
                state,
                phase=CUTOVER_TO_V10,
                v08_admission_open=mutation == "dual_stack_cutover",
                v10_admission_open=mutation == "dual_stack_cutover",
            ),
            {},
        )

    if state.phase == CUTOVER_TO_V10 and not state.cutover_quiesced:
        yield Edge(
            "quiesce_cutover",
            replace(state, cutover_quiesced=True),
            {},
        )

    if state.phase == CUTOVER_TO_V10 and (
        state.cutover_quiesced or mutation == "activate_v10_before_quiescence"
    ):
        yield Edge(
            "activate_v10",
            replace(
                state,
                phase=V10_ACTIVE,
                deployment_term=state.deployment_term + 1,
                v08_admission_open=False,
                v10_admission_open=True,
                cutover_done=True,
            ),
            {},
        )

    if state.phase == V10_ACTIVE and not state.rollback_done:
        yield Edge(
            "begin_rollback",
            replace(
                state,
                phase=ROLLBACK_TO_V08,
                v08_admission_open=False,
                v10_admission_open=False,
            ),
            {},
        )

    if state.phase == ROLLBACK_TO_V08 and not state.rollback_quiesced:
        yield Edge(
            "quiesce_rollback",
            replace(state, rollback_quiesced=True),
            {},
        )

    if state.phase == ROLLBACK_TO_V08 and (
        state.rollback_quiesced or mutation == "activate_v08_before_quiescence"
    ):
        next_step = (
            state.v08_incarnation_step
            if mutation == "rollback_reuses_v08_incarnation"
            else state.v08_incarnation_step + 1
        )
        yield Edge(
            "activate_v08_rollback",
            replace(
                state,
                phase=V08_ROLLBACK,
                deployment_term=state.deployment_term + 1,
                v08_incarnation_step=next_step,
                v08_admission_open=True,
                v10_admission_open=False,
                rollback_done=True,
            ),
            {},
        )

    for command in state.pending:
        admitted = _migration_implementation_admits(state, command, mutation)
        pending = tuple(item for item in state.pending if item != command)
        target = replace(
            state,
            pending=pending,
            applied=(
                tuple(sorted((*state.applied, command.command_id)))
                if admitted
                else state.applied
            ),
            rejected=(
                state.rejected
                if admitted
                else tuple(sorted((*state.rejected, command.command_id)))
            ),
        )
        yield Edge(
            f"deliver:{command.command_id}:{command.origin}",
            target,
            {
                "admitted": admitted,
                "spec_admitted": _migration_spec_admits(state, command),
                "command": command,
                "phase": state.phase,
            },
        )


def _migration_invariant(state: MigrationState) -> str | None:
    if state.v08_admission_open and state.v10_admission_open:
        return "v0.8 and v1.0 admission were open simultaneously"
    if state.phase == V08_ACTIVE and (
        not state.v08_admission_open or state.v10_admission_open
    ):
        return "initial v0.8 phase lacked its exclusive admission plane"
    if state.phase == V10_ACTIVE and (
        state.v08_admission_open
        or not state.v10_admission_open
        or not state.cutover_quiesced
        or not state.cutover_done
    ):
        return "v1.0 activated before a complete quiesced cut"
    if state.phase == V08_ROLLBACK and (
        not state.v08_admission_open
        or state.v10_admission_open
        or not state.rollback_quiesced
        or not state.rollback_done
    ):
        return "v0.8 rollback activated before a complete quiesced cut"
    if state.phase in {CUTOVER_TO_V10, ROLLBACK_TO_V08} and (
        state.v08_admission_open or state.v10_admission_open
    ):
        return "a wire admission plane remained open during quiescence"
    if state.phase == V08_ROLLBACK and state.v08_incarnation_step == 0:
        return "rollback revived the pre-cutover v0.8 incarnation"
    if len(state.applied) != len(set(state.applied)):
        return "a migration command was applied more than once"
    if set(state.applied) & set(state.rejected):
        return "a migration command is both applied and rejected"
    return None


def check_migration_cutover(mutation: str | None = None) -> dict[str, Any]:
    initial = MigrationState()
    parents: dict[MigrationState, tuple[MigrationState | None, str]] = {
        initial: (None, "")
    }
    depths = {initial: 0}
    queue: deque[MigrationState] = deque([initial])
    coverage: Counter[str] = Counter()
    witnesses: set[str] = set()
    transitions = 0
    while queue:
        state = queue.popleft()
        if len(parents) > 100_000:
            raise ModelError("migration state bound exceeded", _trace(parents, state))
        for edge in _migration_edges(state, mutation):
            transitions += 1
            action_class = edge.action.split(":", 1)[0]
            coverage[action_class] += 1
            invariant = _migration_invariant(edge.next_state)
            if invariant is not None:
                raise ModelError(invariant, _trace(parents, state, edge.action))
            metadata = edge.metadata
            if "admitted" in metadata:
                command: MigrationCommand = metadata["command"]
                if metadata["admitted"] and not metadata["spec_admitted"]:
                    raise ModelError(
                        f"stale or cross-wire command {command.origin} was admitted",
                        _trace(parents, state, edge.action),
                    )
                if metadata["admitted"] and metadata["spec_admitted"]:
                    if command.origin == "issue_v10":
                        witnesses.add("fresh_v10_command_applied")
                    if command.origin == "issue_v08_rollback":
                        witnesses.add("fresh_rollback_v08_command_applied")
                if not metadata["admitted"] and not metadata["spec_admitted"]:
                    if (
                        command.origin == "issue_v08_pre_cutover"
                        and metadata["phase"] == V10_ACTIVE
                    ):
                        witnesses.add("pre_cutover_v08_rejected_in_v10")
                    if (
                        command.origin == "issue_v08_pre_cutover"
                        and metadata["phase"] == V08_ROLLBACK
                    ):
                        witnesses.add("pre_cutover_v08_rejected_after_rollback")
            if edge.action == "quiesce_cutover":
                witnesses.add("cutover_quiescence_reached")
            if edge.action == "activate_v10":
                witnesses.add("fresh_v10_incarnation_activated")
            if edge.action == "quiesce_rollback":
                witnesses.add("rollback_quiescence_reached")
            if edge.action == "activate_v08_rollback":
                witnesses.add("fresh_v08_rollback_incarnation_activated")
            if edge.next_state not in parents:
                parents[edge.next_state] = (state, edge.action)
                depths[edge.next_state] = depths[state] + 1
                queue.append(edge.next_state)

    required_actions = {
        "issue_v08_pre_cutover",
        "begin_cutover",
        "quiesce_cutover",
        "activate_v10",
        "issue_v10",
        "begin_rollback",
        "quiesce_rollback",
        "activate_v08_rollback",
        "issue_v08_rollback",
        "deliver",
    }
    missing_actions = sorted(required_actions - set(coverage))
    if missing_actions:
        raise ModelError(f"migration actions were unreachable: {missing_actions}", [])
    required_witnesses = {
        "cutover_quiescence_reached",
        "fresh_v10_incarnation_activated",
        "pre_cutover_v08_rejected_in_v10",
        "fresh_v10_command_applied",
        "rollback_quiescence_reached",
        "fresh_v08_rollback_incarnation_activated",
        "pre_cutover_v08_rejected_after_rollback",
        "fresh_rollback_v08_command_applied",
    }
    missing_witnesses = sorted(required_witnesses - witnesses)
    if missing_witnesses:
        raise ModelError(
            f"migration non-vacuity witnesses were absent: {missing_witnesses}",
            [],
        )
    return {
        "states": len(parents),
        "transitions": transitions,
        "maximum_depth": max(depths.values()),
        "action_counts": dict(sorted(coverage.items())),
        "witnesses": sorted(witnesses),
    }


def _kill_mutations() -> list[dict[str, Any]]:
    mutations = {
        "composition": (
            check_composition,
            (
                "omit_generation",
                "ordered_generation",
                "omit_term",
                "omit_epoch",
                "omit_holder",
                "simulation_as_plant",
                "wrong_haldir_principal",
                "overlap_handover",
                "restart_loses_requested_latch",
                "restart_loses_quiesced_latch",
                "restart_loses_retired_latch",
                "restart_loses_term_persisted_latch",
                "complete_from_requested",
                "complete_from_quiesced",
                "complete_from_retired",
                "complete_to_old_holder",
            ),
        ),
        "deny_lifecycle": (
            check_deny_lifecycle,
            (
                "expiry_clears",
                "retraction_clears",
                "disable_clears",
                "restart_drops",
                "unauthenticated_clear",
                "record_only_clears",
                "assessor_allows",
                "unauthenticated_deny_applies",
                "producer_request_applies",
                "assessor_profile_applies",
                "missing_qualification_applies",
                "ineligible_verdict_applies",
                "abstention_applies",
                "same_causal_revision_applies",
                "recovery_dwell_bypass",
                "authenticated_widen_disabled",
            ),
        ),
        "migration_cutover": (
            check_migration_cutover,
            (
                "dual_stack_cutover",
                "activate_v10_before_quiescence",
                "activate_v08_before_quiescence",
                "rollback_reuses_v08_incarnation",
                "ordered_v08_incarnation",
                "accept_v08_in_v10",
            ),
        ),
    }
    killed: list[dict[str, Any]] = []
    for model_name, (checker, names) in mutations.items():
        for mutation in names:
            try:
                checker(mutation)
            except ModelError as error:
                killed.append(
                    {
                        "model": model_name,
                        "mutation": mutation,
                        "detected": True,
                        "reason": str(error),
                        "trace": error.trace,
                    }
                )
            else:
                raise ModelError(
                    f"mutation survived: {model_name}/{mutation}",
                    [],
                )
    return killed


def build_result() -> dict[str, Any]:
    composition = check_composition()
    deny = check_deny_lifecycle()
    migration = check_migration_cutover()
    mutations = _kill_mutations()
    return {
        "schema": "ncp.b01-preliminary-model-result.v2",
        "scope": "bounded-pre-ratification-counterexample-discovery",
        "claim_boundary": (
            "No counterexample was found only within this finite abstraction. "
            "This is not TLA+, refinement, implementation proof, independent review, "
            "interoperability, plant safety evidence, or release authorization."
        ),
        "composition": composition,
        "deny_lifecycle": deny,
        "migration_cutover": migration,
        "mutation_kill_matrix": mutations,
        "counts": {
            "models": 3,
            "mutations_killed": len(mutations),
            "mutations_survived": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.parse_args()
    result = build_result()
    if result["counts"]["mutations_killed"] != 38:
        raise ModelError("unexpected mutation count", [])
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
