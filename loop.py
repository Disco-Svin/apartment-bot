"""
Непрерывный локальный запуск: проверяет объявления в бесконечном цикле
с интервалом poll_interval_seconds из config.yaml.

Для запуска "по расписанию" (Планировщик заданий Windows, GitHub Actions)
используйте вместо этого main.py напрямую — там один прогон и выход.
"""
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from main import load_config, log, parse_chat_ids, run_cycle
from notifier import TelegramNotifier
from storage import SeenStore

BASE_DIR = Path(__file__).resolve().parent


def main():
    load_dotenv(BASE_DIR / ".env")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_ids_raw = os.environ.get("TELEGRAM_CHAT_IDS")
    chat_ids = parse_chat_ids(chat_ids_raw) if chat_ids_raw else []
    if not token or not chat_ids:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS не заданы — создайте .env по образцу .env.example")
        sys.exit(1)

    store = SeenStore(str(BASE_DIR / "data" / "seen.json"))
    notifier = TelegramNotifier(token, chat_ids)

    while True:
        config = load_config()  # перечитываем на каждой итерации, чтобы правки в config.yaml подхватывались без перезапуска
        interval = config.get("poll_interval_seconds", 900)

        try:
            run_cycle(config, store, notifier)
        except Exception:
            log.exception("run_cycle failed, will retry next cycle")

        log.info("sleeping for %d seconds", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
