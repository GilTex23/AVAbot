"""
Пересобирает services/timezone_labels.py из данных CLDR (нужен babel: pip install -r requirements-dev.txt).

AnimeGO подписывает время поясом IP так же, как ICU-формат «место» (VVVV):
- страна, если в ней один пояс (или это главный пояс страны): «Хорватия», «Беларусь», «Армения»;
- город, если поясов несколько: «Москва», «Томск», «Алматы».
Дополнительно берутся общие названия метазон («Центральная Европа») и города всех поясов.
Подпись, за которой стоят пояса с разными смещениями (сейчас или после переходов на летнее время
в ближайшие годы), попадает в AMBIGUOUS_TIMEZONE_LABELS и не используется.

Запуск из backend: python -m scripts.generate_timezone_labels
"""
import datetime
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

from babel import Locale
from babel.core import get_global

OUTPUT = Path(__file__).resolve().parent.parent / "services" / "timezone_labels.py"

# primaryZones из CLDR metaZones.xml: у страны несколько поясов, но этот называется именем страны
PRIMARY_ZONES = {
    "CL": "America/Santiago", "CN": "Asia/Shanghai", "DE": "Europe/Berlin", "EC": "America/Guayaquil",
    "ES": "Europe/Madrid", "MH": "Pacific/Majuro", "MY": "Asia/Kuala_Lumpur", "NZ": "Pacific/Auckland",
    "PT": "Europe/Lisbon", "UA": "Europe/Kyiv", "UZ": "Asia/Tashkent",
}

# Подписи, которых нет в CLDR, но которые встречались на AnimeGO
MANUAL_LABELS: dict[str, str] = {}

# Пояса считаются одинаковыми, если совпадают смещения во всех точках этого интервала
CHECK_FROM = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
CHECK_YEARS = 6
CHECK_STEP = datetime.timedelta(hours=3)


def offset_signature(zone_name: str) -> tuple:
    zone = ZoneInfo(zone_name)
    steps = int(datetime.timedelta(days=365 * CHECK_YEARS) / CHECK_STEP)
    return tuple(zone.utcoffset(CHECK_FROM + CHECK_STEP * i) for i in range(steps))


def main():
    ru = Locale.parse("ru")
    aliases = get_global("zone_aliases")
    zone_territories = get_global("zone_territories")
    territory_zones = get_global("territory_zones")
    meta_zones = get_global("meta_zones")

    zones = sorted({aliases.get(name, name) for name in available_timezones()} & available_timezones())
    signatures: dict[str, tuple] = {}

    def signature(zone_name: str) -> tuple:
        if zone_name not in signatures:
            signatures[zone_name] = offset_signature(zone_name)
        return signatures[zone_name]

    candidates: dict[str, set[str]] = defaultdict(set)
    # Пояс, чей город или главный пояс страны называется этой подписью: «Москва» — Europe/Moscow, а не Europe/Minsk
    preferred: dict[str, str] = {}

    for zone_name in zones:
        info = ru.time_zones.get(zone_name, {})
        metazone = meta_zones.get(zone_name)
        metazone_info = ru.meta_zones.get(metazone, {}) if metazone else {}

        city = info.get("city") or metazone_info.get("city")
        if city:
            candidates[city].add(zone_name)
            preferred.setdefault(city, zone_name)

        territory = zone_territories.get(zone_name)
        if territory and territory in ru.territories:
            country_zones = [zone for zone in territory_zones.get(territory, []) if zone in available_timezones()]
            same_offsets = len({signature(zone) for zone in country_zones}) == 1
            if len(country_zones) == 1 or PRIMARY_ZONES.get(territory) == zone_name or same_offsets:
                candidates[ru.territories[territory]].add(zone_name)
                if PRIMARY_ZONES.get(territory) == zone_name:
                    preferred[ru.territories[territory]] = zone_name

        generic = info.get("long", {}).get("generic") or metazone_info.get("long", {}).get("generic")
        if generic:
            candidates[generic].add(zone_name)

    for label, zone_name in MANUAL_LABELS.items():
        candidates[label] = {zone_name}

    labels: dict[str, str] = {}
    ambiguous: set[str] = set()
    for label, label_zones in candidates.items():
        if len({signature(zone) for zone in label_zones}) == 1:
            labels[label] = preferred.get(label) if preferred.get(label) in label_zones else min(label_zones)
        else:
            ambiguous.add(label)

    write(labels, ambiguous)
    print(f"{len(labels)} labels, {len(ambiguous)} ambiguous -> {OUTPUT}")


def write(labels: dict[str, str], ambiguous: set[str]):
    lines = [
        '"""',
        "Русские названия часовых поясов, которыми AnimeGO подписывает время: «16:00 (Москва)», «(Хорватия)».",
        "",
        "AnimeGO показывает время в поясе того IP, с которого пришёл запрос, а прокси ScraperAPI каждый раз разные.",
        "Подпись — страна, если в ней один пояс, иначе город; плюс общие названия метазон CLDR.",
        "За подписями из AMBIGUOUS_TIMEZONE_LABELS стоят пояса с разными смещениями — время с таких страниц не используется.",
        "",
        "Файл сгенерирован scripts/generate_timezone_labels.py — не правьте руками:",
        "новые подписи добавляйте в MANUAL_LABELS генератора и пересобирайте.",
        '"""',
        "",
        "TIMEZONE_LABELS = {",
    ]
    lines += [f"    {label!r}: {zone!r}," for label, zone in sorted(labels.items())]
    lines += [
        "}",
        "",
        "# За этими подписями стоят пояса с разными смещениями — время с такой страницы не используется",
        "AMBIGUOUS_TIMEZONE_LABELS = frozenset({",
    ]
    lines += [f"    {label!r}," for label in sorted(ambiguous)]
    lines += ["})", ""]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
