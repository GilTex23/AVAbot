"""Shikimori: cached anime data, title matching and airing source.

Revision ID: 20260914_0009
Revises: 20260914_0008
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260914_0009"
down_revision = "20260914_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shikimori_animes",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("russian", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("episodes", sa.Integer(), nullable=True),
        sa.Column("episodes_aired", sa.Integer(), nullable=True),
        sa.Column("next_episode_at", sa.DateTime(), nullable=True),
        sa.Column("aired_on", sa.Date(), nullable=True),
        sa.Column("released_on", sa.Date(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("anime_titles", sa.Column("alt_names", postgresql.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False))
    op.add_column("anime_titles", sa.Column("english_title", sa.String(), nullable=True))
    op.add_column("anime_titles", sa.Column("kind", sa.String(), nullable=True))
    op.add_column("anime_titles", sa.Column("aired_on", sa.Date(), nullable=True))
    op.add_column("anime_titles", sa.Column("episodes", sa.Integer(), nullable=True))
    op.add_column("anime_titles", sa.Column("meta_updated_at", sa.DateTime(), nullable=True))
    op.add_column("anime_titles", sa.Column("shikimori_id", sa.Integer(), nullable=True))
    op.add_column("anime_titles", sa.Column("shikimori_status", sa.String(), server_default="pending", nullable=False))
    op.add_column("anime_titles", sa.Column("shikimori_checked_at", sa.DateTime(), nullable=True))
    op.add_column("anime_titles", sa.Column("shikimori_candidates", postgresql.JSONB(), nullable=True))
    op.add_column("anime_titles", sa.Column("shikimori_error", sa.String(), nullable=True))
    op.create_foreign_key(
        "anime_titles_shikimori_id_fkey", "anime_titles", "shikimori_animes", ["shikimori_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column("episode_airings", sa.Column("source", sa.String(), server_default="animego", nullable=False))


def downgrade() -> None:
    op.drop_column("episode_airings", "source")
    op.drop_constraint("anime_titles_shikimori_id_fkey", "anime_titles", type_="foreignkey")
    for column in (
        "shikimori_error", "shikimori_candidates", "shikimori_checked_at", "shikimori_status", "shikimori_id",
        "meta_updated_at", "episodes", "aired_on", "kind", "english_title", "alt_names",
    ):
        op.drop_column("anime_titles", column)
    op.drop_table("shikimori_animes")
