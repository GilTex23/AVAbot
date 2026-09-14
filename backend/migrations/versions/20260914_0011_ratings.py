"""Ratings from AnimeGO, Shikimori and YummyAnime.

Revision ID: 20260914_0011
Revises: 20260914_0010
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "20260914_0011"
down_revision = "20260914_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("anime_titles", sa.Column("rating", sa.Float(), nullable=True))
    op.add_column("anime_titles", sa.Column("rating_votes", sa.Integer(), nullable=True))
    op.add_column("shikimori_animes", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("yummy_titles", sa.Column("rating", sa.Float(), nullable=True))
    op.add_column("yummy_titles", sa.Column("rating_votes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("yummy_titles", "rating_votes")
    op.drop_column("yummy_titles", "rating")
    op.drop_column("shikimori_animes", "score")
    op.drop_column("anime_titles", "rating_votes")
    op.drop_column("anime_titles", "rating")
