import html
import logging
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from notifier import TelegramNotifier
from sources import domovita, kufar, onliner, realt
from storage import SeenStore

BASE_DIR = Path(__file__).resolve().parent

SOURCE_FETCHERS = {
    "kufar": lambda cfg, filters: kufar.fetch(
        filters["rooms"], filters["price_max_usd"], filters.get("price_min_usd", 0)
    ),
    "onliner": lambda cfg, filters: onliner.fetch(
        filters["rooms"], filters["price_max_usd"], filters.get("price_min_usd", 0)
    ),
    "realt": lambda cfg, filters: realt.fetch(
        filters["rooms"],
        filters["price_max_usd"],
        filters.get("price_min_usd", 0),
        filters.get("currency_per_usd", {}),
    ),
    "domovita": lambda cfg, filters: domovita.fetch(
        filters["rooms"],
        filters["price_max_usd"],
        filters.get("price_min_usd", 0),
        pages=cfg.get("domovita", {}).get("fetch_pages", 2),
    ),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("apartment-bot")


def load_config():
    with open(BASE_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_message(listing):
    price = f"${listing.price_usd:,.0f}".replace(",", " ") if listing.price_usd else "цена не указана"
    rooms = f"{listing.rooms}-комн." if listing.rooms else "квартира"
    area = f", {listing.area_total:.0f} м²" if listing.area_total else ""

    source_names = {
        "kufar": "Kufar",
        "onliner": "Onliner",
        "realt": "Realt.by",
        "domovita": "Domovita",
    }

    title = html.escape(listing.title)
    address = html.escape(listing.address)
    source_name = source_names.get(listing.source, listing.source)

    return (
        f"🏠 <b>{title}</b>\n"
        f"{rooms}{area}\n"
        f"💰 {price}\n"
        f"📍 {address}\n"
        f"🔗 {listing.url}\n"
        f"Источник: {source_name}"
    )


def run_once(config, store, notifier):
    filters = config["filters"]
    rooms_values = filters["rooms"]
    price_min = filters.get("price_min_usd", 0)
    price_max = filters["price_max_usd"]

    sources_enabled = config.get("sources", {})
    fetched_by_source = {}

    for source, enabled in sources_enabled.items():
        if not enabled:
            continue
        fetcher = SOURCE_FETCHERS.get(source)
        if fetcher is None:
            log.warning("unknown source in config: %s", source)
            continue
        try:
            fetched_by_source[source] = fetcher(config, filters)
        except Exception:
            log.exception("fetch failed for source=%s", source)
            fetched_by_source[source] = []

    all_listings = [listing for listings in fetched_by_source.values() for listing in listings]

    # Дополнительная подстраховка: ещё раз проверяем фильтры на всём
    # объединённом списке, на случай если какой-то источник вернул что-то
    # за пределами запрошенного диапазона.
    rooms_set = set(rooms_values)
    filtered = [
        listing
        for listing in all_listings
        if listing.price_usd is not None
        and price_min <= listing.price_usd <= price_max
        and (listing.rooms is None or listing.rooms in rooms_set)
    ]

    # Источник, который мы видим впервые (пустой seen.json), не должен
    # вываливать в чат разом сотни существующих объявлений — считаем это
    # первоначальной загрузкой и просто запоминаем текущий срез.
    bootstrap_sources = {
        source for source in fetched_by_source if not store.has_source(source)
    }

    new_listings = [
        listing
        for listing in filtered
        if store.is_new(listing.source, listing.listing_id)
    ]
    to_notify = [listing for listing in new_listings if listing.source not in bootstrap_sources]

    for listing in filtered:
        store.mark_seen(listing.source, listing.listing_id)
    store.save()

    log.info(
        "fetched=%d filtered=%d new=%d notify=%d bootstrap=%s",
        len(all_listings),
        len(filtered),
        len(new_listings),
        len(to_notify),
        sorted(bootstrap_sources) or "-",
    )

    for listing in to_notify:
        try:
            notifier.send(format_message(listing))
        except Exception:
            log.exception("failed to send notification for %s", listing.url)
        else:
            time.sleep(1.2)  # не упираемся в лимиты Telegram API


def main():
    load_dotenv(BASE_DIR / ".env")
    config = load_config()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — создайте .env по образцу .env.example")
        sys.exit(1)

    store = SeenStore(str(BASE_DIR / "data" / "seen.json"))
    notifier = TelegramNotifier(token, chat_id)
    run_once(config, store, notifier)


if __name__ == "__main__":
    main()
