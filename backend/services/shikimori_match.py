"""
Сопоставление тайтла AnimeGO с тайтлом Shikimori — без сети, только по данным.

С AnimeGO известны русское название, синонимы, английское название, тип, дата выхода и число серий
(часть может отсутствовать). Кандидат с Shikimori подходит, только если совпало хотя бы одно название;
тип, год и число серий добавляют или снимают баллы. Тайтл считается найденным, если лучший кандидат
набрал MIN_SCORE и заметно опережает второго; иначе — «не найден» или «неоднозначно», и решает админ.
"""
import datetime
import re
from dataclasses import dataclass, field

MIN_SCORE = 55
MIN_MARGIN = 15
MAX_CANDIDATES = 5

EXACT_RUSSIAN = 60
OTHER_NAME = 45
KIND_MATCH = 10
KIND_MISMATCH = -40
YEAR_MATCH = 15
YEAR_NEAR = 5
YEAR_MISMATCH = -40
EPISODES_MATCH = 10

# Тип на AnimeGO -> подходящие kind на Shikimori. Китайские веб-сериалы AnimeGO пишет «Сериалом», а Shikimori — ONA
KINDS = {
    "сериал": {"tv", "ona"},
    "тв сериал": {"tv", "ona"},
    "фильм": {"movie"},
    "ova": {"ova"},
    "ona": {"ona", "tv"},
    "спешл": {"special", "tv_special"},
    "тв спешл": {"special", "tv_special"},
    "клип": {"music", "pv", "cm"},
}

_PUNCTUATION = re.compile(r"[^\w]+", re.UNICODE)


def normalize(name: str | None) -> str:
    """«Блич: Тысячелетняя кровавая война — Бедствие» -> «блич тысячелетняя кровавая война бедствие»"""
    value = (name or "").lower().replace("ё", "е").replace("×", "x")
    return " ".join(_PUNCTUATION.sub(" ", value).replace("_", " ").split())


@dataclass
class TitleMeta:
    russian: str
    alt_names: list[str] = field(default_factory=list)
    english: str | None = None
    kind: str | None = None
    aired_on: datetime.date | None = None
    episodes: int | None = None

    def search_queries(self) -> list[str]:
        queries = [self.russian, self.english]
        return [query for index, query in enumerate(queries) if query and query not in queries[:index]]


@dataclass
class MatchResult:
    status: str  # matched | not_found | ambiguous
    shikimori_id: int | None = None
    candidates: list[dict] = field(default_factory=list)


def _year(value) -> int | None:
    if isinstance(value, datetime.date):
        return value.year
    if isinstance(value, str) and re.match(r"^\d{4}", value):
        return int(value[:4])
    return None


def candidate_names(candidate: dict) -> set[str]:
    names = [candidate.get("russian"), candidate.get("name"), candidate.get("english"), candidate.get("japanese"),
             *(candidate.get("synonyms") or [])]
    return {normalize(name) for name in names if normalize(name)}


def score(meta: TitleMeta, candidate: dict) -> int | None:
    """Баллы кандидата; None — ни одно название не совпало"""
    names = candidate_names(candidate)
    if normalize(meta.russian) and normalize(meta.russian) == normalize(candidate.get("russian")):
        total = EXACT_RUSSIAN
    elif {normalize(name) for name in [meta.russian, meta.english, *meta.alt_names] if normalize(name)} & names:
        total = OTHER_NAME
    else:
        return None

    kinds = KINDS.get(normalize(meta.kind))
    if kinds and candidate.get("kind"):
        total += KIND_MATCH if candidate["kind"] in kinds else KIND_MISMATCH

    meta_year, candidate_year = _year(meta.aired_on), _year((candidate.get("airedOn") or {}).get("date"))
    if meta_year and candidate_year:
        difference = abs(meta_year - candidate_year)
        total += YEAR_MATCH if difference == 0 else YEAR_NEAR if difference == 1 else YEAR_MISMATCH

    if meta.episodes and candidate.get("episodes") and meta.episodes == candidate["episodes"]:
        total += EPISODES_MATCH
    return total


def describe_candidate(candidate: dict, points: int | None = None) -> dict:
    """Кандидат для админки: хватает, чтобы выбрать нужный тайтл глазами"""
    return {
        "id": int(candidate["id"]),
        "name": candidate.get("name"),
        "russian": candidate.get("russian"),
        "kind": candidate.get("kind"),
        "year": _year((candidate.get("airedOn") or {}).get("date")),
        "episodes": candidate.get("episodes") or None,
        "url": candidate.get("url"),
        "score": points,
    }


def choose(meta: TitleMeta, candidates: list[dict]) -> MatchResult:
    unique = {str(candidate["id"]): candidate for candidate in candidates if candidate.get("id")}
    scored = sorted(
        ((points, candidate) for candidate in unique.values() if (points := score(meta, candidate)) is not None),
        key=lambda pair: -pair[0],
    )
    if not scored:
        return MatchResult("not_found")

    described = [describe_candidate(candidate, points) for points, candidate in scored[:MAX_CANDIDATES]]
    best_points, best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else None
    if best_points >= MIN_SCORE and (runner_up is None or best_points - runner_up >= MIN_MARGIN):
        return MatchResult("matched", int(best["id"]), described)
    return MatchResult("ambiguous", None, described)
