"""
Хранилище уже виденных объявлений — простой JSON-файл вида
{"kufar": {"123": {"url": "...", "title": "..."}, ...}, ...}.

Помимо дедупликации хранит ссылку и заголовок каждого объявления — это
нужно кнопке "Отслеживать цену" под уведомлением: при нажатии Telegram
присылает только (source, listing_id) из callback_data (там жёсткий
лимит 64 байта, полную ссылку туда не поместить), а настоящую ссылку
бот берёт отсюда.

JSON выбран вместо SQLite намеренно: файл читаемый и удобно коммитится
в git постранично (если бот будет запускаться через GitHub Actions —
см. .github/workflows/poll.yml), а объём данных небольшой.
"""
import json
from pathlib import Path


class SeenStore:
    def __init__(self, path, max_per_source=8000):
        self.path = Path(path)
        self.max_per_source = max_per_source
        self._entries_by_source = self._load()

    def _load(self):
        if not self.path.exists():
            return {}
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Обратная совместимость со старым форматом файла
        # {"kufar": ["123", "456"]} — раньше хранились только id.
        upgraded = {}
        for source, entries in raw.items():
            if isinstance(entries, list):
                upgraded[source] = {str(listing_id): {} for listing_id in entries}
            else:
                upgraded[source] = {str(k): (v or {}) for k, v in entries.items()}
        return upgraded

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._entries_by_source, f, ensure_ascii=False)
        tmp_path.replace(self.path)

    def has_source(self, source):
        return bool(self._entries_by_source.get(source))

    def is_new(self, source, listing_id):
        return listing_id not in self._entries_by_source.get(source, {})

    def get_url(self, source, listing_id):
        entry = self._entries_by_source.get(source, {}).get(listing_id)
        return entry.get("url") if entry else None

    def mark_seen(self, source, listing_id, url=None, title=None):
        entries = self._entries_by_source.setdefault(source, {})
        entries[listing_id] = {"url": url, "title": title}
        if len(entries) > self.max_per_source:
            # Порядок ключей dict — порядок добавления, так что это
            # действительно удаляет самые старые записи, а не случайные.
            excess = len(entries) - self.max_per_source
            for old_id in list(entries.keys())[:excess]:
                del entries[old_id]
