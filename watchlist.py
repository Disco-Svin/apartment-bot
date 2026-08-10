"""
Отслеживание изменения цены у конкретных, вручную выбранных объявлений
(в отличие от main.py, который ищет НОВЫЕ объявления по фильтрам).

Список ссылок — в watchlist.yaml. Состояние (последняя известная цена
по каждой ссылке) — в data/watchlist_state.json, в том же духе, что и
storage.py для основного поиска.
"""
import html
import json
import logging
import re
from pathlib import Path

import yaml

from sources import domovita, kufar, onliner, realt

log = logging.getLogger("apartment-bot")

SOURCE_PATTERNS = [
    (re.compile(r"re\.kufar\.by/vi/\d+"), "kufar"),
    (re.compile(r"r\.onliner\.by/pk/apartments/\d+"), "onliner"),
    (re.compile(r"realt\.by/sale-flats/object/\d+"), "realt"),
    (re.compile(r"domovita\.by/"), "domovita"),
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


def load_watchlist(path):
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


def check_watchlist(watchlist_path, state_path, notifier, currency_per_usd=None):
    urls = load_watchlist(watchlist_path)
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
            try:
                notifier.send(_format_price_change_message(listing, prev["price_usd"]))
            except Exception:
                log.exception("watchlist: не удалось отправить уведомление по %s", url)

        state[url] = {"price_usd": listing.price_usd, "title": listing.title}

    _save_state(state_path, state)
