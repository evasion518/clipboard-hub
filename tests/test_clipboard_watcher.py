from PySide6.QtCore import QBuffer, QIODevice, QMimeData
from PySide6.QtGui import QImage

from src.source_app import SourceInfo
from src.clipboard_store import ClipboardStore
from src.clipboard_watcher import ClipboardWatcher


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(buffer.data())


class FakeClipboard:
    def __init__(self, mime: QMimeData):
        self._mime = mime

    def mimeData(self):
        return self._mime

    def set_mime(self, mime: QMimeData):
        self._mime = mime


class FakeSourceProvider:
    def __init__(self, app: str = "Code.exe", window: str | None = "notes.txt"):
        self._info = SourceInfo(app=app, window=window)

    def get(self):
        return self._info


def test_watcher_has_timer(qapp):
    store = ClipboardStore()
    watcher = ClipboardWatcher(store, autostart=False)

    assert watcher._timer is not None
    assert watcher._timer.interval() == 500


def test_poll_decodes_text_and_html_clipboard_and_ignores_image(qapp):
    store = ClipboardStore()
    mime = QMimeData()
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xFF00FF00)

    mime.setText("hello")
    mime.setHtml("<p><b>hello</b></p>")
    mime.setImageData(image)

    watcher = ClipboardWatcher(
        store,
        clipboard=FakeClipboard(mime),
        source_provider=FakeSourceProvider(app="Chrome.exe", window="Docs"),
        autostart=False,
    )

    watcher.poll()

    items = store.get_all()
    assert len(items) == 1
    assert items[0].text == "hello"
    assert items[0].html == "<p><b>hello</b></p>"
    assert items[0].image_png is None
    assert items[0].image_size is None
    assert items[0].source_app == "Chrome.exe"
    assert items[0].source_window == "Docs"
    assert watcher._last_seen_hash == items[0].content_hash


def test_notify_self_copy_skips_matching_hash_until_clipboard_changes(qapp):
    store = ClipboardStore()
    mime = QMimeData()
    mime.setText("copied by app")

    watcher = ClipboardWatcher(
        store,
        clipboard=FakeClipboard(mime),
        source_provider=FakeSourceProvider(),
        autostart=False,
    )

    expected_hash = watcher._codec.decode(mime, source_app="Code.exe", source_window="notes.txt").content_hash
    watcher.notify_self_copy(expected_hash)

    watcher.poll()
    assert store.get_all() == []
    assert watcher.pending_self_hash is None

    watcher.poll()
    assert store.get_all() == []
    assert watcher._last_seen_hash == expected_hash


def test_notify_self_copy_with_different_hash_does_not_skip_next_item(qapp):
    store = ClipboardStore()
    mime = QMimeData()
    mime.setText("external clipboard")

    watcher = ClipboardWatcher(
        store,
        clipboard=FakeClipboard(mime),
        source_provider=FakeSourceProvider(app="Chrome.exe", window="Page"),
        autostart=False,
    )

    watcher.notify_self_copy("different-hash")

    watcher.poll()

    items = store.get_all()
    assert len(items) == 1
    assert items[0].text == "external clipboard"
    assert watcher.pending_self_hash is None


def test_empty_clipboard_clears_last_seen_hash_so_same_content_can_be_readded(qapp):
    class RecordingStore:
        def __init__(self):
            self.items = []
            self.add_calls = 0

        def add(self, item):
            self.add_calls += 1
            self.items.append(item)

    store = RecordingStore()
    first = QMimeData()
    first.setText("A")
    clipboard = FakeClipboard(first)
    watcher = ClipboardWatcher(
        store,
        clipboard=clipboard,
        source_provider=FakeSourceProvider(),
        autostart=False,
    )

    watcher.poll()
    assert store.add_calls == 1

    clipboard.set_mime(QMimeData())
    watcher.poll()
    assert watcher._last_seen_hash is None

    clipboard.set_mime(first)
    watcher.poll()

    assert store.add_calls == 2
    assert len(store.items) == 2
    assert store.items[0].text == "A"
    assert store.items[1].text == "A"


def test_polling_same_clipboard_content_twice_only_stores_one_item(qapp):
    class RecordingStore:
        def __init__(self):
            self.items = []
            self.add_calls = 0

        def add(self, item):
            self.add_calls += 1
            self.items.append(item)

    store = RecordingStore()
    mime = QMimeData()
    mime.setText("same clipboard content")
    clipboard = FakeClipboard(mime)
    watcher = ClipboardWatcher(
        store,
        clipboard=clipboard,
        source_provider=FakeSourceProvider(),
        autostart=False,
    )

    watcher.poll()
    watcher.poll()

    assert store.add_calls == 1
    assert len(store.items) == 1
    assert store.items[0].text == "same clipboard content"
    assert watcher._last_seen_hash == store.items[0].content_hash


class RaisingClipboard:
    def mimeData(self):
        raise ValueError("clipboard unavailable")


def test_poll_records_last_exception_when_recovering_from_error(qapp):
    store = ClipboardStore()
    watcher = ClipboardWatcher(
        store,
        clipboard=RaisingClipboard(),
        source_provider=FakeSourceProvider(),
        autostart=False,
    )

    watcher.poll()

    assert isinstance(watcher.last_exception, ValueError)
    assert str(watcher.last_exception) == "clipboard unavailable"


def test_poll_logs_clipboard_failure_without_clipboard_content(qapp, caplog):
    store = ClipboardStore()
    watcher = ClipboardWatcher(
        store,
        clipboard=RaisingClipboard(),
        source_provider=FakeSourceProvider(),
        autostart=False,
    )

    with caplog.at_level("WARNING", logger="clipboard_hub"):
        watcher.poll()

    messages = [record.getMessage() for record in caplog.records]
    assert "Clipboard poll failed" in messages
    assert all("same clipboard content" not in message for message in messages)
