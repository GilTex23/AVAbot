import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from aiogram import types
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqladmin import Admin

import config
from loader import bot, dp
from api.miniapp import router as miniapp_router
from handlers import user, admin, other
from middlewares.callback import CallbackAnswerMiddleware
from services.logger import setup_logger
from services.checker import check_updates, check_missing_episodes_info
from services.notifier import notify_admins
from database.requests import init_db, engine

from services.admin_panel import authentication_backend, UserAdmin, SubscriptionAdmin

logger = setup_logger(config.LOG_LEVEL)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    logger.info("––– Starting up... –––")

    await init_db()
    logger.info("Database initialize successfully")

    dp.callback_query.middleware(CallbackAnswerMiddleware())
    logger.info("Callback query middleware installed successfully")

    dp.include_router(admin.router)
    logger.info("Admin router included successfully")
    dp.include_router(user.router)
    logger.info("User router included successfully")
    dp.include_router(other.router)
    logger.info("Other router included successfully")

    webhook_info = await bot.get_webhook_info()
    expected_url = config.WEBHOOK_URL + config.WEBHOOK_PATH
    if webhook_info.url != expected_url:
        await bot.set_webhook(
            url=expected_url,
            drop_pending_updates=True
        )
        logger.info("New webhook has been installed")
    logger.info("Webhook ready")

    scheduler.add_job(check_updates, "interval", minutes=20, args=[bot], id="updates_checker", replace_existing=True)
    scheduler.add_job(check_missing_episodes_info, "cron", hour=21, minute=0, args=[bot])
    scheduler.start()

    await notify_admins(bot, f"Бот успешно запущен и готов к работе!", level="INFO")

    yield

    # --- SHUTDOWN ---
    logger.info("––– Shutting down... –––")
    await notify_admins(bot, f"Бот останавливается (Shutdown signal)", level="WARNING")
    await bot.session.close()
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.include_router(miniapp_router)

if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/miniapp/assets", StaticFiles(directory=assets_dir), name="miniapp-assets")


@app.get("/miniapp", include_in_schema=False)
async def miniapp_index():
    index_path = FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return PlainTextResponse("Mini App frontend is not built yet.", status_code=404)


@app.get("/miniapp/{path:path}", include_in_schema=False)
async def miniapp_spa(path: str):
    index_path = FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return PlainTextResponse("Mini App frontend is not built yet.", status_code=404)

admin_panel = Admin(app, engine, authentication_backend=authentication_backend, title="AnimeBot Admin")
admin_panel.add_view(UserAdmin)
admin_panel.add_view(SubscriptionAdmin)


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    """
    Запрещаем индексацию админ-панели и пути вебхука поисковыми ботами.
    """
    lines = [
        "User-agent: *",
        "Disallow: /admin",
        "Disallow: /docs",
        f"Disallow: {config.WEBHOOK_PATH}"
    ]
    return "\n".join(lines)


@app.post(config.WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
