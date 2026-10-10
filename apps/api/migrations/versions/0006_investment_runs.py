"""Saved investment funding proposals.

Revision ID: 0006_investment_runs
Revises: 0005_allocation_runs
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_investment_runs"
down_revision: Union[str, Sequence[str], None] = "0005_allocation_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_runs",
        sa.Column("investment_run_id", sa.String(64), nullable=False),
        sa.Column("allocation_run_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(64), nullable=False),
        sa.Column("solver_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["allocation_run_id"],
            ["allocation_runs.allocation_run_id"],
            name=op.f("fk_investment_runs_allocation_run_id_allocation_runs"),
        ),
        sa.PrimaryKeyConstraint("investment_run_id", name=op.f("pk_investment_runs")),
    )
    op.create_index(
        op.f("ix_investment_runs_allocation_run_id"), "investment_runs", ["allocation_run_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_investment_runs_allocation_run_id"), "investment_runs")
    op.drop_table("investment_runs")
