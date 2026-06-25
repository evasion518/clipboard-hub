from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..clip_item import ClipItem
from .theme import ThemePalette

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
