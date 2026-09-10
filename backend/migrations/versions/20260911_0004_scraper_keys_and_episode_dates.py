"""Store ScraperAPI keys in the database and track last episode dates.

Revision ID: 20260911_0004
Revises: 20260430_0003
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa


revision = "20260911_0004"
down_revision = "20260430_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Существующим подпискам отсчёт 30 дней без серий начинается с момента миграции
    op.add_column(
        "subscriptions",
        sa.Column("last_episode_at", sa.DateTime(), server_default=sa.text("timezone('utc', now())"), nullable=True),
    )
    # NULL: страницы существующих подписок посмотрим при первой же проверке
    op.add_column("subscriptions", sa.Column("info_checked_at", sa.DateTime(), nullable=True))

    op.create_table(
        "scraper_api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("key_encrypted", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(), server_default="active", nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=True),
        sa.Column("request_limit", sa.Integer(), nullable=True),
        sa.Column("failed_request_count", sa.Integer(), nullable=True),
        sa.Column("subscription_date", sa.DateTime(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scraper_api_key_usage",
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("success", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["key_id"], ["scraper_api_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("key_id", "day"),
    )


def downgrade() -> None:
    op.drop_table("scraper_api_key_usage")
    op.drop_table("scraper_api_keys")
    op.drop_column("subscriptions", "info_checked_at")
    op.drop_column("subscriptions", "last_episode_at")
