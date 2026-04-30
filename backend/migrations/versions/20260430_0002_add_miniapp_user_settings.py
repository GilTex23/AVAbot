"""Add mini app profile and quiet-hours settings.

Revision ID: 20260430_0002
Revises: 20260430_0001
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa


revision = "20260430_0002"
down_revision = "20260430_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("photo_url", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("quiet_hours_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("quiet_hours_start", sa.String(), server_default="23:00", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("quiet_hours_end", sa.String(), server_default="09:00", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("quiet_timezone", sa.String(), server_default="Europe/Moscow", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "quiet_timezone")
    op.drop_column("users", "quiet_hours_end")
    op.drop_column("users", "quiet_hours_start")
    op.drop_column("users", "quiet_hours_enabled")
    op.drop_column("users", "photo_url")
