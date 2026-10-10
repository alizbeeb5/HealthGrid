"""Preserve historical service status, separate from the current snapshot."""

import sqlalchemy as sa
from alembic import op

revision = "0003_daily_service_status"
down_revision = "0002_daily_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("daily_service_demand") as batch:
        batch.add_column(
            sa.Column("service_status", sa.String(20), nullable=False, server_default="operating")
        )
        batch.create_check_constraint(
            "service_status", "service_status IN ('operating', 'limited', 'unavailable')"
        )


def downgrade() -> None:
    with op.batch_alter_table("daily_service_demand") as batch:
        batch.drop_constraint("service_status", type_="check")
        batch.drop_column("service_status")
