"""Facilities, services, resource definitions and resource observations.

Revision ID: 0001_facility_snapshot
Revises:
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_facility_snapshot"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "facilities",
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name=op.f("ck_facilities_latitude_range")
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name=op.f("ck_facilities_longitude_range")
        ),
        sa.PrimaryKeyConstraint("facility_id", name=op.f("pk_facilities")),
    )
    op.create_table(
        "services",
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("service_id", name=op.f("pk_services")),
    )
    op.create_table(
        "resource_definitions",
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("allows_fractional", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "category IN ('beds', 'staff', 'equipment', 'supplies', 'infrastructure')",
            name=op.f("ck_resource_definitions_category"),
        ),
        sa.CheckConstraint(
            "unit IN ('bed', 'person', 'item', 'liter')",
            name=op.f("ck_resource_definitions_unit"),
        ),
        sa.PrimaryKeyConstraint("resource_id", name=op.f("pk_resource_definitions")),
    )
    op.create_table(
        "facility_services",
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.CheckConstraint(
            "status IN ('operating', 'limited', 'unavailable')",
            name=op.f("ck_facility_services_status"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.facility_id"],
            name=op.f("fk_facility_services_facility_id_facilities"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.service_id"],
            name=op.f("fk_facility_services_service_id_services"),
        ),
        sa.PrimaryKeyConstraint("facility_id", "service_id", name=op.f("pk_facility_services")),
    )
    op.create_table(
        "facility_resources",
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.facility_id"],
            name=op.f("fk_facility_resources_facility_id_facilities"),
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resource_definitions.resource_id"],
            name=op.f("fk_facility_resources_resource_id_resource_definitions"),
        ),
        sa.PrimaryKeyConstraint(
            "facility_id", "resource_id", name=op.f("pk_facility_resources")
        ),
    )
    op.create_table(
        "resource_observations",
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("available_quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "available_quantity >= 0",
            name=op.f("ck_resource_observations_quantity_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id", "resource_id"],
            ["facility_resources.facility_id", "facility_resources.resource_id"],
            name=op.f("fk_resource_observations_facility_resource"),
        ),
        sa.PrimaryKeyConstraint("observation_id", name=op.f("pk_resource_observations")),
    )
    op.create_index(
        "ix_resource_observations_latest",
        "resource_observations",
        ["facility_id", "resource_id", "observed_at", "recorded_at"],
    )
    op.create_index(
        op.f("ix_resource_observations_recorded_at"), "resource_observations", ["recorded_at"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_resource_observations_recorded_at"), "resource_observations")
    op.drop_index("ix_resource_observations_latest", "resource_observations")
    op.drop_table("resource_observations")
    op.drop_table("facility_resources")
    op.drop_table("facility_services")
    op.drop_table("resource_definitions")
    op.drop_table("services")
    op.drop_table("facilities")
