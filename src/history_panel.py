from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .clip_item import ClipItem
from .clipboard_codec import ClipboardCodec
from .clipboard_store import ClipboardStore
from .clipboard_watcher import ClipboardWatcher
from .theme import ThemePalette, get_theme

PANEL_SIZE = (420, 520)
ROW_SURFACE_WIDTH = 360
ROW_SURFACE_HEIGHT = 52


def format_relative_time(timestamp: float, *, now: float | None = None) -> str:
    current_time = time.time() if now is None else now
    elapsed_seconds = max(0, int(current_time - timestamp))
    if elapsed_seconds < 60:
        return "刚刚"

    elapsed_minutes = elapsed_seconds // 60
    if elapsed_minutes < 60:
        return f"{elapsed_minutes} 分钟前"

    elapsed_hours = elapsed_minutes // 60
    if elapsed_hours < 24:
        return f"{elapsed_hours} 小时前"

    elapsed_days = elapsed_hours // 24
    return f"{elapsed_days} 天前"


def feedback_text_for_state(state: str | None) -> str | None:
    if state == "copied":
        return "已复制"
    if state == "failed":
        return "复制失败"
    return None


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


class HistoryCard(QWidget):
    def __init__(self, item: ClipItem, theme: ThemePalette, delete_handler, parent=None, *, sequence: int | None = None):
        super().__init__(parent)
        self._item = item
        self._theme = theme
        self._feedback_state: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(2)

        self._row_surface = QWidget(self)
        self._row_surface.setObjectName("rowSurface")
        self._row_surface.setFixedWidth(ROW_SURFACE_WIDTH)
        self._row_surface.setFixedHeight(ROW_SURFACE_HEIGHT)
        row_layout = QHBoxLayout(self._row_surface)
        row_layout.setContentsMargins(12, 0, 0, 0)
        row_layout.setSpacing(8)

        self._sequence_label = QLabel("" if sequence is None else str(sequence))
        self._sequence_label.setObjectName("sequenceLabel")
        self._sequence_label.setAlignment(Qt.AlignCenter)
        self._sequence_label.setFixedSize(26, 26)
        row_layout.addWidget(self._sequence_label, 0, Qt.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(0)

        self._preview_label = QLabel(item.preview)
        self._preview_label.setObjectName("previewLabel")
        self._preview_label.setWordWrap(True)
        self._preview_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._preview_label.setMaximumHeight(34)
        self._preview_label.setMinimumHeight(32)
        self._preview_fade = QWidget(self._preview_label)
        self._preview_fade.setObjectName("previewFadeOverlay")
        self._preview_fade.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._preview_fade.setFixedHeight(10)
        self._preview_fade.raise_()
        text_column.addWidget(self._preview_label)

        self._feedback_label = QLabel("")
        self._feedback_label.setObjectName("feedbackLabel")
        self._feedback_label.hide()

        self._time_label = QLabel(format_relative_time(item.timestamp))
        self._time_label.setObjectName("timeLabel")
        self._time_label.setAlignment(Qt.AlignCenter)

        row_layout.addLayout(text_column, 1)
        row_layout.addWidget(self._feedback_label, 0, Qt.AlignVCenter)
        row_layout.addWidget(self._time_label, 0, Qt.AlignVCenter)

        self._delete_button = QPushButton("")
        self._delete_button.setObjectName("cardActionButton")
        self._delete_button.setCursor(Qt.PointingHandCursor)
        self._delete_button.setFixedSize(ROW_SURFACE_HEIGHT // 2, ROW_SURFACE_HEIGHT)
        self._delete_button.clicked.connect(lambda: delete_handler(item.id))
        row_layout.addWidget(self._delete_button, 0)

        layout.addWidget(self._row_surface)

        self._row_divider = QWidget(self)
        self._row_divider.setObjectName("rowDivider")
        self._row_divider.setFixedHeight(2)
        layout.addWidget(self._row_divider)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(116, 156, 208, 26))
        self.setGraphicsEffect(shadow)

        self.apply_theme(theme)
        self._apply_feedback_style()

    @property
    def item_id(self) -> str:
        return self._item.id

    def visible_feedback_text(self) -> str | None:
        if not self._feedback_label.isVisible():
            return None
        text = self._feedback_label.text().strip()
        return text or None

    def set_feedback(self, state: str | None) -> None:
        self._feedback_state = state
        feedback_text = feedback_text_for_state(state)
        if state == "copied":
            self._feedback_label.setText(feedback_text or "")
            self._feedback_label.setStyleSheet(
                f"""
                color: {self._theme.success};
                background-color: {self._theme.success_background};
                border: 1px solid {self._theme.success};
                border-radius: 999px;
                padding: 2px 8px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: 600;
                """
            )
            self._feedback_label.show()
        elif state == "failed":
            self._feedback_label.setText(feedback_text or "")
            self._feedback_label.setStyleSheet(
                f"""
                color: {self._theme.failure};
                background-color: {self._theme.failure_background};
                border: 1px solid {self._theme.failure};
                border-radius: 999px;
                padding: 2px 8px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: 600;
                """
            )
            self._feedback_label.show()
        else:
            self._feedback_label.hide()
            self._feedback_label.clear()
        self._apply_feedback_style()

    def apply_theme(self, theme: ThemePalette) -> None:
        self._theme = theme
        self._delete_button.setStyleSheet(
            f"""
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 230),
                    stop:0.45 {theme.success_background},
                    stop:1 {theme.success}
                );
                border: 1px solid {theme.success};
                border-radius: 13px;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255, 255, 255, 245),
                    stop:0.4 {theme.search_background},
                    stop:1 {theme.search_focus}
                );
                border: 1px solid {theme.search_focus};
                border-radius: 13px;
            }}
            """
        )
        self._sequence_label.setStyleSheet(
            f"""
            color: {theme.card_meta};
            background-color: {theme.search_background};
            border: 1px solid {theme.card_border};
            border-radius: 13px;
            font-family: 'Segoe UI';
            font-size: 11px;
            font-weight: 700;
            """
        )
        self._preview_label.setStyleSheet(
            f"color: {theme.card_text}; font-family: 'Segoe UI'; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        self._preview_fade.setStyleSheet(
            f"""
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255, 255, 255, 0),
                stop:1 {theme.card_background}
            );
            border: none;
            """
        )
        self._time_label.setStyleSheet(
            f"""
            color: {theme.card_meta};
            background-color: {theme.search_background};
            border: 1px solid {theme.card_border};
            border-radius: 999px;
            padding: 2px 8px;
            font-family: 'Segoe UI';
            font-size: 10px;
            font-weight: 600;
            """
        )
        self._row_divider.setStyleSheet(
            f"""
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(255, 255, 255, 0),
                stop:0.18 {theme.card_border},
                stop:0.5 {theme.search_border},
                stop:0.82 {theme.card_border},
                stop:1 rgba(255, 255, 255, 0)
            );
            border: none;
            margin-left: 18px;
            margin-right: 18px;
            """
        )
        if self._feedback_state is not None:
            self.set_feedback(self._feedback_state)
            return
        self._apply_feedback_style()

    def _apply_feedback_style(self) -> None:
        surface_background = self._theme.card_background
        surface_border = self._theme.card_border
        if self._feedback_state == "copied":
            surface_background = self._theme.success_background
            surface_border = self._theme.success
        elif self._feedback_state == "failed":
            surface_background = self._theme.failure_background
            surface_border = self._theme.failure

        self.setStyleSheet("HistoryCard { background: transparent; border: none; }")
        self._row_surface.setStyleSheet(
            f"""
            QWidget#rowSurface {{
                background-color: {surface_background};
                border: 1px solid {surface_border};
                border-radius: 13px;
            }}
            """
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_preview_fade()

    def _position_preview_fade(self) -> None:
        width = max(0, self._preview_label.width())
        height = self._preview_fade.height()
        y = max(0, self._preview_label.height() - height)
        self._preview_fade.setGeometry(0, y, width, height)
        self._preview_fade.raise_()


class HistoryList(QListWidget):
    item_clicked = Signal(str)
    item_delete_requested = Signal(str)

    def __init__(self, theme: ThemePalette, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._cards: dict[str, HistoryCard] = {}
        self.setSpacing(4)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(
            """
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            """
        )
        self.itemClicked.connect(self._on_item_clicked)

    def clear(self) -> None:
        self._cards.clear()
        super().clear()

    def add_history_item(self, item: ClipItem, feedback: str | None = None, *, sequence: int | None = None) -> None:
        list_item = QListWidgetItem()
        list_item.setData(Qt.UserRole, item.id)
        card = HistoryCard(item, self._theme, self.item_delete_requested.emit, sequence=sequence)
        card.set_feedback(feedback)
        list_item.setSizeHint(card.sizeHint())
        self.addItem(list_item)
        self.setItemWidget(list_item, card)
        self._cards[item.id] = card

    def apply_theme(self, theme: ThemePalette) -> None:
        self._theme = theme
        for card in self._cards.values():
            card.apply_theme(theme)

    def visible_feedback_text(self, item_id: str) -> str | None:
        card = self._cards.get(item_id)
        if card is None:
            return None
        return card.visible_feedback_text() or feedback_text_for_state(card._feedback_state)

    def set_feedback(self, item_id: str, state: str | None) -> None:
        card = self._cards.get(item_id)
        if card is not None:
            card.set_feedback(state)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        item_id = item.data(Qt.UserRole)
        if item_id:
            self.item_clicked.emit(item_id)

    def contextMenuEvent(self, event):
        pass


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
        self._allow_hide_after_copy = False
        self._theme_mode = theme_mode
        self._theme = get_theme(theme_mode)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._animate_hide)
        self._hide_timer.setInterval(300)
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

        self._store.items_changed.connect(self._refresh_list)
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
        self._header_divider.setStyleSheet(
            f"background-color: {self._theme.card_border}; border: none;"
        )
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

    def _refresh_list(self):
        keyword = self._search_box.text().strip()
        all_items = self._store.get_all()
        items = self._store.search(keyword) if keyword else all_items
        self._list.clear()

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
        for index, item in enumerate(items):
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
        message_box = QMessageBox(self)
        message_box.setWindowTitle("确认删除")
        message_box.setText("要删除这条剪贴板记录吗？")
        delete_button = message_box.addButton("删除", QMessageBox.YesRole)
        message_box.addButton("取消", QMessageBox.RejectRole)
        message_box.exec()
        if message_box.clickedButton() is delete_button:
            self._feedback_state.pop(item_id, None)
            self._feedback_revisions.pop(item_id, None)
            timer = self._feedback_timers.pop(item_id, None)
            if timer is not None:
                timer.stop()
                timer.deleteLater()
            self._store.delete(item_id)

    def notify_mouse_enter(self):
        self._allow_hide_after_copy = False
        self._hide_timer.stop()

    def notify_mouse_leave(self):
        if self._contains_active_focus() and not self._allow_hide_after_copy:
            return
        self._hide_timer.start()

    def _animate_hide(self):
        if self._contains_active_focus() and not self._allow_hide_after_copy:
            return
        self._allow_hide_after_copy = False
        self.hide()

    def _contains_active_focus(self) -> bool:
        focus_widget = QApplication.focusWidget()
        return focus_widget is not None and (focus_widget is self or self.isAncestorOf(focus_widget))

    def enterEvent(self, event):
        self.notify_mouse_enter()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.notify_mouse_leave()
        super().leaveEvent(event)
