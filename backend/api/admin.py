import asyncio
import datetime
import re

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, status

import config
from api.miniapp import validate_init_data
from database import requests as db
from loader import bot
from services import checker, health, scraper_keys

router = APIRouter(prefix="/api/miniapp/admin", tags=["miniapp-admin"])

# Админка принимает только свежий подписанный initData — dev-авторизация здесь не работает
ADMIN_INIT_DATA_MAX_AGE_SECONDS = 3600
USAGE_DAYS = 14
BURN_RATE_DAYS = 7
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
API_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")

_background_tasks: set[asyncio.Task] = set()


async def require_admin(request: Request) -> dict:
    init_data = request.headers.get("x-telegram-init-data")
    if not init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram initData is required")

    user = validate_init_data(init_data, ADMIN_INIT_DATA_MAX_AGE_SECONDS)
    if int(user["id"]) not in config.ADMIN_IDS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def _iso(value: datetime.datetime | None) -> str | None:
    # В БД naive UTC; суффикс Z, чтобы фронт не принял время за локальное
    return value.isoformat() + "Z" if value else None


def _serialize_key(row) -> dict:
    api_key = scraper_keys.decrypt_key(row.key_encrypted)
    return {
        "id": row.id,
        "name": row.name,
        "email": row.email,
        "masked_key": scraper_keys.mask_key(api_key),
        "decrypt_error": api_key is None,
        "enabled": row.enabled,
        "status": row.status,
        "request_count": row.request_count,
        "request_limit": row.request_limit,
        "failed_request_count": row.failed_request_count,
        "remaining": scraper_keys.remaining_credits(row.request_count, row.request_limit),
        "subscription_date": _iso(row.subscription_date),
        "last_checked_at": _iso(row.last_checked_at),
        "last_used_at": _iso(row.last_used_at),
        "last_error": row.last_error,
        "last_error_at": _iso(row.last_error_at),
        "created_at": _iso(row.created_at),
    }


async def _overview() -> dict:
    rows = await db.get_scraper_keys()

    today = datetime.datetime.utcnow().date()
    first_day = today - datetime.timedelta(days=USAGE_DAYS - 1)
    usage_by_day = {
        day: (int(success or 0), int(failed or 0))
        for day, success, failed in await db.get_scraper_usage(first_day)
    }
    usage = []
    for offset in range(USAGE_DAYS):
        day = first_day + datetime.timedelta(days=offset)
        success, failed = usage_by_day.get(day, (0, 0))
        usage.append({"day": day.isoformat(), "success": success, "failed": failed})

    usable = [row for row in rows if row.enabled and row.status in scraper_keys.USABLE_STATUSES]
    remaining = sum(scraper_keys.remaining_credits(row.request_count, row.request_limit) or 0 for row in usable)
    limit = sum(row.request_limit or 0 for row in usable)

    # Средний расход по полным дням (без сегодняшнего), начиная с первого дня, где есть статистика
    history = usage[-(BURN_RATE_DAYS + 1):-1]
    first_with_data = next((index for index, item in enumerate(history) if item["success"] or item["failed"]), None)
    avg_daily = None
    if first_with_data is not None:
        window = history[first_with_data:]
        avg_daily = sum(item["success"] for item in window) / len(window)

    return {
        "keys": [_serialize_key(row) for row in rows],
        "usage": usage,
        "summary": {
            "total_keys": len(rows),
            "usable_keys": len(usable),
            "remaining": remaining,
            "limit": limit,
            "avg_daily": round(avg_daily, 1) if avg_daily is not None else None,
            "days_left": round(remaining / avg_daily, 1) if avg_daily else None,
        },
        "subscriptions_check_running": checker.is_subscriptions_check_running(),
        "parser_health": health.snapshot(),
    }


def _clean_name(value) -> str:
    name = (value or "").strip()
    if not name or len(name) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название ключа: от 1 до 64 символов")
    return name


def _clean_email(value) -> str | None:
    email = (value or "").strip()
    if not email:
        return None
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректная почта")
    return email


async def _get_key_or_404(key_id: int):
    row = await db.get_scraper_key(key_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ключ не найден")
    return row


@router.get("/keys")
async def get_keys(_: dict = Depends(require_admin)):
    return await _overview()


@router.post("/keys")
async def add_key(payload: dict, _: dict = Depends(require_admin)):
    name = _clean_name(payload.get("name"))
    email = _clean_email(payload.get("email"))
    api_key = (payload.get("key") or "").strip()
    if not API_KEY_RE.match(api_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ключ выглядит некорректно")

    rows = await db.get_scraper_keys()
    if any(scraper_keys.decrypt_key(row.key_encrypted) == api_key for row in rows):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Такой ключ уже добавлен")

    try:
        async with aiohttp.ClientSession() as session:
            status_code, data = await scraper_keys.fetch_account(api_key, session)
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось связаться с ScraperAPI, попробуйте позже")

    if status_code != 200 or not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"ScraperAPI отклонил ключ (код {status_code})")

    await db.add_scraper_key(name, email, scraper_keys.encrypt_key(api_key), **scraper_keys.account_values(data))
    await scraper_keys.key_pool.reload()
    return await _overview()


@router.patch("/keys/{key_id}")
async def update_key(key_id: int, payload: dict, _: dict = Depends(require_admin)):
    await _get_key_or_404(key_id)

    values = {}
    if "name" in payload:
        values["name"] = _clean_name(payload.get("name"))
    if "email" in payload:
        values["email"] = _clean_email(payload.get("email"))
    if "enabled" in payload:
        values["enabled"] = bool(payload.get("enabled"))

    if values:
        await db.update_scraper_key(key_id, **values)
        await scraper_keys.key_pool.reload()
    return await _overview()


@router.delete("/keys/{key_id}")
async def delete_key(key_id: int, _: dict = Depends(require_admin)):
    await _get_key_or_404(key_id)
    await db.delete_scraper_key(key_id)
    await scraper_keys.key_pool.reload()
    return await _overview()


@router.post("/keys/refresh")
async def refresh_keys(_: dict = Depends(require_admin)):
    await scraper_keys.refresh_all_keys(bot)
    return await _overview()


@router.post("/keys/{key_id}/refresh")
async def refresh_one_key(key_id: int, _: dict = Depends(require_admin)):
    await _get_key_or_404(key_id)
    async with aiohttp.ClientSession() as session:
        await scraper_keys.refresh_key(key_id, bot, session)
    await scraper_keys.key_pool.reload()
    return await _overview()


@router.post("/subscriptions/check")
async def run_subscriptions_check(_: dict = Depends(require_admin)):
    if checker.is_subscriptions_check_running():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Проверка подписок уже идёт")

    # Полная проверка без недельного ограничения; может идти долго, итог придёт админам в Telegram
    task = asyncio.create_task(checker.check_subscriptions_status(bot, notify_summary=True, force=True))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"started": True}
