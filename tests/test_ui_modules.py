from src.history_panel import HistoryPanel as PublicHistoryPanel
from src.screen_geometry import ScreenRect as PublicScreenRect
from src.tab_bar import TabBar as PublicTabBar
from src.theme import LIGHT_THEME as PUBLIC_LIGHT_THEME
from src.ui.history_card import HistoryCard, format_relative_time
from src.ui.history_list import HistoryList
from src.ui.history_panel import HistoryPanel
from src.ui.geometry import ScreenRect
from src.ui.tab_bar import TabBar
from src.ui.theme import LIGHT_THEME


def test_history_panel_ui_modules_are_split_and_public_import_still_works():
    assert PublicHistoryPanel is HistoryPanel
    assert HistoryCard.__name__ == "HistoryCard"
    assert HistoryList.__name__ == "HistoryList"
    assert format_relative_time(0, now=0)


def test_ui_support_modules_are_split_and_public_imports_still_work():
    assert PublicScreenRect is ScreenRect
    assert PublicTabBar is TabBar
    assert PUBLIC_LIGHT_THEME is LIGHT_THEME
