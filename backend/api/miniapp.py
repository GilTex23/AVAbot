import hashlib
import hmac
import json
import logging
import re
import time
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, status

import config
from database import requests as db
from loader import bot
from services import anime_titles, forecast, parser, shikimori_sync, stats, voiceovers
from services.subscription_rules import subscription_block_reason

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validate_init_data(init_data: str, max_age_seconds: int = 86400) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telegram hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram signature")

    auth_date = int(pairs.get("auth_date", "0") or 0)
    if time.time() - auth_date > max_age_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram session expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telegram user")

    return json.loads(user_raw)


def _resolve_miniapp_user(request: Request) -> dict:
    init_data = (
        request.headers.get("x-telegram-init-data")
        or request.query_params.get("initData")
        or request.query_params.get("tgWebAppData")
    )
    if init_data:
        return validate_init_data(init_data)

    if config.MINIAPP_DEV_AUTH_ENABLED:
        tg_id = request.query_params.get("tg_id")
        if tg_id:
            return {"id": int(tg_id), "username": "dev"}
        if config.ADMIN_IDS:
            return {"id": config.ADMIN_IDS[0], "username": "admin"}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram initData is required")


async def get_miniapp_user(request: Request) -> dict:
    user = _resolve_miniapp_user(request)
    # Для статистики: запросы к AnimeGO из этого запроса — «мини-апп», пользователь сегодня активен
    stats.set_source(stats.SOURCE_MINIAPP)
    await stats.mark_active(int(user["id"]), stats.SOURCE_MINIAPP)
    return user


async def sync_miniapp_user(current_user: dict):
    return await db.upsert_user_profile(
        int(current_user["id"]),
        current_user.get("username") or current_user.get("first_name"),
        current_user.get("photo_url"),
    )


def _serialize_subscription(sub, next_episode: dict | None = None) -> dict:
    return {
        "id": sub.id,
        "title": sub.anime_title,
        "link": sub.anime_url,
        "poster_url": sub.poster_url,
        "voiceover": sub.voiceover,
        "last_episode": sub.last_episode,
        "total_episodes": sub.total_episodes,
        "next_episode": next_episode,
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_miniapp_user)):
    tg_id = int(current_user["id"])
    user = await sync_miniapp_user(current_user)
    subscriptions = await db.get_user_subscriptions(tg_id)

    return {
        "id": tg_id,
        "username": user.username,
        "photo_url": user.photo_url,
        "favorite_voiceovers": list(user.favorite_voiceovers or []),
        "quiet_hours_enabled": user.quiet_hours_enabled,
        "quiet_hours_start": user.quiet_hours_start,
        "quiet_hours_end": user.quiet_hours_end,
        "quiet_timezone": user.quiet_timezone,
        "subscriptions_count": len(subscriptions),
        "is_admin": tg_id in config.ADMIN_IDS,
    }


@router.get("/updates")
async def get_updates(voiceover: str | None = None, current_user: dict = Depends(get_miniapp_user)):
    """
    Свежие серии. Без voiceover — по любимым озвучкам пользователя (нет любимых — все),
    voiceover=«Все» — все серии, иначе — одна озвучка. studios — озвучки, которые сейчас есть в ленте.
    """
    user = await sync_miniapp_user(current_user)
    favorites = list(user.favorite_voiceovers or [])

    updates = await parser.get_updates(bot)
    if updates is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AnimeGO is temporarily unavailable")

    voiceover = (voiceover or "").strip()
    if not voiceover:
        mode, names = "favorites", favorites
    elif voiceover == voiceovers.ALL_VOICEOVERS:
        mode, names = "all", []
    else:
        mode, names = "voiceover", [voiceover]

    return {
        "filter": mode,
        "voiceover": voiceover or None,
        "favorites": favorites,
        "items": voiceovers.filter_updates(updates, names),
        "studios": voiceovers.studios_in(updates),
    }


@router.get("/voiceovers")
async def get_voiceovers(current_user: dict = Depends(get_miniapp_user)):
    """Справочник озвучек, популярные первыми"""
    await sync_miniapp_user(current_user)
    return {
        "items": [
            {"id": item["id"], "name": item["name"], "releases": item["releases"], "subscriptions": item["subscriptions"]}
            for item in await voiceovers.catalog()
        ],
        "popular_days": voiceovers.POPULAR_DAYS,
    }


@router.get("/subscriptions")
async def get_subscriptions(current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    subscriptions = await db.get_user_subscriptions(int(current_user["id"]))
    try:
        forecasts = await forecast.build_forecasts(subscriptions)
    except Exception as e:
        # Прогноз — дополнение: без него список подписок всё равно должен открываться
        logger.error(f"Failed to build episode forecasts: {e}")
        forecasts = {}
    return {"items": [_serialize_subscription(sub, forecasts.get(sub.id)) for sub in subscriptions]}


@router.get("/my-week")
async def get_my_week(current_user: dict = Depends(get_miniapp_user)):
    """Серии по подпискам, которые ожидаются в ближайшие 7 дней, и задерживающиеся — по прогнозу"""
    await sync_miniapp_user(current_user)
    subscriptions = await db.get_user_subscriptions(int(current_user["id"]))
    by_id = {sub.id: sub for sub in subscriptions}
    week = await forecast.build_week(subscriptions)
    return {
        "items": [
            {**_serialize_subscription(by_id[item["subscription_id"]]), "forecast": item["forecast"]}
            for item in week
        ]
    }


@router.post("/subscriptions")
async def add_subscription(payload: dict, current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    title = (payload.get("title") or "").strip()
    link = (payload.get("link") or "").strip()
    episode = (payload.get("episode") or "Серия 0").strip()
    voiceover = (payload.get("voiceover") or "").strip()
    poster_url = (payload.get("poster_url") or "").strip() or None
    if not title or not link or not voiceover:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title, link and voiceover are required")

    # Страница тайтла обычно уже в кэше: её только что открывали, чтобы выбрать озвучку или показать обновления
    info = await parser.get_anime_info(link, bot)
    reason = subscription_block_reason(info, episode)
    if reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    if parser.max_episode_number(episode) == 0:
        # Подписка из расписания: уже вышедшие в озвучке серии не присылаем — начинаем с последней из истории ленты
        releases = await db.get_episode_releases({link})
        last_known = max((release.episode for release in releases if voiceovers.matches(voiceover, release.studio)), default=None)
        if last_known:
            episode = f"Серия {last_known}"

    payload_total = payload.get("total_episodes")
    total_episodes = payload_total if payload_total is not None else (info.get("total_episodes") if info else None)
    created = await db.add_subscription(
        int(current_user["id"]),
        title,
        link,
        episode,
        voiceover,
        total_episodes,
        poster_url,
    )
    if created:
        await stats.increment("subscriptions.created", stats.SOURCE_MINIAPP)
        await anime_titles.remember([{"title": title, "link": link, "poster_url": poster_url}])
        shikimori_sync.kick(link)
    return {"ok": True, "created": created}


@router.get("/anime-details")
async def get_anime_details(link: str, current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    info = await parser.get_anime_details(link, bot)
    if not info:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Anime details are temporarily unavailable")

    return {
        "type": info.get("type"),
        "status": info.get("status"),
        "total_episodes": info.get("total_episodes"),
        "voiceovers": info.get("available_voiceovers") or [],
    }


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: int, current_user: dict = Depends(get_miniapp_user)):
    subscriptions = await db.get_user_subscriptions(int(current_user["id"]))
    if not any(sub.id == subscription_id for sub in subscriptions):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    await db.delete_subscription(subscription_id)
    await stats.increment("subscriptions.deleted", stats.SOURCE_MINIAPP)
    return {"ok": True}


@router.get("/schedule")
async def get_schedule(current_user: dict = Depends(get_miniapp_user)):
    user = await sync_miniapp_user(current_user)
    schedule = await parser.get_schedule(bot)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AnimeGO is temporarily unavailable")
    return {"days": parser.localize_schedule(schedule, parser.zone_or_moscow(user.quiet_timezone))}


def _valid_timezone(value) -> str:
    timezone = (value or "").strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown timezone")
    return timezone


@router.put("/settings/timezone")
async def update_timezone(payload: dict, current_user: dict = Depends(get_miniapp_user)):
    """Часовой пояс пользователя: расписание, прогнозы и тихие часы"""
    await sync_miniapp_user(current_user)
    timezone = _valid_timezone(payload.get("timezone"))
    await db.update_user_timezone(int(current_user["id"]), timezone)
    return {"quiet_timezone": timezone}


@router.put("/settings/voiceovers")
async def update_favorite_voiceovers(payload: dict, current_user: dict = Depends(get_miniapp_user)):
    """Любимые озвучки — названия из справочника; пустой список — все озвучки"""
    await sync_miniapp_user(current_user)
    names = payload.get("voiceovers")
    if not isinstance(names, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voiceovers must be a list")
    try:
        favorites = await voiceovers.validate_favorites(names)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await db.update_user_favorite_voiceovers(int(current_user["id"]), favorites)
    return {"favorite_voiceovers": favorites}


@router.put("/settings/quiet-hours")
async def update_quiet_hours(payload: dict, current_user: dict = Depends(get_miniapp_user)):
    user = await sync_miniapp_user(current_user)
    enabled = bool(payload.get("enabled"))
    start = (payload.get("start") or "23:00").strip()
    end = (payload.get("end") or "09:00").strip()
    # Пояс теперь настраивается отдельно; старые клиенты ещё присылают его вместе с тихими часами
    timezone = _valid_timezone(payload["timezone"]) if payload.get("timezone") else user.quiet_timezone

    if not TIME_RE.match(start) or not TIME_RE.match(end):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time must be HH:MM")

    await db.update_user_quiet_hours(int(current_user["id"]), enabled, start, end, timezone)
    return {
        "quiet_hours_enabled": enabled,
        "quiet_hours_start": start,
        "quiet_hours_end": end,
        "quiet_timezone": timezone,
    }
