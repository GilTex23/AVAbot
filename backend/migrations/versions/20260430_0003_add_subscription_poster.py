"""Add poster URL to subscriptions.

Revision ID: 20260430_0003
Revises: 20260430_0002
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa


revision = "20260430_0003"
down_revision = "20260430_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("poster_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "poster_url")
