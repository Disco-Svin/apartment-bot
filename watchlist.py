"""
Отслеживание изменения цены у конкретных объявлений — добавляются либо
кнопкой "Отслеживать цену" под уведомлением (см. bot_updates.py), либо
вручную ссылкой в watchlist.yaml. Оба способа сходятся в одном файле
состояния data/watchlist_state.json (url -> {source, listing_id,
price_usd, title}) — кнопка "Остановить отслеживание" убирает запись
оттуда, даже если она изначально была добавлена вручную через yaml
(при следующей проверке она просто снова подхватится из yaml, если
ссылку не убрать и оттуда тоже — это ожидаемое поведение для "быстро
остановить" через кнопку).
"""
import html
import json
import logging
import re
from pathlib import Path

import yaml

from keyboards import track_button
from sources import domovita, kufar, onliner, realt

log = logging.getLogger("apartment-bot")

SOURCE_PATTERNS = [
    (re.compile(r"^https?://re\.kufar\.by/vi/\d+"), "kufar"),
    (re.compile(r"^https?://r\.onliner\.by/pk/apartments/\d+"), "onliner"),
    (re.compile(r"^https?://realt\.by/sale-flats/object/\d+"), "realt"),
    (re.compile(r"^https?://domovita\.by/"), "domovita"),
]

FETCHERS = {
    "kufar": lambda url, currency_per_usd: kufar.fetch_one(url),
    "onliner": lambda url, currency_per_usd: onliner.fetch_one(url),
    "realt": lambda url, currency_per_usd: realt.fetch_one(url, currency_per_usd),
    "domovita": lambda url, currency_per_usd: domovita.fetch_one(url),
}


def detect_source(url):
    for pattern, source in SOURCE_PATTERNS:
        if pattern.search(url):
            return source
    return None


def _load_yaml_urls(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [u.strip() for u in (data.get("urls") or []) if u and u.strip()]


def _load_state(path):
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0)
    tmp_path.replace(path)


def load_watchlist(yaml_path, state_path):
    yaml_urls = _load_yaml_urls(yaml_path)
    button_urls = list(_load_state(state_path).keys())

    seen = set()
    result = []
    for url in yaml_urls + button_urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def is_watched(state_path, url):
    return url in _load_state(state_path)


def add_watch(state_path, listing):
    state = _load_state(state_path)
    state[listing.url] = {
        "source": listing.source,
        "listing_id": listing.listing_id,
        "price_usd": listing.price_usd,
        "title": listing.title,
    }
    _save_state(state_path, state)


def remove_watch(state_path, url):
    state = _load_state(state_path)
    state.pop(url, None)
    _save_state(state_path, state)


def _format_usd(amount):
    return f"${amount:,.0f}".replace(",", " ")


def _format_price_change_message(listing, old_price_usd):
    direction = "выросла" if listing.price_usd > old_price_usd else "снизилась"
    diff = abs(listing.price_usd - old_price_usd)
    title = html.escape(listing.title)
    return (
        f"💸 <b>{title}</b>\n"
        f"Цена {direction} на {_format_usd(diff)}: "
        f"{_format_usd(old_price_usd)} → {_format_usd(listing.price_usd)}\n"
        f"🔗 {listing.url}"
    )


def check_watchlist(watchlist_yaml_path, state_path, notifier, currency_per_usd=None):
    urls = load_watchlist(watchlist_yaml_path, state_path)
    if not urls:
        return

    currency_per_usd = currency_per_usd or {}
    state = _load_state(state_path)

    for url in urls:
        source = detect_source(url)
        fetcher = FETCHERS.get(source)
        if fetcher is None:
            log.warning("watchlist: не распознана площадка для ссылки %s", url)
            continue

        try:
            listing = fetcher(url, currency_per_usd)
        except Exception:
            log.exception("watchlist: не удалось получить данные по %s", url)
            continue

        if listing is None or listing.price_usd is None:
            log.warning(
                "watchlist: объявление недоступно (снято с продажи?) — %s", url
            )
            continue

        prev = state.get(url)
        if prev and prev.get("price_usd") is not None and prev["price_usd"] != listing.price_usd:
            keyboard = track_button(listing.source, listing.listing_id, tracking=True)
            try:
                notifier.send(_format_price_change_message(listing, prev["price_usd"]), reply_markup=keyboard)
            except Exception:
                log.exception("watchlist: не удалось отправить уведомление по %s", url)

        state[url] = {
            "source": listing.source,
            "listing_id": listing.listing_id,
            "price_usd": listing.price_usd,
            "title": listing.title,
        }

    _save_state(state_path, state)
