"""Инлайн-кнопки Telegram для карточек объявлений."""


def track_button(source, listing_id, tracking):
    """Кнопка под объявлением: "Отслеживать цену" или, если уже
    отслеживается — "Остановить отслеживание". callback_data короткий
    ("track:kufar:123"), т.к. у Telegram лимит 64 байта — полную ссылку
    туда не поместить, поэтому обработчик сам находит её по (source, id)
    в storage.SeenStore."""
    if tracking:
        text, action = "🔕 Остановить отслеживание", "untrack"
    else:
        text, action = "🔔 Отслеживать цену", "track"
    return {"inline_keyboard": [[{"text": text, "callback_data": f"{action}:{source}:{listing_id}"}]]}
