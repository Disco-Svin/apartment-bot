"""
Хранилище уже виденных объявлений — простой JSON-файл вида
{"kufar": ["123", "456"], "onliner": [...], ...}.

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
        self._ids_by_source = self._load()

    def _load(self):
        if not self.path.exists():
            return {}
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {source: set(ids) for source, ids in raw.items()}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {source: sorted(ids) for source, ids in self._ids_by_source.items()}
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False)
        tmp_path.replace(self.path)

    def has_source(self, source):
        return bool(self._ids_by_source.get(source))

    def is_new(self, source, listing_id):
        return listing_id not in self._ids_by_source.get(source, set())

    def mark_seen(self, source, listing_id):
        ids = self._ids_by_source.setdefault(source, set())
        ids.add(listing_id)
        if len(ids) > self.max_per_source:
            # Порядок множества не хронологический, но для простого
            # ограничения размера этого достаточно — не даём файлу расти
            # бесконечно на источниках с большим оборотом объявлений.
            excess = len(ids) - self.max_per_source
            for old_id in list(ids)[:excess]:
                ids.discard(old_id)
