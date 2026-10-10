"""Pure decision state machine: (record, command) -> new record, or a DecisionError.

draft -> pending_review -> approved -> in_progress -> completed
                       -> rejected
draft/pending_review/approved/in_progress -> cancelled

No database, clock or inventory access: recording a decision never changes hospital
reports. Prerequisite decision status is passed in by the caller.
"""

from datetime import datetime

from app.modules.decisions.errors import DecisionError, invalid
from app.modules.decisions.schemas import (
    TERMINAL_DECISION,
    ActionCorrection,
    ActionItem,
    ActionStatus,
    DecisionEventRequest,
    DecisionRecord,
    DecisionStatus,
)

S, A = DecisionStatus, ActionStatus
ACTION_MOVES = {
    A.PENDING: {A.IN_PROGRESS, A.BLOCKED},
    A.IN_PROGRESS: {A.BLOCKED, A.COMPLETED},
    A.BLOCKED: {A.IN_PROGRESS, A.BLOCKED},
}


def _transition(name: str, current: DecisionStatus, allowed: set[DecisionStatus]) -> None:
    if current not in allowed:
        raise DecisionError("invalid_transition",
                            f"Cannot {name} a decision that is {current.value}.")


def _not_future(field: str, value: datetime | None, now: datetime) -> None:
    if value is not None and value > now:
        raise invalid(field, "Reported execution times cannot be in the future.")


def apply(record: DecisionRecord, command: DecisionEventRequest, now: datetime,
          prerequisite_status: DecisionStatus | None) -> DecisionRecord:
    """Return the record after the command. Raises DecisionError on any illegal change."""
    p = command.payload
    status = record.status
    updates: dict = {}
    actions = [a.model_copy() for a in record.actions]
    by_id = {a.action_id: a for a in actions}

    for field in ("occurred_at", "completed_at"):
        _not_future(f"payload.{field}", getattr(p, field, None), now)

    match p.event_type:
        case "edit_draft":
            _transition("edit", status, {S.DRAFT})
            updates = {k: v for k, v in {"title": p.title, "owner_name": p.owner_name,
                                         "rationale": p.rationale,
                                         "target_completion_at": p.target_completion_at
                                         }.items() if v is not None}
        case "submit":
            _transition("submit", status, {S.DRAFT})
            updates["status"] = S.PENDING_REVIEW
        case "approve" | "reject":
            _transition(p.event_type, status, {S.PENDING_REVIEW})
            updates["status"] = S.APPROVED if p.event_type == "approve" else S.REJECTED
        case "start":
            _transition("start", status, {S.APPROVED})
            _require_prerequisite(record, prerequisite_status)
            updates["status"] = S.IN_PROGRESS
        case "update_action":
            _transition("update actions of", status, {S.IN_PROGRESS})
            action = by_id.get(p.action_id)
            if action is None:
                raise invalid("payload.action_id", f"Unknown action {p.action_id}.")
            target = A(p.status)
            if target not in ACTION_MOVES.get(action.status, set()):
                raise DecisionError("invalid_transition", f"Action {action.action_id} cannot "
                                    f"move from {action.status.value} to {target.value}; "
                                    "use correct_action_report for completed actions.")
            if target in (A.IN_PROGRESS, A.COMPLETED):
                _require_prerequisite(record, prerequisite_status)
                unfinished = [r for r in action.requires_action_ids
                              if by_id[r].status != A.COMPLETED]
                if unfinished:
                    raise DecisionError("prerequisite_not_met", f"Complete {', '.join(unfinished)}"
                                        f" before {action.action_id}.")
            change: dict = {"status": target}
            if target == A.IN_PROGRESS and action.reported_started_at is None:
                change["reported_started_at"] = p.occurred_at
            if target == A.BLOCKED:
                change["blocker_note"] = p.blocker_note
            if target == A.COMPLETED:
                if action.reported_started_at and p.occurred_at < action.reported_started_at:
                    raise invalid("payload.occurred_at",
                                  "Completion cannot precede the reported start.")
                change.update(reported_completed_at=p.occurred_at,
                              evidence_note=p.evidence_note,
                              actual_cost_minor_units=p.actual_cost_minor_units,
                              blocker_note=None)
            by_id[action.action_id] = action.model_copy(update=change)
        case "complete":
            allowed = {S.IN_PROGRESS} | ({S.APPROVED} if not actions else set())
            _transition("complete", status, allowed)
            unfinished = [a.action_id for a in actions if a.status != A.COMPLETED]
            if unfinished:
                raise DecisionError("prerequisite_not_met", "Every action must be reported "
                                    f"completed first: {', '.join(unfinished)}.")
            updates["status"] = S.COMPLETED
        case "cancel":
            _transition("cancel", status, set(S) - TERMINAL_DECISION)
            updates["status"] = S.CANCELLED
            for a in actions:  # completed work is preserved
                if a.status != A.COMPLETED:
                    by_id[a.action_id] = a.model_copy(update={"status": A.CANCELLED})
        case "correct_action_report":
            _transition("correct actions of", status,
                        {S.IN_PROGRESS, S.COMPLETED, S.CANCELLED})
            action = by_id.get(p.action_id)
            if action is None:
                raise invalid("payload.action_id", f"Unknown action {p.action_id}.")
            if action.status != A.COMPLETED:
                raise DecisionError("invalid_transition",
                                    "Only completed action reports can be corrected.")
            correction = ActionCorrection(
                corrected_at=now, actor_name=command.actor_name, reason=p.reason,
                previous_completed_at=action.reported_completed_at,
                previous_evidence_note=action.evidence_note,
                previous_actual_cost_minor_units=action.actual_cost_minor_units)
            change = {"corrections": [*action.corrections, correction]}
            if p.completed_at is not None:
                change["reported_completed_at"] = p.completed_at
            if p.evidence_note is not None:
                change["evidence_note"] = p.evidence_note
            if p.actual_cost_minor_units is not None:
                change["actual_cost_minor_units"] = p.actual_cost_minor_units
            by_id[action.action_id] = action.model_copy(update=change)

    new_actions: list[ActionItem] = [by_id[a.action_id] for a in actions]
    return record.model_copy(update={**updates, "actions": new_actions, "updated_at": now})


def _require_prerequisite(record: DecisionRecord,
                          prerequisite_status: DecisionStatus | None) -> None:
    if record.prerequisite_decision_id and prerequisite_status != S.COMPLETED:
        raise DecisionError("prerequisite_not_met", f"Prerequisite decision "
                            f"{record.prerequisite_decision_id} must be reported completed "
                            "before this work starts.")
