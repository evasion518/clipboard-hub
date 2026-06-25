from PySide6.QtCore import QObject, Signal

from .clip_item import ClipItem, strip_html
from .sqlite_repository import SQLiteRepository


class ClipboardStore(QObject):
    item_added = Signal(object)
    items_changed = Signal()

    def __init__(
        self,
        repository: SQLiteRepository | None = None,
        max_items: int = 1000,
        max_bytes: int = 200 * 1024 * 1024,
        parent=None,
    ):
        super().__init__(parent)
        self._repository = repository
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._items: list[ClipItem] = repository.load_all() if repository is not None else []
        self._total_bytes = sum(item.size_bytes for item in self._items)
        self._enforce_retention_limits()

    def add(self, item: ClipItem) -> bool:
        if self._items and self._items[0].content_hash == item.content_hash:
            return False
        if item.size_bytes > self._max_bytes:
            return False

        if self._repository is not None:
            self._repository.insert(item)
        self._items.insert(0, item)
        self._total_bytes += item.size_bytes

        self._enforce_retention_limits()
        self.item_added.emit(item)
        self.items_changed.emit()
        return True

    def delete(self, item_id: str) -> bool:
        for index, item in enumerate(self._items):
            if item.id != item_id:
                continue

            del self._items[index]
            self._total_bytes -= item.size_bytes
            if self._repository is not None:
                self._repository.delete(item_id)
            self.items_changed.emit()
            return True

        return False

    def clear(self) -> bool:
        if not self._items:
            return False

        self._items.clear()
        self._total_bytes = 0
        if self._repository is not None:
            self._repository.clear()
        self.items_changed.emit()
        return True

    def get_all(self) -> list[ClipItem]:
        return list(self._items)

    def search(self, keyword: str) -> list[ClipItem]:
        kw = keyword.lower()
        matches: list[ClipItem] = []

        for item in self._items:
            searchable_values = (
                item.text,
                item.html,
                strip_html(item.html) if item.html is not None else None,
                item.preview,
                item.source_app,
                item.source_window,
            )
            if any(kw in value.lower() for value in searchable_values if value is not None):
                matches.append(item)

        return matches

    def get_by_id(self, item_id: str):
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def _enforce_retention_limits(self) -> None:
        while len(self._items) > self._max_items:
            if not self._evict_oldest():
                return

        while self._total_bytes > self._max_bytes:
            if not self._evict_oldest():
                return

    def _evict_oldest(self) -> bool:
        if not self._items:
            return False

        oldest = self._items.pop()
        self._total_bytes -= oldest.size_bytes
        if self._repository is not None:
            self._repository.delete(oldest.id)
        return True
