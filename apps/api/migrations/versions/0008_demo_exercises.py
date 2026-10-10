"""Persist the isolated demo clock and saved-run manifest.

Revision ID: 0008_demo_exercises
Revises: 0007_decisions
"""

import sqlalchemy as sa
from alembic import op

from app.core.types import UTCDateTime

revision = "0008_demo_exercises"
down_revision = "0007_decisions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_exercises",
        sa.Column("exercise_id", sa.String(64), primary_key=True),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("clock", UTCDateTime(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("demo_exercises")
