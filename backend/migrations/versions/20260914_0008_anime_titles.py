"""AnimeGO titles by numeric id for bot deep links.

Revision ID: 20260914_0008
Revises: 20260914_0007
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "20260914_0008"
down_revision = "20260914_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anime_titles",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("poster_url", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    # Тайтлы из подписок и истории ленты: у адреса AnimeGO в конце числовой id («…-3484»)
    op.execute(r"""
        INSERT INTO anime_titles (id, url, title, poster_url, updated_at)
        SELECT DISTINCT ON (anime_id) anime_id, url, title, poster_url, now() AT TIME ZONE 'utc'
        FROM (
            SELECT substring(anime_url from '-(\d+)/?$')::int AS anime_id, anime_url AS url, anime_title AS title,
                   poster_url, 0 AS priority
            FROM subscriptions
            UNION ALL
            SELECT substring(anime_url from '-(\d+)/?$')::int, anime_url, anime_title, NULL, 1
            FROM episode_releases
        ) AS seen
        WHERE anime_id IS NOT NULL AND title IS NOT NULL AND title <> 'Unknown'
        ORDER BY anime_id, priority, poster_url IS NULL
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("anime_titles")
