"""Incidents, immutable revisions, baselines and saved simulation runs.

Revision ID: 0004_incident_scenarios
Revises: 0003_daily_service_status
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_incident_scenarios"
down_revision: Union[str, Sequence[str], None] = "0003_daily_service_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("incident_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("incident_id", name=op.f("pk_incidents")),
    )
    op.create_table(
        "incident_baselines",
        sa.Column("baseline_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("baseline_id", name=op.f("pk_incident_baselines")),
    )
    op.create_table(
        "incident_revisions",
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("incident_id", sa.String(64), nullable=False),
        sa.Column("parent_revision_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(100), nullable=True),
        sa.Column("baseline_id", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed')", name=op.f("ck_incident_revisions_status")
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND baseline_id IS NULL AND confirmed_at IS NULL"
            " AND confirmed_by IS NULL) OR (status = 'confirmed' AND baseline_id IS NOT NULL"
            " AND confirmed_at IS NOT NULL AND confirmed_by IS NOT NULL)",
            name=op.f("ck_incident_revisions_confirmation_fields"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.incident_id"],
            name=op.f("fk_incident_revisions_incident_id_incidents"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_revision_id"],
            ["incident_revisions.revision_id"],
            name=op.f("fk_incident_revisions_parent_revision_id_incident_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["baseline_id"],
            ["incident_baselines.baseline_id"],
            name=op.f("fk_incident_revisions_baseline_id_incident_baselines"),
        ),
        sa.PrimaryKeyConstraint("revision_id", name=op.f("pk_incident_revisions")),
        sa.UniqueConstraint(
            "parent_revision_id", name=op.f("uq_incident_revisions_parent_revision_id")
        ),
        sa.UniqueConstraint("baseline_id", name=op.f("uq_incident_revisions_baseline_id")),
    )
    op.create_index(
        op.f("ix_incident_revisions_incident_id"), "incident_revisions", ["incident_id"]
    )
    op.create_table(
        "simulation_runs",
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("revision_id", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impact", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["incident_revisions.revision_id"],
            name=op.f("fk_simulation_runs_revision_id_incident_revisions"),
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_simulation_runs")),
        sa.UniqueConstraint(
            "revision_id", "engine_version", name=op.f("uq_simulation_runs_revision_engine")
        ),
    )


def downgrade() -> None:
    op.drop_table("simulation_runs")
    op.drop_index(op.f("ix_incident_revisions_incident_id"), "incident_revisions")
    op.drop_table("incident_revisions")
    op.drop_table("incident_baselines")
    op.drop_table("incidents")
