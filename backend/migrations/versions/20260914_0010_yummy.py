"""YummyAnime as a second episode source.

Revision ID: 20260914_0010
Revises: 20260914_0009
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "20260914_0010"
down_revision = "20260914_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("source", sa.String(), server_default="animego", nullable=False))
    op.add_column("subscriptions", sa.Column("source_id", sa.String(), nullable=True))

    op.create_table(
        "yummy_titles",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("poster_url", sa.String(), nullable=True),
        sa.Column("shikimori_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("episodes_count", sa.Integer(), nullable=True),
        sa.Column("episodes_aired", sa.Integer(), nullable=True),
        sa.Column("next_episode_at", sa.DateTime(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_yummy_titles_shikimori_id", "yummy_titles", ["shikimori_id"])


def downgrade() -> None:
    op.drop_index("ix_yummy_titles_shikimori_id", table_name="yummy_titles")
    op.drop_table("yummy_titles")
    op.drop_column("subscriptions", "source_id")
    op.drop_column("subscriptions", "source")
