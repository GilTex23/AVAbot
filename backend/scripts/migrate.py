from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from database.requests import engine

BASELINE_REVISION = "20260430_0001"


async def _needs_baseline_stamp() -> bool:
    async with engine.connect() as conn:
        users_exists = await conn.scalar(text("SELECT to_regclass('public.users') IS NOT NULL"))
        subscriptions_exists = await conn.scalar(text("SELECT to_regclass('public.subscriptions') IS NOT NULL"))
        alembic_exists = await conn.scalar(text("SELECT to_regclass('public.alembic_version') IS NOT NULL"))

    return bool(users_exists and subscriptions_exists and not alembic_exists)


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    return Config(str(backend_dir / "alembic.ini"))


def main() -> None:
    cfg = _alembic_config()
    if asyncio.run(_needs_baseline_stamp()):
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
