import hashlib
import hmac
import json
import re
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request, status

import config
from database import requests as db
from loader import bot
from services import parser

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_init_data(init_data: str) -> dict:
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
    if auth_date and time.time() - auth_date > 86400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram session expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Telegram user")

    return json.loads(user_raw)


async def get_miniapp_user(request: Request) -> dict:
    init_data = request.headers.get("x-telegram-init-data") or request.query_params.get("initData")
    if init_data:
        return _validate_init_data(init_data)

    if config.MINIAPP_DEV_AUTH_ENABLED:
        tg_id = request.query_params.get("tg_id")
        if tg_id:
            return {"id": int(tg_id), "username": "dev"}
        if config.ADMIN_IDS:
            return {"id": config.ADMIN_IDS[0], "username": "admin"}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram initData is required")


async def sync_miniapp_user(current_user: dict):
    return await db.upsert_user_profile(
        int(current_user["id"]),
        current_user.get("username") or current_user.get("first_name"),
        current_user.get("photo_url"),
    )


def _serialize_subscription(sub) -> dict:
    return {
        "id": sub.id,
        "title": sub.anime_title,
        "link": sub.anime_url,
        "voiceover": sub.voiceover,
        "last_episode": sub.last_episode,
        "total_episodes": sub.total_episodes,
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
        "favorite_voiceover": user.favorite_voiceover,
        "quiet_hours_enabled": user.quiet_hours_enabled,
        "quiet_hours_start": user.quiet_hours_start,
        "quiet_hours_end": user.quiet_hours_end,
        "quiet_timezone": user.quiet_timezone,
        "subscriptions_count": len(subscriptions),
    }


@router.get("/updates")
async def get_updates(voiceover: str | None = None, current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    tg_id = int(current_user["id"])
    selected_voiceover = voiceover
    if not selected_voiceover:
        selected_voiceover = await db.get_user_voiceover(tg_id) or "AniLiberty"

    updates = await parser.get_filtered(selected_voiceover, bot)
    if updates is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AnimeGO is temporarily unavailable")

    return {
        "voiceover": selected_voiceover,
        "items": updates,
    }


@router.get("/subscriptions")
async def get_subscriptions(current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    subscriptions = await db.get_user_subscriptions(int(current_user["id"]))
    return {"items": [_serialize_subscription(sub) for sub in subscriptions]}


@router.post("/subscriptions")
async def add_subscription(payload: dict, current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    title = (payload.get("title") or "").strip()
    link = (payload.get("link") or "").strip()
    episode = (payload.get("episode") or "Серия 0").strip()
    voiceover = (payload.get("voiceover") or "").strip()
    if not title or not link or not voiceover:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title, link and voiceover are required")

    info = await parser.get_anime_info(link, bot)
    total_episodes = info.get("total_episodes") if info else None
    created = await db.add_subscription(
        int(current_user["id"]),
        title,
        link,
        episode,
        voiceover,
        total_episodes,
    )
    return {"ok": True, "created": created}


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: int, current_user: dict = Depends(get_miniapp_user)):
    subscriptions = await db.get_user_subscriptions(int(current_user["id"]))
    if not any(sub.id == subscription_id for sub in subscriptions):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    await db.delete_subscription(subscription_id)
    return {"ok": True}


@router.get("/schedule")
async def get_schedule(current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    schedule = await parser.get_schedule(bot)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AnimeGO is temporarily unavailable")
    return {"days": schedule}


@router.put("/settings/voiceover")
async def update_voiceover(payload: dict, current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    voiceover = (payload.get("voiceover") or "").strip()
    if not voiceover:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voiceover is required")

    await db.update_user_voiceover(int(current_user["id"]), voiceover)
    return {"favorite_voiceover": voiceover}


@router.put("/settings/quiet-hours")
async def update_quiet_hours(payload: dict, current_user: dict = Depends(get_miniapp_user)):
    await sync_miniapp_user(current_user)
    enabled = bool(payload.get("enabled"))
    start = (payload.get("start") or "23:00").strip()
    end = (payload.get("end") or "09:00").strip()
    timezone = (payload.get("timezone") or "Europe/Moscow").strip()

    if not TIME_RE.match(start) or not TIME_RE.match(end):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time must be HH:MM")
    if not timezone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Timezone is required")

    await db.update_user_quiet_hours(int(current_user["id"]), enabled, start, end, timezone)
    return {
        "quiet_hours_enabled": enabled,
        "quiet_hours_start": start,
        "quiet_hours_end": end,
        "quiet_timezone": timezone,
    }
