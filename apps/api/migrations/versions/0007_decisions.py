"""Decisions, append-only decision events and captured outcome reviews.

Revision ID: 0007_decisions
Revises: 0006_investment_runs
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_decisions"
down_revision: Union[str, Sequence[str], None] = "0006_investment_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE = sa.text("status NOT IN ('rejected', 'cancelled')")


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("decision_id", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_run_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("decision_id", name=op.f("pk_decisions")),
    )
    op.create_index(
        "uq_decisions_active_source", "decisions", ["source_type", "source_run_id"],
        unique=True, sqlite_where=ACTIVE, postgresql_where=ACTIVE,
    )
    op.create_table(
        "decision_events",
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("decision_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["decisions.decision_id"],
            name=op.f("fk_decision_events_decision_id_decisions"),
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_decision_events")),
        sa.UniqueConstraint("decision_id", "sequence", name="uq_decision_events_sequence"),
        sa.UniqueConstraint("decision_id", "request_id", name="uq_decision_events_request"),
    )
    op.create_index(
        op.f("ix_decision_events_decision_id"), "decision_events", ["decision_id"]
    )
    op.create_table(
        "outcome_reviews",
        sa.Column("review_id", sa.String(64), nullable=False),
        sa.Column("decision_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["decisions.decision_id"],
            name=op.f("fk_outcome_reviews_decision_id_decisions"),
        ),
        sa.PrimaryKeyConstraint("review_id", name=op.f("pk_outcome_reviews")),
        sa.UniqueConstraint("decision_id", "request_id", name="uq_outcome_reviews_request"),
    )
    op.create_index(
        op.f("ix_outcome_reviews_decision_id"), "outcome_reviews", ["decision_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_outcome_reviews_decision_id"), "outcome_reviews")
    op.drop_table("outcome_reviews")
    op.drop_index(op.f("ix_decision_events_decision_id"), "decision_events")
    op.drop_table("decision_events")
    op.drop_index("uq_decisions_active_source", "decisions")
    op.drop_table("decisions")
