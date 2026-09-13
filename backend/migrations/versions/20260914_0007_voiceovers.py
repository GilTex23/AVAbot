"""Voiceover catalog and multiple favorite voiceovers per user.

Revision ID: 20260914_0007
Revises: 20260912_0006
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260914_0007"
down_revision = "20260912_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voiceovers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    # Справочник сразу наполняется тем, что уже есть: история ленты, подписки и любимые озвучки
    op.execute("""
        INSERT INTO voiceovers (name, first_seen_at, last_seen_at)
        SELECT name, MIN(seen_at), MAX(seen_at) FROM (
            SELECT studio AS name, released_at AS seen_at FROM episode_releases
            UNION ALL
            SELECT voiceover, now() AT TIME ZONE 'utc' FROM subscriptions
            UNION ALL
            SELECT favorite_voiceover, now() AT TIME ZONE 'utc' FROM users
        ) AS seen
        WHERE name IS NOT NULL AND btrim(name) <> '' AND name NOT IN ('Все', 'Unknown')
        GROUP BY name
    """)

    op.add_column(
        "users",
        sa.Column("favorite_voiceovers", postgresql.ARRAY(sa.String()), server_default=sa.text("'{}'"), nullable=False),
    )
    op.execute("""
        UPDATE users SET favorite_voiceovers = ARRAY[favorite_voiceover]
        WHERE favorite_voiceover IS NOT NULL AND btrim(favorite_voiceover) <> '' AND favorite_voiceover <> 'Все'
    """)
    op.drop_column("users", "favorite_voiceover")


def downgrade() -> None:
    op.add_column("users", sa.Column("favorite_voiceover", sa.String(), nullable=True))
    op.execute("UPDATE users SET favorite_voiceover = COALESCE(favorite_voiceovers[1], 'Все')")
    op.drop_column("users", "favorite_voiceovers")
    op.drop_table("voiceovers")
