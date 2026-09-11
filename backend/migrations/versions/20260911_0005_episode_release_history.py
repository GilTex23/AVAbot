"""Collect dub release and Japan airing history for next-episode forecasts.

Revision ID: 20260911_0005
Revises: 20260911_0004
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa


revision = "20260911_0005"
down_revision = "20260911_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episode_releases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("anime_url", sa.String(), nullable=False),
        sa.Column("anime_title", sa.String(), nullable=False),
        sa.Column("studio", sa.String(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("anime_url", "studio", "episode", name="uq_episode_releases_anime_studio_episode"),
    )
    op.create_index("ix_episode_releases_anime_url", "episode_releases", ["anime_url"])

    op.create_table(
        "episode_airings",
        sa.Column("anime_url", sa.String(), nullable=False),
        sa.Column("episode", sa.Integer(), nullable=False),
        sa.Column("air_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("anime_url", "episode"),
    )


def downgrade() -> None:
    op.drop_table("episode_airings")
    op.drop_index("ix_episode_releases_anime_url", table_name="episode_releases")
    op.drop_table("episode_releases")
