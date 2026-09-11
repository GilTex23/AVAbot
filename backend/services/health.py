"""
Здоровье парсинга главной AnimeGO.

Бот целиком держится на разборе одной страницы: если AnimeGO поменяет разметку, лента начнёт
разбираться в пустоту и уведомления тихо перестанут приходить. Здесь после каждой загрузки
запоминается, что удалось разобрать, а админам уходит сообщение, если проблема держится
FAILURE_THRESHOLD загрузок подряд (и ещё одно — когда всё восстановилось).
"""
import datetime
import html
import logging
from dataclasses import dataclass, field

from aiogram import Bot

from services import stats
from services.notifier import notify_admins

logger = logging.getLogger(__name__)

# Чекер ходит на главную раз в 20 минут: три загрузки подряд — это около часа
FAILURE_THRESHOLD = 3
# О незнакомом поясе админам пишет timezone_alerts по каждой странице; уведомления о сериях при этом работают,
# поэтому в счёт сбоев подряд такая проблема не идёт — она только видна в админке
TIMEZONE_PROBLEM_PREFIX = "Незнакомый часовой пояс страницы"


@dataclass
class HomeHealth:
    last_attempt_at: datetime.datetime | None = None
    last_success_at: datetime.datetime | None = None
    updates_count: int = 0
    schedule_count: int = 0
    timed_schedule_count: int = 0
    timezone: str | None = None
    problems: list[str] = field(default_factory=list)
    consecutive_failures: int = 0
    alerted: bool = False


home_health = HomeHealth()


def find_problems(home: dict | None) -> list[str]:
    if home is None:
        return ["Не удалось загрузить главную AnimeGO"]

    problems = []
    updates = home.get("updates") or []
    schedule_items = [item for day in home.get("schedule") or [] for item in day.get("items") or []]
    # При незнакомом поясе время со страницы не используется намеренно — это не поломка разметки
    timezone_unknown = bool(home.get("timezone")) and not home.get("timezone_known")

    if not updates:
        problems.append("Лента обновлений разобралась пустой — возможно, AnimeGO поменял разметку")
    elif not timezone_unknown and not any(update.get("released_at") for update in updates):
        problems.append("В ленте не распознано время выхода серий")

    if not schedule_items:
        problems.append("Расписание разобралось пустым — возможно, AnimeGO поменял разметку")
    elif timezone_unknown:
        problems.append(f"{TIMEZONE_PROBLEM_PREFIX}: «{home['timezone']}»")
    elif not any(item.get("air_at") for item in schedule_items):
        problems.append("В расписании не распознано время выхода серий")

    return problems


async def record_home_result(bot: Bot | None, home: dict | None) -> list[str]:
    """Учитывает результат очередной загрузки главной и при необходимости пишет админам"""
    now = datetime.datetime.utcnow()
    health = home_health
    health.last_attempt_at = now

    if home is not None:
        health.updates_count = len(home.get("updates") or [])
        schedule_items = [item for day in home.get("schedule") or [] for item in day.get("items") or []]
        health.schedule_count = len(schedule_items)
        health.timed_schedule_count = sum(1 for item in schedule_items if item.get("air_at"))
        health.timezone = home.get("timezone")

    problems = find_problems(home)
    health.problems = problems
    failures = [problem for problem in problems if not problem.startswith(TIMEZONE_PROBLEM_PREFIX)]
    if home is None:
        result = "fetch_failed"
    elif failures:
        result = "problem"
    else:
        result = "timezone_unknown" if problems else "ok"
    await stats.increment("home.result", result)

    if not failures:
        health.last_success_at = now
        health.consecutive_failures = 0
        if health.alerted and bot is not None:
            health.alerted = False
            await notify_admins(bot, "✅ Парсинг главной AnimeGO снова работает.", level="INFO")
        return problems

    health.consecutive_failures += 1
    logger.warning(f"AnimeGO home page problems ({health.consecutive_failures} in a row): {problems}")
    if health.consecutive_failures >= FAILURE_THRESHOLD and not health.alerted and bot is not None:
        health.alerted = True
        await notify_admins(
            bot,
            f"Проблема с главной AnimeGO уже {health.consecutive_failures} загрузки подряд — "
            "уведомления о новых сериях могут не приходить.\n\n"
            + "\n".join(f"• {html.escape(problem)}" for problem in problems),
            level="ERROR",
        )
    return problems


def snapshot() -> dict:
    health = home_health

    def iso(value):
        return value.isoformat() + "Z" if value else None

    return {
        "last_attempt_at": iso(health.last_attempt_at),
        "last_success_at": iso(health.last_success_at),
        "updates_count": health.updates_count,
        "schedule_count": health.schedule_count,
        "timed_schedule_count": health.timed_schedule_count,
        "timezone": health.timezone,
        "problems": list(health.problems),
        "consecutive_failures": health.consecutive_failures,
        "failure_threshold": FAILURE_THRESHOLD,
    }
