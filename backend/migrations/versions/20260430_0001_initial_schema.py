"""Initial bot schema.

Revision ID: 20260430_0001
Revises:
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa


revision = "20260430_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("favorite_voiceover", sa.String(), nullable=True),
        sa.Column("registered_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("anime_url", sa.String(), nullable=False),
        sa.Column("anime_title", sa.String(), nullable=False),
        sa.Column("voiceover", sa.String(), nullable=False),
        sa.Column("total_episodes", sa.Integer(), nullable=True),
        sa.Column("last_episode", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("users")
