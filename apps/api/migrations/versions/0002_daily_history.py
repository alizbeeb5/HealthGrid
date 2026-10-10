"""Daily resource and service-demand history for forecasting.

Revision ID: 0002_daily_history
Revises: 0001_facility_snapshot
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_daily_history"
down_revision: Union[str, Sequence[str], None] = "0001_facility_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_resource_records",
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("available_quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("data_quality", sa.String(20), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "available_quantity >= 0",
            name=op.f("ck_daily_resource_records_quantity_nonnegative"),
        ),
        sa.CheckConstraint(
            "data_quality IN ('reported', 'estimated')",
            name=op.f("ck_daily_resource_records_data_quality"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id", "resource_id"],
            ["facility_resources.facility_id", "facility_resources.resource_id"],
            name=op.f("fk_daily_resource_records_facility_resource"),
        ),
        sa.PrimaryKeyConstraint(
            "facility_id", "resource_id", "record_date", name=op.f("pk_daily_resource_records")
        ),
    )
    op.create_table(
        "daily_service_demand",
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("peak_required_places", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("data_quality", sa.String(20), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "peak_required_places >= 0",
            name=op.f("ck_daily_service_demand_places_nonnegative"),
        ),
        sa.CheckConstraint(
            "data_quality IN ('reported', 'estimated')",
            name=op.f("ck_daily_service_demand_data_quality"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id", "service_id"],
            ["facility_services.facility_id", "facility_services.service_id"],
            name=op.f("fk_daily_service_demand_facility_service"),
        ),
        sa.PrimaryKeyConstraint(
            "facility_id", "service_id", "record_date", name=op.f("pk_daily_service_demand")
        ),
    )


def downgrade() -> None:
    op.drop_table("daily_service_demand")
    op.drop_table("daily_resource_records")
