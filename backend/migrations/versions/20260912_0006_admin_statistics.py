"""Daily statistics, user activity and ScraperAPI key snapshots for the admin statistics page.

Revision ID: 20260912_0006
Revises: 20260911_0005
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa


revision = "20260912_0006"
down_revision = "20260911_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_stats",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("dimension", sa.String(), server_default="", nullable=False),
        sa.Column("value", sa.BigInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("day", "metric", "dimension"),
    )

    op.create_table(
        "user_activity",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("day", "user_id", "source"),
    )

    op.create_table(
        "scraper_key_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("taken_at", sa.DateTime(), nullable=False),
        sa.Column("key_id", sa.Integer(), nullable=True),
        sa.Column("key_name", sa.String(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=True),
        sa.Column("request_limit", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["scraper_api_keys.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scraper_key_snapshots_taken_at", "scraper_key_snapshots", ["taken_at"])


def downgrade() -> None:
    op.drop_index("ix_scraper_key_snapshots_taken_at", table_name="scraper_key_snapshots")
    op.drop_table("scraper_key_snapshots")
    op.drop_table("user_activity")
    op.drop_table("daily_stats")
