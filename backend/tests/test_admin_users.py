"""Админка: пользователи, их настройки и подписки."""
import datetime as dt

from sqlalchemy import update

from conftest import ADMIN_ID
from database.models import Subscription, User
from test_db_flows import add_sub, client, get_sub, init_data  # noqa: F401 — фикстура client


async def test_users_list_search_and_details(database, client):
    headers = init_data(ADMIN_ID)
    today = dt.datetime.utcnow().date()
    first = await add_sub(database, 501, "Первый тайтл", "https://animego.me/anime/one-1", "AniDUB", "Серия 3", total=12)
    await add_sub(database, 501, "Второй тайтл", "https://yummyani.me/catalog/item/two", "AniLiberty", "Серия 5")
    await add_sub(database, 502, "Чужой", "https://animego.me/anime/three-3", "AniDUB", "Серия 1")
    await database.add_user(503, "silent_user")
    async with database.async_session() as session:
        await session.execute(update(Subscription).where(Subscription.anime_url.like("%yummyani%")).values(source="yummy", source_id="2"))
        await session.execute(update(User).where(User.id == 501).values(favorite_voiceovers=["AniDUB"], quiet_hours_enabled=True))
        await session.commit()
    await database.record_user_activity(502, "bot", day=today)
    await database.record_user_activity(501, "miniapp", day=today - dt.timedelta(days=3))
    await database.record_user_activity(501, "bot", day=today - dt.timedelta(days=40))

    listing = (await client.get("/api/miniapp/admin/users", headers=headers)).json()
    assert listing["total"] == 3
    # Недавно активные — первыми, без активности — в конце
    assert [user["id"] for user in listing["items"]] == [502, 501, 503]
    user_501 = listing["items"][1]
    assert (user_501["subscriptions"], user_501["yummy_subscriptions"], user_501["last_active"]) == (2, 1, (today - dt.timedelta(days=3)).isoformat())

    by_name = (await client.get("/api/miniapp/admin/users", params={"q": "@SILENT"}, headers=headers)).json()
    assert [user["id"] for user in by_name["items"]] == [503]
    by_id = (await client.get("/api/miniapp/admin/users", params={"q": "502"}, headers=headers)).json()
    assert [user["id"] for user in by_id["items"]] == [502]
    page = (await client.get("/api/miniapp/admin/users", params={"offset": 2, "limit": 1}, headers=headers)).json()
    assert page["total"] == 3 and [user["id"] for user in page["items"]] == [503]

    details = (await client.get("/api/miniapp/admin/users/501", headers=headers)).json()
    assert details["favorite_voiceovers"] == ["AniDUB"] and details["quiet_hours"]["enabled"] is True
    # Активность за 30 дней: день 40-дневной давности не считается
    assert details["active_days"] == 1 and details["activity_sources"] == ["miniapp"]
    assert [(sub["title"], sub["source"]) for sub in details["subscriptions_list"]] == [("Второй тайтл", "yummy"), ("Первый тайтл", "animego")]
    assert (await client.get("/api/miniapp/admin/users/999", headers=headers)).status_code == 404

    deleted = await client.delete(f"/api/miniapp/admin/subscriptions/{first}", headers=headers)
    assert deleted.status_code == 200 and [sub["title"] for sub in deleted.json()["subscriptions_list"]] == ["Второй тайтл"]
    assert await get_sub(database, first) is None
    assert (await client.delete(f"/api/miniapp/admin/subscriptions/{first}", headers=headers)).status_code == 404


async def test_users_admin_only(database, client):
    for path in ("/api/miniapp/admin/users", "/api/miniapp/admin/users/1"):
        assert (await client.get(path, headers=init_data(12345))).status_code == 403
    assert (await client.delete("/api/miniapp/admin/subscriptions/1", headers=init_data(12345))).status_code == 403
