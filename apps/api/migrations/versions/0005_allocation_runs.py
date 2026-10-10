"""Saved allocation proposals.

Revision ID: 0005_allocation_runs
Revises: 0004_incident_scenarios
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_allocation_runs"
down_revision: Union[str, Sequence[str], None] = "0004_incident_scenarios"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "allocation_runs",
        sa.Column("allocation_run_id", sa.String(64), nullable=False),
        sa.Column("simulation_run_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("solver_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.run_id"],
            name=op.f("fk_allocation_runs_simulation_run_id_simulation_runs"),
        ),
        sa.PrimaryKeyConstraint("allocation_run_id", name=op.f("pk_allocation_runs")),
    )
    op.create_index(
        op.f("ix_allocation_runs_simulation_run_id"), "allocation_runs", ["simulation_run_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_allocation_runs_simulation_run_id"), "allocation_runs")
    op.drop_table("allocation_runs")
