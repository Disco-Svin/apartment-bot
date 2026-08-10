"""
Обработка нажатий на инлайн-кнопки "Отслеживать цену" / "Остановить
отслеживание" под уведомлениями.

Бот не держит постоянное соединение с Telegram (весь цикл — раз в
15 минут), поэтому вместо вебхука используется getUpdates с сохранением
смещения (offset) в data/telegram_offset.json — вызывается один раз за
цикл, перед основным поиском. Из-за этого нажатие обрабатывается не
мгновенно, а на ближайшем прогоне бота (до ~15 минут) — это ограничение
общей архитектуры бота, а не баг.
"""
import json
import logging
from pathlib import Path

import requests

from keyboards import track_button
from watchlist import FETCHERS, add_watch, remove_watch

log = logging.getLogger("apartment-bot")

API_URL = "https://api.telegram.org/bot{token}/{method}"


def _call(token, method, request_timeout=15, **params):
    # request_timeout — таймаут самого HTTP-запроса (requests), не путать
    # с параметром "timeout" у getUpdates (это long-polling — Telegram-параметр,
    # который тоже мог бы называться timeout и конфликтовать с этим kwarg).
    resp = requests.post(API_URL.format(token=token, method=method), data=params, timeout=request_timeout)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error in {method}: {data}")
    return data["result"]


def _load_offset(path):
    path = Path(path)
    if not path.exists():
        return 0
    return json.loads(path.read_text(encoding="utf-8")).get("offset", 0)


def _save_offset(path, offset):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def process_updates(token, offset_path, store, watchlist_state_path, currency_per_usd=None, allowed_chat_ids=None):
    currency_per_usd = currency_per_usd or {}
    allowed_chat_ids = {str(chat_id) for chat_id in (allowed_chat_ids or [])}
    offset = _load_offset(offset_path)
    # Без явного timeout getUpdates не блокируется в ожидании новых
    # апдейтов — сразу возвращает то, что уже накопилось. Долгий
    # long-polling тут не нужен: бот и так вызывается раз в 15 минут.
    updates = _call(token, "getUpdates", offset=offset)

    max_update_id = offset - 1
    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        callback = update.get("callback_query")
        if not callback:
            continue
        try:
            _handle_callback(token, callback, store, watchlist_state_path, currency_per_usd, allowed_chat_ids)
        except Exception:
            log.exception("failed to handle callback_query %s", callback.get("id"))

    if updates:
        _save_offset(offset_path, max_update_id + 1)


def _handle_callback(token, callback, store, watchlist_state_path, currency_per_usd, allowed_chat_ids):
    data = callback.get("data") or ""
    callback_id = callback["id"]
    parts = data.split(":", 2)

    if len(parts) != 3 or parts[0] not in ("track", "untrack"):
        _call(token, "answerCallbackQuery", callback_query_id=callback_id)
        return

    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")

    # Сообщения с инлайн-кнопками можно переслать в другой чат — кнопка
    # при этом останется рабочей. Не даём управлять watchlist никому, кроме
    # адресатов из TELEGRAM_CHAT_IDS.
    if chat_id is None or str(chat_id) not in allowed_chat_ids:
        log.warning("ignoring track/untrack callback from unauthorized chat_id=%s", chat_id)
        _call(token, "answerCallbackQuery", callback_query_id=callback_id)
        return

    action, source, listing_id = parts
    message_id = message.get("message_id")

    if action == "track":
        tracking = _do_track(token, callback_id, store, watchlist_state_path, currency_per_usd, source, listing_id)
    else:
        tracking = _do_untrack(token, callback_id, store, watchlist_state_path, source, listing_id)

    if tracking is None:
        return  # уже отправили ответ об ошибке, кнопку не трогаем

    if chat_id is not None and message_id is not None:
        try:
            _call(
                token,
                "editMessageReplyMarkup",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=json.dumps(track_button(source, listing_id, tracking)),
            )
        except RuntimeError:
            log.exception("failed to edit reply markup chat=%s message=%s", chat_id, message_id)


def _do_track(token, callback_id, store, watchlist_state_path, currency_per_usd, source, listing_id):
    fetcher = FETCHERS.get(source)
    if fetcher is None:
        _call(
            token,
            "answerCallbackQuery",
            callback_query_id=callback_id,
            text="Эта площадка пока не поддерживает отслеживание цены",
        )
        return None

    url = store.get_url(source, listing_id)
    listing = None
    if url:
        try:
            listing = fetcher(url, currency_per_usd)
        except Exception:
            log.exception("track: не удалось получить данные %s/%s", source, listing_id)

    if listing is None or listing.price_usd is None:
        _call(
            token,
            "answerCallbackQuery",
            callback_query_id=callback_id,
            text="Не удалось получить данные объявления — попробуйте позже",
        )
        return None

    add_watch(watchlist_state_path, listing)
    _call(token, "answerCallbackQuery", callback_query_id=callback_id, text="Отслеживаем цену 🔔")
    return True


def _do_untrack(token, callback_id, store, watchlist_state_path, source, listing_id):
    url = store.get_url(source, listing_id)
    if url:
        remove_watch(watchlist_state_path, url)
    _call(token, "answerCallbackQuery", callback_query_id=callback_id, text="Отслеживание остановлено")
    return False
