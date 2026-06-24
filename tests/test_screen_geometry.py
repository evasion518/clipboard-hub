from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from src.screen_geometry import ScreenRect, choose_screen, panel_position, top_right_position
from src.tab_bar import TabBar


def test_choose_screen_prefers_screen_containing_point():
    left = ScreenRect(x=0, y=0, width=1920, height=1080)
    right = ScreenRect(x=1920, y=0, width=2560, height=1440)

    chosen = choose_screen([left, right], (2200, 400))

    assert chosen == right


def test_choose_screen_falls_back_to_nearest_screen():
    left = ScreenRect(x=0, y=0, width=1920, height=1080)
    right = ScreenRect(x=1920, y=0, width=2560, height=1440)

    chosen = choose_screen([left, right], (4700, 500))

    assert chosen == right


def test_choose_screen_handles_negative_coordinate_displays():
    left = ScreenRect(x=-1600, y=0, width=1600, height=900)
    primary = ScreenRect(x=0, y=0, width=1920, height=1080)

    chosen = choose_screen([left, primary], (-200, 100))

    assert chosen == left


def test_choose_screen_chooses_nearest_stacked_screen():
    top = ScreenRect(x=0, y=-900, width=1600, height=900)
    bottom = ScreenRect(x=0, y=0, width=1600, height=900)

    chosen = choose_screen([top, bottom], (700, -950))

    assert chosen == top


def test_top_right_position_stays_inside_screen():
    screen = ScreenRect(x=100, y=50, width=120, height=80)

    position = top_right_position(screen, size=(140, 6))

    assert position == (100, 50)


def test_panel_position_opens_upward_when_below_space_is_insufficient():
    screen = ScreenRect(x=0, y=0, width=1920, height=1080)
    anchor = ScreenRect(x=1800, y=1074, width=120, height=6)

    position = panel_position(
        anchor_rect=anchor,
        panel_size=(420, 520),
        screen=screen,
    )

    assert position == (1500, 554)


def test_panel_position_clamps_horizontally_to_screen():
    screen = ScreenRect(x=1920, y=0, width=1280, height=1024)
    anchor = ScreenRect(x=1940, y=50, width=120, height=6)

    position = panel_position(
        anchor_rect=anchor,
        panel_size=(420, 520),
        screen=screen,
    )

    assert position == (1920, 56)


def test_panel_position_clamps_with_negative_origin_screen():
    screen = ScreenRect(x=-1280, y=0, width=1280, height=1024)
    anchor = ScreenRect(x=-1260, y=40, width=120, height=6)

    position = panel_position(
        anchor_rect=anchor,
        panel_size=(420, 520),
        screen=screen,
    )

    assert position == (-1280, 46)


class _FakeQtRect:
    def __init__(self, x, y, width, height):
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._width

    def height(self):
        return self._height


class _FakeScreen:
    def __init__(self, rect):
        self._rect = rect

    def availableGeometry(self):
        return _FakeQtRect(*self._rect)


def _mouse_event(event_type, position):
    point = QPointF(*position)
    return QMouseEvent(
        event_type,
        point,
        point,
        point,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )


def test_tab_bar_emits_initial_position_after_consumer_hookup(qapp, monkeypatch):
    screen = _FakeScreen((0, 0, 1920, 1080))
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [screen]))

    tab = TabBar()
    positions = []
    tab.position_changed.connect(lambda x, y: positions.append((x, y)))

    QApplication.processEvents()

    assert positions == [(1500, 8)]


def test_tab_bar_emits_updated_panel_position_immediately_on_release(qapp, monkeypatch):
    screen = _FakeScreen((0, 0, 1920, 1080))
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [screen]))

    tab = TabBar()
    positions = []
    tab.position_changed.connect(lambda x, y: positions.append((x, y)))
    QApplication.processEvents()
    positions.clear()

    tab.mousePressEvent(_mouse_event(QMouseEvent.MouseButtonPress, (10, 3)))
    tab.move(1700, 100)

    tab.mouseReleaseEvent(_mouse_event(QMouseEvent.MouseButtonRelease, (10, 3)))

    assert positions == [(1400, 108)]


def test_tab_bar_tracks_current_panel_position(qapp, monkeypatch):
    screen = _FakeScreen((0, 0, 1920, 1080))
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [screen]))

    tab = TabBar()
    QApplication.processEvents()

    assert tab.current_panel_position() == (1500, 8)


def test_tab_bar_refreshes_theme_when_system_color_scheme_changes(qapp, monkeypatch):
    from src import tab_bar as tab_bar_module

    light_theme = object()
    dark_theme = object()
    current_mode = {"value": "light"}

    def fake_get_theme(mode="system"):
        if mode == "system":
            return light_theme if current_mode["value"] == "light" else dark_theme
        return light_theme

    screen = _FakeScreen((0, 0, 1920, 1080))
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [screen]))
    monkeypatch.setattr(tab_bar_module, "get_theme", fake_get_theme)

    tab = TabBar()
    assert tab._theme is light_theme

    current_mode["value"] = "dark"
    tab._on_system_color_scheme_changed(Qt.ColorScheme.Dark)

    assert tab._theme is dark_theme


def test_tab_bar_uses_explicit_theme_mode_when_provided(qapp, monkeypatch):
    from src import tab_bar as tab_bar_module

    light_theme = object()
    dark_theme = object()

    def fake_get_theme(mode="system"):
        return light_theme if mode == "light" else dark_theme

    screen = _FakeScreen((0, 0, 1920, 1080))
    monkeypatch.setattr(QApplication, "screens", staticmethod(lambda: [screen]))
    monkeypatch.setattr(tab_bar_module, "get_theme", fake_get_theme)

    tab = TabBar(theme_mode="light")

    assert tab._theme is light_theme
