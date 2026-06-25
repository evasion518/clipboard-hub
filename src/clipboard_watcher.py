import logging

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from .clipboard_codec import ClipboardCodec
from .clipboard_store import ClipboardStore
from .source_app import SourceAppProvider

logger = logging.getLogger("clipboard_hub")


class ClipboardWatcher(QObject):
    def __init__(
        self,
        store: ClipboardStore,
        parent=None,
        *,
        clipboard=None,
        source_provider=None,
        autostart: bool = True,
    ):
        super().__init__(parent)
        self._store = store
        self._clipboard = clipboard
        self._codec = ClipboardCodec()
        self._source_provider = source_provider or SourceAppProvider()
        self.pending_self_hash: str | None = None
        self._last_seen_hash: str | None = None
        self.last_exception: Exception | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.poll)
        if autostart:
            self._timer.start()

    def poll(self):
        try:
            clipboard = self._clipboard or QApplication.clipboard()
            mime = clipboard.mimeData()
            source = self._source_provider.get()
            item = self._codec.decode(
                mime,
                source_app=source.app,
                source_window=source.window,
            )
            if item is None:
                self._last_seen_hash = None
                self.last_exception = None
                return

            if self.pending_self_hash == item.content_hash:
                self.pending_self_hash = None
                self._last_seen_hash = item.content_hash
                self.last_exception = None
                return

            if self.pending_self_hash is not None:
                self.pending_self_hash = None

            if self._last_seen_hash == item.content_hash:
                self.last_exception = None
                return

            self._store.add(item)
            self._last_seen_hash = item.content_hash
            self.last_exception = None
        except (RuntimeError, OSError, AttributeError, ValueError) as exc:
            self.last_exception = exc
            logger.warning("Clipboard poll failed", exc_info=True)

    def notify_self_copy(self, content_hash: str):
        self.pending_self_hash = content_hash
