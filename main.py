import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import types
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from loader import bot, dp
from handlers import user, admin
from services.logger import setup_logger
from services.checker import check_updates
from database.requests import init_db

# Настройка логгера
logger = setup_logger(config.LOG_LEVEL)

# Планировщик задач
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    logger.info("Starting up...")

    await init_db()

    dp.include_router(admin.router)
    dp.include_router(user.router)

    webhook_info = await bot.get_webhook_info()
    expected_url = config.WEBHOOK_URL + config.WEBHOOK_PATH
    if webhook_info.url != expected_url:
        await bot.set_webhook(
            url=expected_url,
            drop_pending_updates=True
        )

    scheduler.add_job(check_updates, "interval", minutes=15, args=[bot])
    scheduler.start()

    yield  # Приложение работает здесь

    # --- SHUTDOWN ---
    logger.info("Shutting down...")
    await bot.session.close()
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post(config.WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")