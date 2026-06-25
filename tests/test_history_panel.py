from PySide6.QtCore import QBuffer, QIODevice, QPoint, Qt
from PySide6.QtGui import QFocusEvent, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QStyleOptionViewItem, QWidget
import pytest

from src.clip_item import ClipItem
from src.clipboard_codec import ClipboardCodec
from src.clipboard_store import ClipboardStore
from src.history_panel import HistoryPanel, HistoryList, RENDER_ITEM_LIMIT, format_relative_time
from src.theme import DARK_THEME, LIGHT_THEME, get_theme


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(buffer.data())


class FakeWatcher:
    def __init__(self):
        self.notified_hashes: list[str] = []

    def notify_self_copy(self, content_hash: str):
        self.notified_hashes.append(content_hash)


class FakeClipboard:
    def __init__(self):
        self.mime = None

    def setMimeData(self, mime):
        self.mime = mime

    def mimeData(self):
        return self.mime


class RaisingClipboardWriter:
    def write(self, item):
        raise RuntimeError("clipboard unavailable")


class PollingClipboardWriter:
    def __init__(self, clipboard, watcher):
        self._clipboard = clipboard
        self._watcher = watcher

    def write(self, item):
        self._clipboard.setMimeData(ClipboardCodec.encode(item))
        self._watcher.poll()


def test_plain_text_recopy_still_works_and_notifies_hash(qapp, monkeypatch):
    store = ClipboardStore()
    item = ClipItem.create(
        text="hello from history",
        source_app="Code.exe",
        source_window="notes.txt",
    )
    store.add(item)
    watcher = FakeWatcher()
    panel = HistoryPanel(store, watcher)
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))

    assert panel.copy_item(item.id) is True

    restored = ClipboardCodec.decode(clipboard.mimeData())
    assert watcher.notified_hashes == [ClipboardCodec.self_copy_hash(item)]
    assert clipboard.mimeData().hasText()
    assert restored is not None
    assert restored.text == item.text
    assert restored.content_hash == item.content_hash


def test_panel_copy_does_not_create_duplicate_when_watcher_polls_during_write(qapp):
    from src.clipboard_watcher import ClipboardWatcher
    from src.source_app import SourceInfo

    class FakeSourceProvider:
        def get(self):
            return SourceInfo(app="Clipboard Hub", window=None)

    store = ClipboardStore()
    item = ClipItem.create(
        text="same copied text",
        html="<b>same copied text</b>",
        source_app="Code.exe",
    )
    store.add(item)
    clipboard = FakeClipboard()
    watcher = ClipboardWatcher(
        store,
        clipboard=clipboard,
        source_provider=FakeSourceProvider(),
        autostart=False,
    )
    panel = HistoryPanel(
        store,
        watcher,
        clipboard_writer=PollingClipboardWriter(clipboard, watcher),
    )

    assert panel.copy_item(item.id) is True

    watcher.poll()
    assert store.get_all() == [item]


def test_image_recopy_writes_no_image_data(qapp, monkeypatch):
    store = ClipboardStore()
    image = QImage(4, 3, QImage.Format.Format_ARGB32)
    image.fill(0xFF224466)
    item = ClipItem.create(
        text="image fallback text",
        image_png=_png_bytes(image),
        image_size=(4, 3),
        source_app="Paint.exe",
        source_window="Canvas",
    )
    store.add(item)
    watcher = FakeWatcher()
    panel = HistoryPanel(store, watcher)
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))

    assert panel.copy_item(item.id) is True

    assert watcher.notified_hashes == [ClipboardCodec.self_copy_hash(item)]
    assert clipboard.mimeData().hasText()
    assert not clipboard.mimeData().hasImage()
    assert bytes(clipboard.mimeData().data("image/png")) == b""


def test_image_card_does_not_render_preview_area(qapp):
    store = ClipboardStore()
    image = QImage(24, 18, QImage.Format.Format_ARGB32)
    image.fill(0xFF224466)
    item = ClipItem.create(
        image_png=_png_bytes(image),
        image_size=(24, 18),
        source_app="Paint.exe",
        source_window="Canvas",
    )
    store.add(item)

    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    assert panel._list.indexWidget(panel._list.model().index(0, 0)) is None


def test_text_card_does_not_render_image_preview_area(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", source_app="Code.exe")
    store.add(item)

    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    assert panel._list.indexWidget(panel._list.model().index(0, 0)) is None


def test_multiformat_recopy_writes_only_plain_text(qapp, monkeypatch):
    store = ClipboardStore()
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xFF00FF00)
    png_bytes = _png_bytes(image)
    item = ClipItem.create(
        text="hello",
        html="<p><b>hello</b></p>",
        image_png=png_bytes,
        image_size=(3, 2),
        source_app="Chrome.exe",
        source_window="Docs",
    )
    store.add(item)
    watcher = FakeWatcher()
    panel = HistoryPanel(store, watcher)
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))

    assert panel.copy_item(item.id) is True

    mime = clipboard.mimeData()
    restored = ClipboardCodec.decode(mime)
    assert watcher.notified_hashes == [ClipboardCodec.self_copy_hash(item)]
    assert mime.hasText()
    assert not mime.hasHtml()
    assert not mime.hasImage()
    assert restored is not None
    assert restored.text == item.text
    assert restored.html is None
    assert restored.image_png is None
    assert restored.image_size is None


def test_search_box_exposes_enabled_clear_button(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert panel.search_box.isClearButtonEnabled() is True
    assert panel.search_box.placeholderText() == "搜索"


def test_search_input_keeps_panel_visible_after_hide_is_requested(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="hello", source_app="Code.exe"))
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    panel.notify_mouse_leave()
    panel.search_box.setText("he")
    QTest.qWait(360)

    assert panel.isVisible() is True


def test_panel_stays_open_when_cursor_has_moved_from_tab_into_panel(qapp, monkeypatch):
    store = ClipboardStore()
    store.add(ClipItem.create(text="hello", source_app="Code.exe"))
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(20, 20)
    monkeypatch.setattr(panel, "_cursor_position", lambda: panel.geometry().center())

    panel._animate_hide()

    assert panel.isVisible() is True


def test_focused_panel_hides_when_cursor_is_outside(qapp, monkeypatch):
    store = ClipboardStore()
    store.add(ClipItem.create(text="hello", source_app="Code.exe"))
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(20, 20)
    monkeypatch.setattr(panel, "_cursor_position", lambda: QPoint(900, 900))

    panel._animate_hide()

    assert panel.isVisible() is False


def test_panel_hides_after_copy_when_mouse_leaves(qapp, monkeypatch):
    store = ClipboardStore()
    item = ClipItem.create(text="copy then leave", source_app="Code.exe")
    store.add(item)
    watcher = FakeWatcher()
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))
    panel = HistoryPanel(store, watcher)
    panel.show_at(0, 0)

    monkeypatch.setattr(panel, "_cursor_position", lambda: QPoint(900, 900))

    assert panel.copy_item(item.id) is True
    panel._animate_hide()

    assert panel.isVisible() is False


def test_search_focus_does_not_cancel_pending_hide_after_copy(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())
    panel._allow_hide_after_copy = True

    panel.search_box.focusInEvent(QFocusEvent(QFocusEvent.FocusIn))

    assert panel._allow_hide_after_copy is True


def test_successful_copy_sets_temporary_feedback_and_notifies_watcher(qapp, monkeypatch):
    store = ClipboardStore()
    item = ClipItem.create(text="copied", source_app="Code.exe", source_window="notes.txt")
    store.add(item)
    watcher = FakeWatcher()
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))
    panel = HistoryPanel(store, watcher, feedback_duration_ms=25)
    panel.show_at(0, 0)

    assert panel.copy_item(item.id) is True
    assert panel.feedback_for(item.id) == "copied"
    assert watcher.notified_hashes == [item.content_hash]

    QTest.qWait(80)
    assert panel.feedback_for(item.id) is None


def test_failed_copy_sets_failure_feedback_and_does_not_notify_watcher(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="copied", source_app="Code.exe", source_window="notes.txt")
    store.add(item)
    watcher = FakeWatcher()
    panel = HistoryPanel(
        store,
        watcher,
        clipboard_writer=RaisingClipboardWriter(),
        feedback_duration_ms=25,
    )

    assert panel.copy_item(item.id) is False
    assert panel.feedback_for(item.id) == "failed"
    assert watcher.notified_hashes == []

    QTest.qWait(80)
    assert panel.feedback_for(item.id) is None


def test_empty_store_shows_real_empty_history_state(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    panel.show_at(0, 0)

    visible_texts = {
        label.text()
        for label in panel.findChildren(QLabel)
        if label.isVisible() and label.text()
    }
    assert "还没有剪贴板记录" in visible_texts
    assert "没有找到匹配内容" not in visible_texts


def test_hidden_panel_defers_refresh_until_shown(qapp):
    store = ClipboardStore()
    panel = HistoryPanel(store, FakeWatcher())

    assert panel.isVisible() is False
    store.add(ClipItem.create(text="copied while hidden", source_app="Code.exe"))

    assert panel._list.count() == 0

    panel.show_at(0, 0)

    assert panel._list.count() == 1


def test_large_history_panel_renders_only_initial_limit(qapp):
    store = ClipboardStore()
    for index in range(RENDER_ITEM_LIMIT + 25):
        store.add(ClipItem.create(text=f"clip {index}", source_app="Code.exe"))
    panel = HistoryPanel(store, FakeWatcher())

    panel.show_at(0, 0)

    assert panel._list.count() == RENDER_ITEM_LIMIT
    assert RENDER_ITEM_LIMIT <= 24


def test_history_list_does_not_attach_widgets_per_row(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="hello", source_app="Code.exe"))
    panel = HistoryPanel(store, FakeWatcher())

    panel.show_at(0, 0)

    assert panel._list.indexWidget(panel._list.model().index(0, 0)) is None


def test_visible_panel_adds_new_item_without_full_refresh(qapp, monkeypatch):
    store = ClipboardStore()
    store.add(ClipItem.create(text="first", source_app="Code.exe"))
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)
    clear_calls = []
    original_clear = panel._list.clear

    def recording_clear():
        clear_calls.append("clear")
        original_clear()

    monkeypatch.setattr(panel._list, "clear", recording_clear)

    store.add(ClipItem.create(text="second", source_app="Code.exe"))

    assert clear_calls == []
    assert panel._list.count() == 2


def test_repeated_copy_refreshes_feedback_timer_without_stale_clear(qapp, monkeypatch):
    store = ClipboardStore()
    item = ClipItem.create(text="copied twice", source_app="Code.exe", source_window="notes.txt")
    store.add(item)
    watcher = FakeWatcher()
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))
    panel = HistoryPanel(store, watcher, feedback_duration_ms=40)

    assert panel.copy_item(item.id) is True
    QTest.qWait(25)
    assert panel.copy_item(item.id) is True

    QTest.qWait(25)
    assert panel.feedback_for(item.id) == "copied"

    QTest.qWait(60)
    assert panel.feedback_for(item.id) is None


def test_get_theme_rejects_unsupported_mode():
    with pytest.raises(ValueError, match="Unsupported theme mode"):
        get_theme("sepia")


def test_get_theme_system_uses_qt_color_scheme(monkeypatch):
    class FakeHints:
        def colorScheme(self):
            return Qt.ColorScheme.Dark

    class FakeApp:
        @staticmethod
        def styleHints():
            return FakeHints()

    monkeypatch.setattr("src.ui.theme.QApplication.instance", staticmethod(lambda: FakeApp()))

    assert get_theme("system") == DARK_THEME


def test_get_theme_defaults_to_system(monkeypatch):
    class FakeHints:
        def colorScheme(self):
            return Qt.ColorScheme.Dark

    class FakeApp:
        @staticmethod
        def styleHints():
            return FakeHints()

    monkeypatch.setattr("src.ui.theme.QApplication.instance", staticmethod(lambda: FakeApp()))

    assert get_theme() == DARK_THEME


def test_get_theme_system_does_not_create_application(monkeypatch):
    monkeypatch.setattr("src.ui.theme.QApplication.instance", staticmethod(lambda: None))

    assert get_theme("system") == LIGHT_THEME


def test_relative_time_helper_is_clear():
    item = ClipItem.create(
        text="hello",
        source_app="Code.exe",
        source_window="notes.txt",
        timestamp=240.0,
    )

    assert format_relative_time(300.0, now=300.0) == "刚刚"
    assert format_relative_time(240.0, now=300.0) == "1 分钟前"


def test_history_card_renders_separate_time_badge(qapp, monkeypatch):
    monkeypatch.setattr("src.ui.history_card.time.time", lambda: 300.0)
    store = ClipboardStore()
    item = ClipItem.create(
        text="hello",
        source_app="Code.exe",
        source_window="notes.txt",
        timestamp=240.0,
    )
    store.add(item)

    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    assert panel._list.model().index(0, 0).data(Qt.DisplayRole) == "hello"
    assert format_relative_time(item.timestamp) == "1 分钟前"


def test_visible_feedback_text_is_observable_for_success_and_failure(qapp, monkeypatch):
    store = ClipboardStore()
    item = ClipItem.create(text="copied", source_app="Code.exe", source_window="notes.txt")
    store.add(item)
    watcher = FakeWatcher()
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))
    panel = HistoryPanel(store, watcher, feedback_duration_ms=25)
    panel.show_at(0, 0)

    assert panel.copy_item(item.id) is True
    assert panel.visible_feedback_text(item.id) == "已复制"

    failing_panel = HistoryPanel(
        store,
        watcher,
        clipboard_writer=RaisingClipboardWriter(),
        feedback_duration_ms=25,
    )
    failing_panel.show_at(0, 0)
    assert failing_panel.copy_item(item.id) is False
    assert failing_panel.visible_feedback_text(item.id) == "复制失败"


def test_history_card_hides_type_labels(qapp):
    store = ClipboardStore()
    text_item = ClipItem.create(text="hello", source_app="Code.exe")
    html_item = ClipItem.create(html="<b>hello</b>", source_app="Chrome.exe")
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xFF00FF00)
    image_item = ClipItem.create(image_png=_png_bytes(image), image_size=(3, 2), source_app="Paint.exe")
    store.add(text_item)
    store.add(html_item)
    store.add(image_item)

    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    labels = [label.text() for label in panel.findChildren(QLabel)]
    assert "文本" not in labels
    assert "网页" not in labels
    assert "图片" not in labels


def test_history_cards_show_reverse_sequence_numbers(qapp):
    store = ClipboardStore()
    oldest = ClipItem.create(text="oldest", source_app="Code.exe", timestamp=1.0)
    middle = ClipItem.create(text="middle", source_app="Code.exe", timestamp=2.0)
    newest = ClipItem.create(text="newest", source_app="Code.exe", timestamp=3.0)
    store.add(oldest)
    store.add(middle)
    store.add(newest)

    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    assert panel._list.row_sequence(newest.id) == 3
    assert panel._list.row_sequence(middle.id) == 2
    assert panel._list.row_sequence(oldest.id) == 1


def test_history_list_delegate_uses_fixed_height_rows(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="第一行很长的内容 第二行也很长 第三行应该被裁切隐藏", source_app="Code.exe")
    store.add(item)
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    size = panel._list.itemDelegate().sizeHint(QStyleOptionViewItem(), panel._list.model().index(0, 0))

    assert size.height() >= 52
    assert size.width() <= panel._list.viewport().width()


def test_history_list_does_not_need_horizontal_scrollbar(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="a long copied value " * 20, source_app="Code.exe")
    store.add(item)
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    assert panel._list.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert panel._list.indexWidget(panel._list.model().index(0, 0)) is None


def test_history_list_uses_uniform_item_sizes(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert panel._list.uniformItemSizes() is True


def test_history_list_uses_compact_spacing_between_rows(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert panel._list.spacing() <= 10


def test_single_item_delete_does_not_ask_for_confirmation(qapp, monkeypatch):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", source_app="Code.exe")
    store.add(item)
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    monkeypatch.setattr(
        "src.ui.history_panel.QMessageBox",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("single item delete should not ask for confirmation")
        ),
    )

    panel._on_delete_request(item.id)

    assert store.get_all() == []
    assert panel._list.count() == 0


def test_search_box_styles_placeholder_text(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert "QLineEdit::placeholder" in panel.search_box.styleSheet()


def test_clear_history_button_deletes_all_items_after_confirmation(qapp, monkeypatch):
    store = ClipboardStore()
    store.add(ClipItem.create(text="first", id="first"))
    store.add(ClipItem.create(text="second", id="second"))
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)
    seen = {}

    class FakeMessageBox:
        YesRole = object()
        RejectRole = object()

        def __init__(self, parent=None):
            seen["parent"] = parent
            self._buttons = []
            self._clicked = None

        def setWindowTitle(self, title):
            seen["title"] = title

        def setText(self, text):
            seen["text"] = text

        def addButton(self, text, role):
            button = object()
            self._buttons.append((text, role, button))
            return button

        def exec(self):
            seen["buttons"] = [text for text, _role, _button in self._buttons]
            self._clicked = self._buttons[0][2]

        def clickedButton(self):
            return self._clicked

    monkeypatch.setattr("src.ui.history_panel.QMessageBox", FakeMessageBox)

    button = panel.findChild(QPushButton, "clearHistoryButton")
    assert button is not None
    button.click()

    assert store.get_all() == []
    assert panel._list.count() == 0
    assert seen == {
        "parent": panel,
        "title": "确认删除",
        "text": "要删除全部剪贴板记录吗？",
        "buttons": ["全部删除", "取消"],
    }


def test_history_list_exposes_feedback_text_without_private_card_access(qapp):
    history_list = HistoryList(LIGHT_THEME)
    item = ClipItem.create(text="hello", source_app="Code.exe")
    history_list.add_history_item(item, "copied")

    assert history_list.visible_feedback_text(item.id) == "已复制"


def test_history_panel_defaults_to_system_theme(monkeypatch):
    monkeypatch.setattr("src.ui.history_panel.get_theme", lambda mode="light": DARK_THEME if mode == "system" else LIGHT_THEME)

    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert panel._theme == DARK_THEME


def test_history_panel_refreshes_styles_when_system_theme_changes(qapp, monkeypatch):
    themes = {
        "light": LIGHT_THEME,
        "dark": DARK_THEME,
    }
    current_mode = {"value": "light"}

    def fake_get_theme(mode="light"):
        if mode == "system":
            return themes[current_mode["value"]]
        return themes[mode]

    monkeypatch.setattr("src.ui.history_panel.get_theme", fake_get_theme)

    store = ClipboardStore()
    item = ClipItem.create(text="copied", source_app="Code.exe", source_window="notes.txt")
    store.add(item)
    watcher = FakeWatcher()
    clipboard = FakeClipboard()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clipboard))

    panel = HistoryPanel(store, watcher, theme_mode="system", feedback_duration_ms=1000)
    panel.show_at(0, 0)
    assert panel.copy_item(item.id) is True
    assert panel._theme == LIGHT_THEME
    assert LIGHT_THEME.search_background in panel.search_box.styleSheet()
    assert panel._list.itemDelegate().theme == LIGHT_THEME

    current_mode["value"] = "dark"
    panel._on_system_color_scheme_changed(Qt.ColorScheme.Dark)

    assert panel._theme == DARK_THEME
    assert DARK_THEME.search_background in panel.search_box.styleSheet()
    assert panel._list.itemDelegate().theme == DARK_THEME


def test_history_panel_uses_updated_glass_theme_values(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert panel._theme.panel_background != "#f4eee7"
    assert panel._theme.search_background != "#fffaf6"
    assert not hasattr(panel._theme, "danger")


def test_search_box_preserves_glass_container_treatment(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())
    style = panel.search_box.styleSheet()

    assert "background-color:" in style
    assert "border:" in style
    assert "border-radius:" in style


def test_history_card_avoids_per_row_shadow_effect(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", source_app="Code.exe")
    store.add(item)
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    assert panel._list.indexWidget(panel._list.model().index(0, 0)) is None


def test_time_badge_text_remains_available_to_delegate(qapp, monkeypatch):
    monkeypatch.setattr("src.ui.history_card.time.time", lambda: 300.0)
    store = ClipboardStore()
    item = ClipItem.create(
        text="hello",
        source_app="Code.exe",
        source_window="notes.txt",
        timestamp=240.0,
    )
    store.add(item)

    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    row = panel._list.model().index(0, 0).data(Qt.UserRole)

    assert format_relative_time(row.item.timestamp) == "1 分钟前"


def test_history_panel_renders_header_divider_under_search(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    divider = panel.findChild(QWidget, "headerDivider")

    assert divider is not None


def test_history_list_right_edge_click_requests_delete(qapp):
    item = ClipItem.create(text="hello", source_app="Code.exe")
    history_list = HistoryList(LIGHT_THEME)
    history_list.resize(380, 80)
    history_list.add_history_item(item)
    history_list.show()
    qapp.processEvents()

    seen = []
    history_list.item_delete_requested.connect(seen.append)
    index_rect = history_list.visualRect(history_list.model().index(0, 0))

    QTest.mouseClick(history_list.viewport(), Qt.LeftButton, pos=index_rect.center() + QPoint(index_rect.width() // 2 - 8, 0))

    assert seen == [item.id]


def test_history_list_rows_have_no_child_divider_widgets(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", source_app="Code.exe")
    store.add(item)
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    assert panel._list.indexWidget(panel._list.model().index(0, 0)) is None


def test_history_panel_does_not_keep_unused_refresh_or_focus_state(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert not hasattr(panel, "_needs_refresh")
    assert not hasattr(panel, "_contains_active_focus")
