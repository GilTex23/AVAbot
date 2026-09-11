from aiogram import Bot
from services import forecast, parser
from services.notifier import notify_admins
from utils.antispam import AntiSpamNotify
from database import requests as db
import asyncio
import html
import logging
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


logger = logging.getLogger(__name__)
antispam_updates = AntiSpamNotify(logger)

# Тайтл вышел, а в озвучке нет новых серий дольше этого срока — подписку снимаем
STALE_SUBSCRIPTION_DAYS = 30
# Страницу тайтла с неизвестным числом серий смотрим не чаще этого срока: «?» обычно держится до конца показа
INFO_RECHECK_DAYS = 7

_status_check_lock = asyncio.Lock()


def extract_episode_number(ep_str: str) -> float:
    """Номер последней серии: 'Серия 5' -> 5, 'Серия 6.5' -> 6.5, 'Серии 1, 7-8' -> 8"""
    return parser.max_episode_number(ep_str)


def _episodes_label(episodes: list[int]) -> str:
    if len(episodes) > 1 and episodes == list(range(episodes[0], episodes[-1] + 1)):
        return f"{episodes[0]}–{episodes[-1]}"
    return ", ".join(map(str, episodes))


def _parse_time(value: str | None, fallback: dt_time) -> dt_time:
    if not value:
        return fallback
    try:
        hour, minute = value.split(":", 1)
        return dt_time(hour=int(hour), minute=int(minute))
    except (TypeError, ValueError):
        return fallback


def _is_time_inside_range(current: dt_time, start: dt_time, end: dt_time) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _is_quiet_now(user) -> bool:
    if not user or not getattr(user, "quiet_hours_enabled", False):
        return False

    try:
        zone = ZoneInfo(user.quiet_timezone or "Europe/Moscow")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Europe/Moscow")

    now = datetime.now(zone).time()
    start = _parse_time(user.quiet_hours_start, dt_time(23, 0))
    end = _parse_time(user.quiet_hours_end, dt_time(9, 0))
    return _is_time_inside_range(now, start, end)


def _is_completed(sub, total_episodes: int | None) -> bool:
    return bool(total_episodes) and extract_episode_number(sub.last_episode) >= total_episodes


async def finish_subscription(bot: Bot, sub, text: str):
    """Сообщает пользователю о снятии подписки и удаляет её (даже если сообщение не доставлено)"""
    try:
        await bot.send_message(
            sub.user_id,
            text,
            parse_mode="HTML",
            disable_notification=_is_quiet_now(sub.user),
        )
    except Exception as e:
        logger.error(f"Failed to send finish message to {sub.user_id}: {e}")

    await db.delete_subscription(sub.id)


def _completed_text(sub) -> str:
    return f"🏁 Аниме <b>{html.escape(sub.anime_title)}</b> ({html.escape(sub.voiceover)}) завершено! Удаляю из подписок."


def _stale_text(sub) -> str:
    return (
        f"💤 <b>{html.escape(sub.anime_title)}</b> ({html.escape(sub.voiceover)}): аниме уже вышло, "
        f"а новых серий в этой озвучке не было больше {STALE_SUBSCRIPTION_DAYS} дней. "
        f"Удаляю из подписок — если озвучка продолжится, подпишитесь снова."
    )


async def check_updates(bot: Bot):
    try:
        logger.debug("Starting anime check cycle...")

        home = await parser.get_home(bot)
        if not home: return

        subscriptions = await db.get_all_subscriptions()

        # История для прогноза следующей серии; сбой здесь не должен мешать уведомлениям
        try:
            await forecast.record_home(home, subscriptions)
        except Exception as e:
            logger.error(f"Failed to record episode history: {e}")

        updates = home['updates']
        if not updates or not subscriptions: return

        for sub in subscriptions:
            for update in updates:
                # Сравниваем URL
                if sub.anime_url == update['link']:

                    # Проверка озвучки
                    user_vo = sub.voiceover

                    studio_clean = update['studio'].strip().lower()
                    vo_clean = user_vo.strip().lower()

                    if user_vo == "Все" or vo_clean in studio_clean:
                        if _is_quiet_now(sub.user):
                            logger.info(f"Skipped quiet-hours notification for {sub.user_id}")
                            continue

                        # Числовое сравнение серий; выпуск может содержать несколько серий: "Серии 1, 7-8"
                        old_ep_num = extract_episode_number(sub.last_episode)
                        new_ep_num = int(extract_episode_number(update['episode']))

                        if new_ep_num > old_ep_num:
                            total_str = sub.total_episodes if sub.total_episodes else "?"
                            fresh_episodes = [ep for ep in parser.parse_episode_list(update['episode']) if ep > old_ep_num] or [new_ep_num]
                            episodes_title = "Серии" if len(fresh_episodes) > 1 else "Серия"

                            try:
                                await bot.send_message(
                                    chat_id=sub.user_id,
                                    text=(
                                        f"🔥 <b>Новая серия!</b>\n\n"
                                        f"📺 <b>{update['title']}</b>\n"
                                        f"🎬 <b>{episodes_title}:</b> {_episodes_label(fresh_episodes)} из {total_str}\n"
                                        f"🎙 <b>Озвучка:</b> {update['studio']}\n\n"
                                        f"🔗 <a href='{update['link']}'>Смотреть</a>"
                                    ),
                                    parse_mode="HTML"
                                )
                                logger.info(f"Sent update to {sub.user_id}: {update['title']} ep {new_ep_num}")

                                # Обновляем последнюю серию (одним номером, чтобы "Серии 1, 7-8" не сравнивались по первой)
                                await db.update_sub_last_episode(sub.id, f"Серия {new_ep_num}")

                            except Exception as e:
                                logger.error(f"Failed to send to {sub.user_id}: {e}")
                                continue

                            # Проверяем, не последняя ли это серия
                            if sub.total_episodes and new_ep_num >= sub.total_episodes:
                                await finish_subscription(bot, sub, _completed_text(sub))
                                logger.info(f"Anime finished and removed: {sub.anime_title}")
                                break
    except Exception as e:
        antispam_updates.failed_requests += 1
        logger.error(f"Checker updates error: {e}")
        if not antispam_updates.is_notified():
            await notify_admins(
                bot,
                f"Failed requests: {antispam_updates.failed_requests}\nОшибка в Checker Updates:\n<code>{str(e)}</code>",
                level="ERROR"
            )
            antispam_updates.set_notify_timestamp()


def is_subscriptions_check_running() -> bool:
    return _status_check_lock.locked()


async def check_subscriptions_status(bot: Bot, notify_summary: bool = False, force: bool = False):
    """
    Фоновая задача раз в день:
    - дозаполняет total_episodes: у вышедшего тайтла AnimeGO пишет вместо «13 / ?» просто «14»;
    - снимает подписки, где озвучка дошла до последней серии;
    - снимает подписки на вышедшие тайтлы без новых серий дольше STALE_SUBSCRIPTION_DAYS.
    Страница тайтла запрашивается один раз на URL и не чаще INFO_RECHECK_DAYS (force — без этого ограничения).
    """
    if _status_check_lock.locked():
        logger.info("Subscriptions status check is already running")
        return None

    async with _status_check_lock:
        stats = {"checked_urls": 0, "failed_urls": 0, "updated_totals": 0, "completed": 0, "stale": 0}
        try:
            logger.info("Starting subscriptions status check...")
            subscriptions = await db.get_all_subscriptions()
            now = datetime.utcnow()
            stale_before = now - timedelta(days=STALE_SUBSCRIPTION_DAYS)
            recheck_before = now - timedelta(days=INFO_RECHECK_DAYS)

            # Страницу нужно смотреть только если неизвестно число серий или подписка давно без серий
            url_map = {}
            for sub in subscriptions:
                if _is_completed(sub, sub.total_episodes):
                    await finish_subscription(bot, sub, _completed_text(sub))
                    stats["completed"] += 1
                    continue

                is_stale_candidate = sub.last_episode_at is not None and sub.last_episode_at < stale_before
                if sub.total_episodes is None or is_stale_candidate:
                    url_map.setdefault(sub.anime_url, []).append(sub)

            if not force:
                # Если хоть одну подписку на тайтл давно не проверяли — страница нужна всем подпискам на него
                url_map = {
                    url: subs for url, subs in url_map.items()
                    if any(sub.info_checked_at is None or sub.info_checked_at < recheck_before for sub in subs)
                }

            for url, subs in url_map.items():
                info = await parser.get_anime_info(url, bot)
                stats["checked_urls"] += 1
                if not info:
                    stats["failed_urls"] += 1
                    continue

                await db.mark_anime_info_checked(url)

                total = info.get('total_episodes')
                released = bool(info.get('status')) and "Вышел" in info['status']

                for sub in subs:
                    if total and sub.total_episodes != total:
                        logger.info(f"Found total episodes for {url}: {total}")
                        await db.update_total_episodes(sub.id, total)
                        stats["updated_totals"] += 1

                    if _is_completed(sub, total or sub.total_episodes):
                        await finish_subscription(bot, sub, _completed_text(sub))
                        stats["completed"] += 1
                    elif released and sub.last_episode_at is not None and sub.last_episode_at < stale_before:
                        await finish_subscription(bot, sub, _stale_text(sub))
                        stats["stale"] += 1
                        logger.info(f"Stale subscription removed: {sub.anime_title} ({sub.voiceover})")

            logger.info(f"Subscriptions status check finished: {stats}")
        except Exception as e:
            logger.error(f"Checker subscriptions status error: {e}")
            await notify_admins(
                bot,
                f"Ошибка в проверке статусов подписок:\n<code>{html.escape(str(e))}</code>",
                level="ERROR"
            )
            return None

        if notify_summary:
            await notify_admins(
                bot,
                "Проверка подписок завершена.\n\n"
                f"Страниц проверено: <b>{stats['checked_urls']}</b> (ошибок: {stats['failed_urls']})\n"
                f"Обновлено число серий: <b>{stats['updated_totals']}</b>\n"
                f"Завершённых снято: <b>{stats['completed']}</b>\n"
                f"Брошенных озвучек снято: <b>{stats['stale']}</b>",
                level="INFO"
            )
        return stats
