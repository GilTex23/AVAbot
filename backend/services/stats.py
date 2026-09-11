"""
Статистика для админки: сбор дневных счётчиков и сборка данных для экрана «Статистика».

Источник запроса (кто попросил страницу AnimeGO) передаётся через ContextVar, а не параметрами:
его выставляют чекеры, зависимость мини-аппа, админка и вебхук бота, а get_html только читает.
Всё хранится STATS_RETENTION_DAYS дней.
"""
import asyncio
import datetime
import logging
import os
import platform
import time
from collections import defaultdict
from contextvars import ContextVar
from pathlib import Path

import psutil

from database import requests as db

logger = logging.getLogger(__name__)

STATS_RETENTION_DAYS = 180

SOURCE_CHECKER = "checker"
SOURCE_STATUS_CHECK = "status_check"
SOURCE_MINIAPP = "miniapp"
SOURCE_BOT = "bot"
SOURCE_ADMIN = "admin"
SOURCE_OTHER = "other"

request_source: ContextVar[str] = ContextVar("request_source", default=SOURCE_OTHER)

PROCESS_STARTED_AT = time.time()
LOGS_DIR = Path("logs")

# Кто уже отмечен активным сегодня — чтобы не писать в базу на каждый запрос
_active_marked: set[tuple[datetime.date, int, str]] = set()


def set_source(source: str):
    request_source.set(source)


async def increment(metric: str, dimension: str = "", value: int = 1):
    """Прибавляет к дневному счётчику; ошибка статистики никогда не ломает основную работу"""
    await increment_many([(metric, dimension, value)])


async def increment_many(rows: list[tuple[str, str, int]]):
    try:
        await db.increment_daily_stats(rows)
    except Exception as e:
        logger.warning(f"Failed to record stats {rows}: {e}")


async def mark_active(user_id: int, source: str):
    day = datetime.datetime.utcnow().date()
    key = (day, user_id, source)
    if key in _active_marked:
        return
    try:
        await db.record_user_activity(user_id, source, day)
        if len(_active_marked) > 50_000:
            _active_marked.clear()
        _active_marked.add(key)
    except Exception as e:
        logger.warning(f"Failed to record activity of {user_id}: {e}")


async def record_key_snapshots(rows):
    """Снимок счётчиков всех ключей после опроса /account"""
    now = datetime.datetime.utcnow()
    try:
        await db.add_key_snapshots([
            {
                "taken_at": now,
                "key_id": row.id,
                "key_name": row.name,
                "request_count": row.request_count,
                "request_limit": row.request_limit,
                "status": row.status,
                "enabled": row.enabled,
            }
            for row in rows
        ])
    except Exception as e:
        logger.warning(f"Failed to record key snapshots: {e}")


async def prune_old_stats():
    """Ежедневно: удаляет статистику и историю старше STATS_RETENTION_DAYS"""
    before = datetime.datetime.utcnow().date() - datetime.timedelta(days=STATS_RETENTION_DAYS)
    deleted = await db.prune_statistics(before)
    logger.info(f"Old statistics pruned (before {before}): {deleted}")


# --- Сборка данных для экрана «Статистика» ---

def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo:
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value.isoformat() + "Z"
    return value.isoformat()


def _series(days: list[datetime.date], values: dict) -> list[int]:
    return [int(values.get(day, 0)) for day in days]


def _grouped_series(days: list[datetime.date], values: dict) -> dict[str, list[int]]:
    """values: {(day, name): number} -> {name: [по дням]}, по убыванию суммы"""
    names = defaultdict(int)
    for (_, name), value in values.items():
        names[name] += value
    return {name: [int(values.get((day, name), 0)) for day in days] for name in sorted(names, key=lambda n: -names[n])}


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def _server_info() -> dict:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    process = psutil.Process(os.getpid())
    try:
        load = [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        load = None
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_count": psutil.cpu_count(),
        "load_average": load,
        "memory_total": memory.total,
        "memory_used": memory.total - memory.available,
        "memory_percent": memory.percent,
        "process_memory": process.memory_info().rss,
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_percent": disk.percent,
        "logs_bytes": _directory_size(LOGS_DIR),
        "process_uptime_seconds": int(time.time() - PROCESS_STARTED_AT),
        "system_uptime_seconds": int(time.time() - psutil.boot_time()),
        "python": platform.python_version(),
    }


async def build_stats(period_days: int) -> dict:
    today = datetime.datetime.utcnow().date()
    first_day = today - datetime.timedelta(days=period_days - 1)
    days = [first_day + datetime.timedelta(days=offset) for offset in range(period_days)]

    metrics = defaultdict(dict)  # metric -> {(day, dimension): value}
    for day, metric, dimension, value in await db.get_daily_stats(first_day):
        metrics[metric][(day, dimension)] = metrics[metric].get((day, dimension), 0) + value

    def by_day(metric: str, dimension: str | None = None) -> list[int]:
        values = defaultdict(int)
        for (day, dim), value in metrics[metric].items():
            if dimension is None or dim == dimension:
                values[day] += value
        return _series(days, values)

    def by_dimension(metric: str, transform=lambda dim: dim) -> dict[str, list[int]]:
        values = defaultdict(int)
        for (day, dim), value in metrics[metric].items():
            values[(day, transform(dim))] += value
        return _grouped_series(days, values)

    # Запросы к ScraperAPI: dimension = «источник:страница» (checker:home, miniapp:anime...)
    success_by_source = by_dimension("scraper.success", lambda dim: dim.split(":")[0])
    success_by_page = by_dimension("scraper.success", lambda dim: dim.split(":")[-1])
    latency_sum, latency_count = by_day("scraper.latency_ms"), by_day("scraper.latency_count")

    key_usage = {}
    for day, name, success, failed in await db.get_key_usage_by_day(first_day):
        key_usage[(day, name)] = success
    snapshots = await db.get_key_snapshots(datetime.datetime.combine(first_day, datetime.time()))
    credits = defaultdict(lambda: {"remaining": 0, "limit": 0})
    for snapshot in snapshots:
        # Снимки одного опроса пишутся одним временем — складываем ключи в ротации
        if snapshot.enabled and snapshot.status in ("active", "low") and snapshot.request_limit:
            point = credits[snapshot.taken_at.replace(second=0, microsecond=0)]
            point["remaining"] += max(snapshot.request_limit - (snapshot.request_count or 0), 0)
            point["limit"] += snapshot.request_limit

    activity_by_source, activity_total = await db.get_activity_by_day(first_day)
    new_users = {day: count for day, count in await db.get_new_users_by_day(first_day)}
    history = await db.get_history_overview(first_day)
    database = await db.get_database_overview()

    return {
        "period_days": period_days,
        "days": [day.isoformat() for day in days],
        "scraper": {
            "success_by_source": success_by_source,
            "success_by_page": success_by_page,
            "by_key": _grouped_series(days, key_usage),
            "failed": by_day("scraper.failed"),
            "timeouts": by_day("scraper.timeout"),
            "failed_by_status": by_dimension("scraper.failed_status"),
            "cache_hits": by_day("cache.hit"),
            "latency_avg_ms": [round(total / count) if count else None for total, count in zip(latency_sum, latency_count)],
            "credits": [{"at": _iso(at), **values} for at, values in sorted(credits.items())],
            "key_status_changes": by_dimension("keys.status_change"),
        },
        "bot": {
            **await db.get_bot_overview(),
            "active_7d": await db.count_active_users(today - datetime.timedelta(days=6)),
            "active_30d": await db.count_active_users(today - datetime.timedelta(days=29)),
            "active_by_source": _grouped_series(days, {(day, source): count for day, source, count in activity_by_source}),
            "active_total": _series(days, {day: count for day, count in activity_total}),
            "new_users": _series(days, new_users),
            "notifications_sent": by_day("notifications.sent"),
            "notifications_deferred": by_day("notifications.deferred"),
            "subscriptions_created": by_day("subscriptions.created"),
            "subscriptions_deleted": by_day("subscriptions.deleted"),
            "subscriptions_completed": by_day("subscriptions.completed"),
            "subscriptions_stale": by_day("subscriptions.stale"),
        },
        "parser": {"home_results": by_dimension("home.result")},
        "history": {
            "releases": history["releases"],
            "airings": history["airings"],
            "titles": history["titles"],
            "releases_per_day": _series(days, {day: count for day, count in history["per_day"]}),
        },
        "database": {**database, "started_at": _iso(database["started_at"]), "retention_days": STATS_RETENTION_DAYS},
        "server": await asyncio.to_thread(_server_info),
    }
