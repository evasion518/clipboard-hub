from PySide6.QtCore import Qt, QPoint, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QApplication, QGraphicsDropShadowEffect
from PySide6.QtGui import QMouseEvent, QPainter, QBrush, QColor, QPen, QLinearGradient

from .history_panel import PANEL_SIZE
from .screen_geometry import ScreenRect, choose_screen, panel_position, top_right_position
from .theme import get_theme


class TabBar(QWidget):
    panel_show_requested = Signal()
    panel_hide_requested = Signal()
    position_changed = Signal(int, int)

    TAB_WIDTH = 120
    TAB_HEIGHT = 8
    DRAG_WIDTH = 132

    def __init__(self, parent=None, *, theme_mode: str = "system"):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.TAB_WIDTH, self.TAB_HEIGHT)

        self._drag_pos: QPoint | None = None
        self._theme_mode = theme_mode
        self._theme = get_theme(theme_mode)
        self._last_panel_position: tuple[int, int] | None = None
        app = QApplication.instance()
        self._style_hints = app.styleHints() if app is not None else None
        if self._style_hints is not None and self._theme_mode == "system":
            self._style_hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)
        self._position_top_right()
        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.timeout.connect(self._snap_to_top_right)
        QTimer.singleShot(0, self.sync_panel_position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)

        # 渐变边框：顶部透明 -> 底部加深
        gradient = QLinearGradient(0, 0, 0, self.height())
        border_start = QColor(self._theme.panel_border_start)
        border_mid = QColor(self._theme.card_border)
        border_end = QColor(self._theme.panel_border_end)
        border_start.setAlpha(80)
        border_mid.setAlpha(140)
        border_end.setAlpha(180)
        gradient.setColorAt(0.0, border_start)
        gradient.setColorAt(0.5, border_mid)
        gradient.setColorAt(1.0, border_end)

        fill = QColor(self._theme.panel_background)
        fill.setAlpha(180)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(gradient, 0.9))
        painter.drawRoundedRect(rect, 4, 4)

    def _position_top_right(self):
        screen = self._current_screen_rect()
        if screen is None:
            return

        x, y = top_right_position(screen, (self.width(), self.height()))
        self.move(x, y)

    def _snap_to_top_right(self):
        screen = self._current_screen_rect()
        if screen is None:
            return

        target_x, target_y = top_right_position(screen, (self.width(), self.height()))
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(250)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setEndValue(QPoint(target_x, target_y))
        self._anim.finished.connect(self.sync_panel_position)
        self._anim.start()

    def _current_screen_rect(self, point: QPoint | None = None) -> ScreenRect | None:
        screens = [
            ScreenRect.from_rect(screen.availableGeometry())
            for screen in QApplication.screens()
        ]
        if not screens:
            return None

        if point is not None:
            return choose_screen(screens, (point.x(), point.y()))

        frame = ScreenRect.from_rect(self.frameGeometry())
        return choose_screen(screens, frame.center)

    def sync_panel_position(self, anchor_point: QPoint | None = None):
        screen = self._current_screen_rect(anchor_point)
        if screen is None:
            return

        tab_rect = ScreenRect.from_rect(self.geometry())
        panel_x, panel_y = panel_position(tab_rect, PANEL_SIZE, screen)
        self._last_panel_position = (panel_x, panel_y)
        self.position_changed.emit(panel_x, panel_y)

    def current_panel_position(self) -> tuple[int, int]:
        if self._last_panel_position is None:
            self.sync_panel_position()
        return self._last_panel_position or (self.x(), self.y() + self.height())

    def _on_system_color_scheme_changed(self, _scheme) -> None:
        if self._theme_mode != "system":
            return
        self._theme = get_theme("system")
        self.update()

    def enterEvent(self, event):
        self.panel_show_requested.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.panel_hide_requested.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._snap_timer.stop()
            self.setFixedSize(self.DRAG_WIDTH, self.TAB_HEIGHT)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self.sync_panel_position(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        self.setFixedSize(self.TAB_WIDTH, self.TAB_HEIGHT)
        self.sync_panel_position(event.globalPosition().toPoint())
        self._snap_timer.start(600)
        super().mouseReleaseEvent(event)
