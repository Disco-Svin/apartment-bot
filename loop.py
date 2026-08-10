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

from main import load_config, log, run_once
from notifier import TelegramNotifier
from storage import SeenStore

BASE_DIR = Path(__file__).resolve().parent


def main():
    load_dotenv(BASE_DIR / ".env")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — создайте .env по образцу .env.example")
        sys.exit(1)

    store = SeenStore(str(BASE_DIR / "data" / "seen.json"))
    notifier = TelegramNotifier(token, chat_id)

    while True:
        config = load_config()  # перечитываем на каждой итерации, чтобы правки в config.yaml подхватывались без перезапуска
        interval = config.get("poll_interval_seconds", 900)

        try:
            run_once(config, store, notifier)
        except Exception:
            log.exception("run_once failed, will retry next cycle")

        log.info("sleeping for %d seconds", interval)
        time.sleep(interval)


if __name__ == "__main__":
    main()
