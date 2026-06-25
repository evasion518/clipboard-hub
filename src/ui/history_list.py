from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyleOptionViewItem, QStyledItemDelegate

from ..clip_item import ClipItem
from .history_card import ROW_SURFACE_HEIGHT, feedback_text_for_state, format_relative_time
from .theme import ThemePalette


@dataclass(frozen=True)
class HistoryRow:
    item: ClipItem
    feedback: str | None = None
    sequence: int | None = None


class HistoryListModel(QAbstractListModel):
    def __init__(self, rows: list[HistoryRow] | None = None, parent=None):
        super().__init__(parent)
        self.rows = rows or []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.DisplayRole:
            return row.item.preview
        if role == Qt.UserRole:
            return row
        return None

    def clear(self) -> None:
        if not self.rows:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self.rows) - 1)
        self.rows.clear()
        self.endRemoveRows()

    def insert_row(self, row_index: int, row: HistoryRow) -> None:
        row_index = max(0, min(row_index, len(self.rows)))
        self.beginInsertRows(QModelIndex(), row_index, row_index)
        self.rows.insert(row_index, row)
        self.endInsertRows()

    def trim_to_count(self, count: int) -> None:
        count = max(0, count)
        if len(self.rows) <= count:
            return
        first = count
        last = len(self.rows) - 1
        self.beginRemoveRows(QModelIndex(), first, last)
        del self.rows[first:]
        self.endRemoveRows()

    def set_feedback(self, item_id: str, state: str | None) -> None:
        for index, row in enumerate(self.rows):
            if row.item.id != item_id:
                continue
            self.rows[index] = HistoryRow(row.item, state, row.sequence)
            model_index = self.index(index, 0)
            self.dataChanged.emit(model_index, model_index, [Qt.DisplayRole, Qt.UserRole])
            return


class HistoryDelegate(QStyledItemDelegate):
    def __init__(self, theme: ThemePalette, parent=None):
        super().__init__(parent)
        self.theme = theme

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(360, ROW_SURFACE_HEIGHT + 6)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        row = index.data(Qt.UserRole)
        if row is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(0, 3, -4, -3)

        feedback = row.feedback
        bg = self.theme.card_background
        border = self.theme.card_border
        if feedback == "copied":
            bg = self.theme.success_background
            border = self.theme.success
        elif feedback == "failed":
            bg = self.theme.failure_background
            border = self.theme.failure

        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, 13, 13)

        sequence_rect = QRect(rect.left() + 12, rect.top() + 13, 26, 26)
        painter.setPen(QPen(QColor(self.theme.card_border), 1))
        painter.setBrush(QColor(self.theme.search_background))
        painter.drawEllipse(sequence_rect)
        painter.setPen(QColor(self.theme.card_meta))
        font = QFont("Segoe UI", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(sequence_rect, Qt.AlignCenter, "" if row.sequence is None else str(row.sequence))

        action_rect = self.action_rect(rect)
        painter.setPen(QPen(QColor(self.theme.success), 1))
        painter.setBrush(QColor(self.theme.success_background))
        painter.drawRoundedRect(action_rect, 13, 13)

        time_text = format_relative_time(row.item.timestamp)
        time_rect = QRect(action_rect.left() - 58, rect.top() + 16, 50, 20)
        painter.setPen(QPen(QColor(self.theme.card_border), 1))
        painter.setBrush(QColor(self.theme.search_background))
        painter.drawRoundedRect(time_rect, 10, 10)
        painter.setPen(QColor(self.theme.card_meta))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(time_rect, Qt.AlignCenter, time_text)

        feedback_text = feedback_text_for_state(feedback)
        feedback_width = 52 if feedback_text else 0
        feedback_rect = QRect(time_rect.left() - feedback_width - 6, rect.top() + 16, feedback_width, 20)
        if feedback_text:
            color = self.theme.success if feedback == "copied" else self.theme.failure
            fill = self.theme.success_background if feedback == "copied" else self.theme.failure_background
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(QColor(fill))
            painter.drawRoundedRect(feedback_rect, 10, 10)
            painter.setPen(QColor(color))
            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            painter.drawText(feedback_rect, Qt.AlignCenter, feedback_text)

        text_left = sequence_rect.right() + 10
        text_right = feedback_rect.left() - 8 if feedback_text else time_rect.left() - 8
        text_rect = QRect(text_left, rect.top() + 8, max(20, text_right - text_left), rect.height() - 16)
        painter.setPen(QColor(self.theme.card_text))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, row.item.preview)

        painter.restore()

    def action_rect(self, row_rect: QRect) -> QRect:
        return QRect(row_rect.right() - 26, row_rect.top(), 26, row_rect.height())


class HistoryList(QListView):
    item_clicked = Signal(str)
    item_delete_requested = Signal(str)

    def __init__(self, theme: ThemePalette, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._model = HistoryListModel(parent=self)
        self._delegate = HistoryDelegate(theme, self)
        self.setModel(self._model)
        self.setItemDelegate(self._delegate)
        self.setMouseTracking(True)
        self.setSpacing(4)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setStyleSheet(
            """
            QListView {
                background-color: transparent;
                border: none;
                outline: none;
            }
            """
        )

    def clear(self) -> None:
        self._model.clear()

    def count(self) -> int:
        return self._model.rowCount()

    def add_history_item(self, item: ClipItem, feedback: str | None = None, *, sequence: int | None = None) -> None:
        self._model.insert_row(self.count(), HistoryRow(item, feedback, sequence))

    def prepend_history_item(self, item: ClipItem, feedback: str | None = None, *, sequence: int | None = None) -> None:
        self._model.insert_row(0, HistoryRow(item, feedback, sequence))

    def trim_to_count(self, count: int) -> None:
        self._model.trim_to_count(count)

    def apply_theme(self, theme: ThemePalette) -> None:
        self._theme = theme
        self._delegate.theme = theme
        self.viewport().update()

    def visible_feedback_text(self, item_id: str) -> str | None:
        for row in self._model.rows:
            if row.item.id == item_id:
                return feedback_text_for_state(row.feedback)
        return None

    def set_feedback(self, item_id: str, state: str | None) -> None:
        self._model.set_feedback(item_id, state)

    def row_item_id(self, row_index: int) -> str | None:
        if not 0 <= row_index < len(self._model.rows):
            return None
        return self._model.rows[row_index].item.id

    def row_sequence(self, item_id: str) -> int | None:
        for row in self._model.rows:
            if row.item.id == item_id:
                return row.sequence
        return None

    def mouseReleaseEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if not index.isValid():
            super().mouseReleaseEvent(event)
            return

        row = index.data(Qt.UserRole)
        if row is None:
            super().mouseReleaseEvent(event)
            return

        row_rect = self.visualRect(index).adjusted(0, 3, -4, -3)
        if self._delegate.action_rect(row_rect).contains(event.position().toPoint()):
            self.item_delete_requested.emit(row.item.id)
        else:
            self.item_clicked.emit(row.item.id)
        super().mouseReleaseEvent(event)
