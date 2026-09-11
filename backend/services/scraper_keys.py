import asyncio
import base64
import datetime
import hashlib
import html
import logging
import time
from dataclasses import dataclass

import aiohttp
from aiogram import Bot
from cryptography.fernet import Fernet, InvalidToken

import config
from database import requests as db
from services import stats
from services.notifier import notify_admins


logger = logging.getLogger(__name__)

ACCOUNT_URL = 'https://api.scraperapi.com/account'
LOW_CREDITS_RATIO = 0.1

STATUS_ACTIVE = "active"
STATUS_LOW = "low"
STATUS_EXHAUSTED = "exhausted"
STATUS_INVALID = "invalid"
USABLE_STATUSES = (STATUS_ACTIVE, STATUS_LOW)

# Любая строка из .env превращается в валидный 32-байтный ключ Fernet
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(config.SCRAPER_KEYS_SECRET.encode()).digest()))


def encrypt_key(api_key: str) -> str:
    return _fernet.encrypt(api_key.encode()).decode()


def decrypt_key(key_encrypted: str) -> str | None:
    try:
        return _fernet.decrypt(key_encrypted.encode()).decode()
    except InvalidToken:
        return None


def mask_key(api_key: str | None) -> str:
    if not api_key:
        return "не расшифровывается"
    if len(api_key) <= 8:
        return "••••"
    return f"{api_key[:4]}…{api_key[-4:]}"


def remaining_credits(count: int | None, limit: int | None) -> int | None:
    if not limit:
        return None
    return max(limit - (count or 0), 0)


def status_from_counts(count: int | None, limit: int | None) -> str:
    remaining = remaining_credits(count, limit)
    if remaining is None:
        return STATUS_ACTIVE
    if remaining <= 0:
        return STATUS_EXHAUSTED
    if remaining < limit * LOW_CREDITS_RATIO:
        return STATUS_LOW
    return STATUS_ACTIVE


def _parse_api_datetime(value) -> datetime.datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


@dataclass
class PoolKey:
    id: int
    name: str
    email: str | None
    api_key: str
    status: str
    request_limit: int | None
    remaining: int | None
    last_used: float = 0.0


class KeyPool:
    """Ключи ScraperAPI в памяти: выбор ключа для запроса и учёт результатов"""

    def __init__(self):
        self._keys: dict[int, PoolKey] = {}

    async def reload(self):
        rows = await db.get_scraper_keys()
        keys = {}
        for row in rows:
            if not row.enabled:
                continue
            api_key = decrypt_key(row.key_encrypted)
            if api_key is None:
                logger.error(f"Cannot decrypt ScraperAPI key '{row.name}'. Was SCRAPER_KEYS_SECRET changed?")
                continue
            previous = self._keys.get(row.id)
            keys[row.id] = PoolKey(
                id=row.id,
                name=row.name,
                email=row.email,
                api_key=api_key,
                status=row.status,
                request_limit=row.request_limit,
                remaining=remaining_credits(row.request_count, row.request_limit),
                last_used=previous.last_used if previous else 0.0,
            )
        self._keys = keys

    def usable_count(self) -> int:
        return sum(1 for key in self._keys.values() if key.status in USABLE_STATUSES)

    def pick(self, exclude: set[int]) -> PoolKey | None:
        """Ключ с наибольшим остатком кредитов; при равенстве — тот, что дольше не использовался"""
        candidates = [
            key for key in self._keys.values()
            if key.status in USABLE_STATUSES and key.id not in exclude
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda key: (key.remaining or 0, -key.last_used))

    async def report_success(self, key: PoolKey, bot: Bot | None):
        key.last_used = time.monotonic()
        try:
            await db.record_scraper_key_usage(key.id, success=True)
        except Exception as e:
            logger.error(f"Failed to record ScraperAPI usage for '{key.name}': {e}")

        if key.remaining is None:
            return
        key.remaining = max(key.remaining - 1, 0)
        # Исчерпание по локальной оценке не ставим: это решит ответ 403 или /account
        if key.status == STATUS_ACTIVE and key.remaining < key.request_limit * LOW_CREDITS_RATIO:
            await set_key_status(key.id, STATUS_LOW, bot)

    async def report_failure(self, key: PoolKey, error: str, bot: Bot | None, status: str | None = None):
        key.last_used = time.monotonic()
        try:
            await db.record_scraper_key_usage(key.id, success=False, error=error)
        except Exception as e:
            logger.error(f"Failed to record ScraperAPI error for '{key.name}': {e}")

        if status and status != key.status:
            await set_key_status(key.id, status, bot, reason=error)


key_pool = KeyPool()


def _key_label(name: str, email: str | None) -> str:
    label = f"«{html.escape(name)}»"
    if email:
        label += f" ({html.escape(email)})"
    return label


async def _notify_transition(bot: Bot | None, name: str, email: str | None, old: str, new: str, reason: str | None = None):
    if old == new:
        return
    await stats.increment("keys.status_change", new)
    if bot is None:
        return

    label = _key_label(name, email)
    if new == STATUS_INVALID:
        text, level = f"🔑 Ключ ScraperAPI {label} недействителен и выведен из ротации.", "ERROR"
    elif new == STATUS_EXHAUSTED:
        text, level = f"🔑 Ключ ScraperAPI {label} исчерпал лимит кредитов. Вернётся в ротацию после сброса.", "WARNING"
    elif new == STATUS_LOW:
        text, level = f"🔑 У ключа ScraperAPI {label} осталось меньше {int(LOW_CREDITS_RATIO * 100)}% кредитов.", "WARNING"
    elif old in (STATUS_EXHAUSTED, STATUS_INVALID):
        text, level = f"🔑 Ключ ScraperAPI {label} снова работает.", "INFO"
    else:
        return

    if reason:
        text += f"\n\n<b>Ответ:</b> <code>{html.escape(reason[:300])}</code>"
    text += f"\n\nРабочих ключей в ротации: <b>{key_pool.usable_count()}</b>"
    await notify_admins(bot, text, level=level)


async def set_key_status(key_id: int, status: str, bot: Bot | None, reason: str | None = None):
    row = await db.get_scraper_key(key_id)
    if row is None or row.status == status:
        return
    await db.update_scraper_key(key_id, status=status)
    await key_pool.reload()
    logger.warning(f"ScraperAPI key '{row.name}' status: {row.status} -> {status}")
    await _notify_transition(bot, row.name, row.email, row.status, status, reason)


async def fetch_account(api_key: str, session: aiohttp.ClientSession) -> tuple[int, dict | str]:
    """Запрос к /account — не расходует кредиты"""
    async with session.get(ACCOUNT_URL, params={'api_key': api_key}, timeout=aiohttp.ClientTimeout(total=20)) as response:
        if response.status == 200:
            return response.status, await response.json(content_type=None)
        return response.status, (await response.text())[:300]


def account_values(data: dict) -> dict:
    count = int(data.get("requestCount") or 0)
    limit = int(data.get("requestLimit") or 0) or None
    failed = data.get("failedRequestCount")
    return {
        "request_count": count,
        "request_limit": limit,
        "failed_request_count": int(failed) if failed is not None else None,
        "subscription_date": _parse_api_datetime(data.get("subscriptionDate")),
        "status": status_from_counts(count, limit),
        "last_checked_at": datetime.datetime.utcnow(),
    }


async def refresh_key(key_id: int, bot: Bot | None, session: aiohttp.ClientSession):
    row = await db.get_scraper_key(key_id)
    if row is None:
        return

    now = datetime.datetime.utcnow()
    api_key = decrypt_key(row.key_encrypted)
    if api_key is None:
        await db.update_scraper_key(
            key_id,
            last_error="Не удалось расшифровать ключ: SCRAPER_KEYS_SECRET изменился?",
            last_error_at=now,
            last_checked_at=now,
        )
        return

    try:
        status_code, data = await fetch_account(api_key, session)
    except Exception as e:
        logger.error(f"ScraperAPI account check failed for '{row.name}': {e}")
        await db.update_scraper_key(key_id, last_error=f"Account check: {e}"[:500], last_error_at=now, last_checked_at=now)
        return

    if status_code == 200 and isinstance(data, dict):
        values = account_values(data)
    elif status_code == 401:
        values = {"status": STATUS_INVALID, "last_error": f"401: {data}", "last_error_at": now, "last_checked_at": now}
    elif status_code == 403:
        values = {"status": STATUS_EXHAUSTED, "last_error": f"403: {data}", "last_error_at": now, "last_checked_at": now}
    else:
        values = {"last_error": f"Account check {status_code}: {data}"[:500], "last_error_at": now, "last_checked_at": now}

    await db.update_scraper_key(key_id, **values)
    logger.info(f"ScraperAPI key '{row.name}' checked: {status_code}")

    new_status = values.get("status", row.status)
    if new_status != row.status:
        await key_pool.reload()
        await _notify_transition(bot, row.name, row.email, row.status, new_status, values.get("last_error"))


async def refresh_all_keys(bot: Bot | None):
    rows = await db.get_scraper_keys()
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*(refresh_key(row.id, bot, session) for row in rows))
    await key_pool.reload()
    # Для графика остатка кредитов во времени
    await stats.record_key_snapshots(await db.get_scraper_keys())


async def bootstrap():
    """Однократный импорт ключей из .env в пустую таблицу и загрузка пула"""
    if config.SCRAPER_API_KEYS and await db.count_scraper_keys() == 0:
        for name, api_key in config.SCRAPER_API_KEYS:
            await db.add_scraper_key(name=name, email=None, key_encrypted=encrypt_key(api_key))
        logger.warning(
            f"Imported {len(config.SCRAPER_API_KEYS)} ScraperAPI keys from SCRAPER_API_KEYS. "
            "Keys are now managed in the mini app admin page; the env variable can be removed."
        )
    await key_pool.reload()
    logger.info(f"ScraperAPI key pool loaded: {key_pool.usable_count()} usable keys")
