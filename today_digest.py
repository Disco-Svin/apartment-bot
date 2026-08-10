"""
Разовая рассылка: объявления, добавленные СЕГОДНЯ (по времени Минска),
среди тех, что видны в текущей выдаче источников. Не трогает
data/seen.json — можно гонять сколько угодно раз, на дедупликацию
основного поиска это не влияет.

kufar/onliner/realt используют дату создания напрямую; domovita —
поле date_reception. У realt.by и domovita.by нет надёжной серверной
сортировки по дате (см. комментарии в sources/realt.py), поэтому
"сегодняшние" там ищутся в пределах того среза, который вообще
попадает в обычный fetch() — теоретически что-то может быть пропущено.

Запуск: python today_digest.py
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from main import format_message, load_config, parse_chat_ids
from notifier import TelegramNotifier
from sources import domovita, kufar, onliner, realt

BASE_DIR = Path(__file__).resolve().parent
MINSK_TZ = timezone(timedelta(hours=3))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("apartment-bot")


def to_minsk_date(created_at, source):
    if not created_at:
        return None
    try:
        if source == "domovita":
            # naive-строка вида "2026-07-16 03:28:07", уже во времени Минска
            return datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").date()
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return dt.astimezone(MINSK_TZ).date()
    except ValueError:
        return None


def main():
    load_dotenv(BASE_DIR / ".env")
    config = load_config()
    filters = config["filters"]
    rooms = filters["rooms"]
    price_max = filters["price_max_usd"]
    price_min = filters.get("price_min_usd", 0)
    fx = filters.get("currency_per_usd", {})

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_ids = parse_chat_ids(os.environ.get("TELEGRAM_CHAT_IDS", ""))
    if not token or not chat_ids:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS не заданы")
        return

    all_listings = []
    all_listings += kufar.fetch(rooms, price_max, price_min)
    all_listings += onliner.fetch(rooms, price_max, price_min)
    all_listings += realt.fetch(rooms, price_max, price_min, fx)
    all_listings += domovita.fetch(
        rooms, price_max, price_min, pages=config.get("domovita", {}).get("fetch_pages", 2)
    )

    today = datetime.now(MINSK_TZ).date()
    today_listings = [l for l in all_listings if to_minsk_date(l.created_at, l.source) == today]

    log.info("fetched=%d today=%d", len(all_listings), len(today_listings))

    notifier = TelegramNotifier(token, chat_ids)
    for listing in today_listings:
        notifier.send("🆕 [Сегодня]\n" + format_message(listing))


if __name__ == "__main__":
    main()
