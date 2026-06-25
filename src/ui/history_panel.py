from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ..clip_item import ClipItem
from ..clipboard_codec import ClipboardCodec
from ..clipboard_store import ClipboardStore
from ..clipboard_watcher import ClipboardWatcher
from .history_card import feedback_text_for_state
from .history_list import HistoryList
from .theme import ThemePalette, get_theme

PANEL_SIZE = (420, 520)
RENDER_ITEM_LIMIT = 24


class ClipboardWriter:
    def write(self, item: ClipItem) -> None:
        QApplication.clipboard().setMimeData(ClipboardCodec.encode(item))


class SearchBox(QLineEdit):
    def __init__(self, theme: ThemePalette, parent=None):
        super().__init__(parent)
        self.setClearButtonEnabled(True)
        self.setPlaceholderText("搜索")
        self.apply_theme(theme)

    def focusInEvent(self, event):
        parent = self.parentWidget()
        while parent is not None:
            if getattr(parent, "_allow_hide_after_copy", False):
                break
            notify_mouse_enter = getattr(parent, "notify_mouse_enter", None)
            if callable(notify_mouse_enter):
                notify_mouse_enter()
                break
            parent = parent.parentWidget()
        super().focusInEvent(event)

    def apply_theme(self, theme: ThemePalette) -> None:
        self.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: {theme.search_background};
                color: {theme.search_text};
                border: 1px solid {theme.search_border};
                border-radius: 12px;
                padding: 12px 16px;
                font-family: "Segoe UI";
                font-size: 13px;
                selection-background-color: {theme.search_focus};
            }}
            QLineEdit:focus {{
                border: 1px solid {theme.search_focus};
                background-color: {theme.card_background};
            }}
            QLineEdit::placeholder {{
                color: {theme.empty_text};
            }}
            """
        )


class HistoryPanel(QWidget):
    def __init__(
        self,
        store: ClipboardStore,
        watcher: ClipboardWatcher,
        parent=None,
        *,
        clipboard_writer: ClipboardWriter | None = None,
        feedback_duration_ms: int = 1200,
        theme_mode: str = "system",
    ):
        super().__init__(parent)
        self._store = store
        self._watcher = watcher
        self._clipboard_writer = clipboard_writer or ClipboardWriter()
        self._feedback_duration_ms = feedback_duration_ms
        self._feedback_state: dict[str, str] = {}
        self._feedback_revisions: dict[str, int] = {}
        self._feedback_timers: dict[str, QTimer] = {}
        self._skip_next_items_changed = False
        self._allow_hide_after_copy = False
        self._theme_mode = theme_mode
        self._theme = get_theme(theme_mode)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._animate_hide)
        self._hide_timer.setInterval(120)
        app = QApplication.instance()
        self._style_hints = app.styleHints() if app is not None else None
        if self._theme_mode == "system" and self._style_hints is not None:
            self._style_hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(*PANEL_SIZE)
        self.setObjectName("HistoryPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self._search_box = SearchBox(self._theme)
        self._search_box.textChanged.connect(self._on_search)
        layout.addWidget(self._search_box)

        self._clear_button = QPushButton("一键删除")
        self._clear_button.setObjectName("clearHistoryButton")
        self._clear_button.setCursor(Qt.PointingHandCursor)
        self._clear_button.clicked.connect(self._on_clear_request)
        self._clear_button.setEnabled(False)
        layout.addWidget(self._clear_button)

        self._header_divider = QWidget(self)
        self._header_divider.setObjectName("headerDivider")
        self._header_divider.setFixedHeight(1)
        layout.addWidget(self._header_divider)

        self._empty_state_label = QLabel("还没有剪贴板记录")
        self._empty_state_label.setAlignment(Qt.AlignCenter)
        self._empty_state_label.hide()
        layout.addWidget(self._empty_state_label)

        self._no_results_label = QLabel("没有找到匹配内容")
        self._no_results_label.setAlignment(Qt.AlignCenter)
        self._no_results_label.hide()
        layout.addWidget(self._no_results_label)

        self._list = HistoryList(self._theme)
        self._list.item_clicked.connect(self._on_re_copy)
        self._list.item_delete_requested.connect(self._on_delete_request)
        layout.addWidget(self._list, 1)

        self._store.item_added.connect(self._on_item_added)
        self._store.items_changed.connect(self._on_items_changed)
        self._apply_theme()
        self.hide()

    @property
    def search_box(self) -> SearchBox:
        return self._search_box

    def feedback_for(self, item_id: str) -> str | None:
        return self._feedback_state.get(item_id)

    def visible_feedback_text(self, item_id: str) -> str | None:
        visible_text = self._list.visible_feedback_text(item_id)
        if visible_text is not None:
            return visible_text
        return feedback_text_for_state(self._feedback_state.get(item_id))

    def copy_item(self, item_id: str) -> bool:
        item = self._store.get_by_id(item_id)
        if item is None:
            return False

        self_copy_hash = ClipboardCodec.self_copy_hash(item)
        pre_notified = self_copy_hash is not None and hasattr(self._watcher, "pending_self_hash")
        if pre_notified:
            self._watcher.notify_self_copy(self_copy_hash)
        try:
            self._clipboard_writer.write(item)
        except Exception:
            if pre_notified and getattr(self._watcher, "pending_self_hash", None) == self_copy_hash:
                self._watcher.pending_self_hash = None
            self._set_feedback(item_id, "failed")
            return False

        if self_copy_hash is not None and not pre_notified:
            self._watcher.notify_self_copy(self_copy_hash)
        self._set_feedback(item_id, "copied")
        self._allow_hide_after_copy = True
        return True

    def _apply_theme(self) -> None:
        self._search_box.apply_theme(self._theme)
        self._clear_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {self._theme.failure_background};
                color: {self._theme.failure};
                border: 1px solid {self._theme.failure};
                border-radius: 10px;
                padding: 8px 12px;
                font-family: "Segoe UI";
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:disabled {{
                color: {self._theme.empty_text};
                border-color: {self._theme.card_border};
                background-color: {self._theme.search_background};
            }}
            QPushButton:hover:!disabled {{
                background-color: {self._theme.card_background};
            }}
            """
        )
        self._header_divider.setStyleSheet(f"background-color: {self._theme.card_border}; border: none;")
        self._empty_state_label.setStyleSheet(
            f"color: {self._theme.empty_text}; font-family: 'Segoe UI'; font-size: 12px; background: transparent;"
        )
        self._no_results_label.setStyleSheet(
            f"color: {self._theme.empty_text}; font-family: 'Segoe UI'; font-size: 12px; background: transparent;"
        )
        self._list.apply_theme(self._theme)
        self.update()

    def _on_system_color_scheme_changed(self, _scheme) -> None:
        if self._theme_mode != "system":
            return
        self._theme = get_theme("system")
        self._apply_theme()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -2, -2)

        painter.setBrush(QBrush(QColor(self._theme.panel_background)))
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(self._theme.panel_border_start))
        gradient.setColorAt(1.0, QColor(self._theme.panel_border_end))
        painter.setPen(QPen(gradient, 1.2))
        painter.drawRoundedRect(rect, 28, 28)

    def show_at(self, x: int, y: int):
        self.move(x, y)
        self.show()
        self.raise_()
        self._refresh_list()

    def _on_items_changed(self) -> None:
        if self._skip_next_items_changed:
            self._skip_next_items_changed = False
            return
        if not self.isVisible():
            return
        self._refresh_list()

    def _on_item_added(self, item: ClipItem) -> None:
        self._skip_next_items_changed = True
        if not self.isVisible():
            return
        if self._search_box.text().strip():
            self._refresh_list()
            return

        total = len(self._store.get_all())
        self._clear_button.setEnabled(total > 0)
        self._empty_state_label.hide()
        self._no_results_label.hide()
        self._list.prepend_history_item(item, self._feedback_state.get(item.id), sequence=total)
        self._list.trim_to_count(min(total, RENDER_ITEM_LIMIT))

    def _refresh_list(self):
        keyword = self._search_box.text().strip()
        all_items = self._store.get_all()
        items = self._store.search(keyword) if keyword else all_items
        self._list.clear()
        self._clear_button.setEnabled(bool(all_items))

        if not all_items:
            self._empty_state_label.show()
            self._no_results_label.hide()
        elif not items and keyword:
            self._empty_state_label.hide()
            self._no_results_label.show()
        else:
            self._empty_state_label.hide()
            self._no_results_label.hide()

        total = len(items)
        for index, item in enumerate(items[:RENDER_ITEM_LIMIT]):
            self._list.add_history_item(item, self._feedback_state.get(item.id), sequence=total - index)

    def _on_search(self, text: str):
        self.notify_mouse_enter()
        self._refresh_list()

    def _on_re_copy(self, item_id: str):
        self.copy_item(item_id)

    def _set_feedback(self, item_id: str, state: str) -> None:
        revision = self._feedback_revisions.get(item_id, 0) + 1
        self._feedback_revisions[item_id] = revision
        self._feedback_state[item_id] = state
        self._list.set_feedback(item_id, state)

        def clear_feedback():
            if self._feedback_revisions.get(item_id) != revision:
                return
            self._feedback_state.pop(item_id, None)
            self._list.set_feedback(item_id, None)
            timer = self._feedback_timers.pop(item_id, None)
            if timer is not None:
                timer.deleteLater()

        prior_timer = self._feedback_timers.pop(item_id, None)
        if prior_timer is not None:
            prior_timer.stop()
            prior_timer.deleteLater()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(clear_feedback)
        timer.start(self._feedback_duration_ms)
        self._feedback_timers[item_id] = timer

    def _on_delete_request(self, item_id: str):
        self._feedback_state.pop(item_id, None)
        self._feedback_revisions.pop(item_id, None)
        timer = self._feedback_timers.pop(item_id, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._store.delete(item_id)

    def _on_clear_request(self):
        if not self._store.get_all():
            return

        message_box = QMessageBox(self)
        message_box.setWindowTitle("确认删除")
        message_box.setText("要删除全部剪贴板记录吗？")
        delete_button = message_box.addButton("全部删除", QMessageBox.YesRole)
        message_box.addButton("取消", QMessageBox.RejectRole)
        message_box.exec()
        if message_box.clickedButton() is delete_button:
            self._feedback_state.clear()
            self._feedback_revisions.clear()
            for timer in self._feedback_timers.values():
                timer.stop()
                timer.deleteLater()
            self._feedback_timers.clear()
            self._store.clear()

    def notify_mouse_enter(self):
        self._allow_hide_after_copy = False
        self._hide_timer.stop()

    def notify_mouse_leave(self):
        self._hide_timer.start()

    def _animate_hide(self):
        if self.geometry().contains(self._cursor_position()):
            return
        self._allow_hide_after_copy = False
        self.hide()

    def _cursor_position(self):
        return QCursor.pos()

    def enterEvent(self, event):
        self.notify_mouse_enter()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.notify_mouse_leave()
        super().leaveEvent(event)
