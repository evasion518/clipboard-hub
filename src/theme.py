from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemePalette:
    panel_background: str
    panel_border_start: str
    panel_border_end: str
    search_background: str
    search_text: str
    search_border: str
    search_focus: str
    card_background: str
    card_border: str
    card_text: str
    card_meta: str
    success: str
    success_background: str
    failure: str
    failure_background: str
    danger: str
    empty_text: str


LIGHT_THEME = ThemePalette(
    panel_background="#E8F7FBFF",
    panel_border_start="#FCFFFFFF",
    panel_border_end="#9FCFDFEE",
    search_background="#E2FFFFFF",
    search_text="#203246",
    search_border="rgba(190, 209, 228, 218)",
    search_focus="#94B7DD",
    card_background="#D8FFFFFF",
    card_border="#A8D7E4F0",
    card_text="#1D2E40",
    card_meta="#627587",
    success="#6FAF98",
    success_background="#E3F5ED",
    failure="#C48796",
    failure_background="#F9EDEF",
    danger="#D08B95",
    empty_text="#8093A6",
)


DARK_THEME = ThemePalette(
    panel_background="#D0141D2C",
    panel_border_start="#70F3FAFF",
    panel_border_end="#56324558",
    search_background="#C0192637",
    search_text="#F3F8FF",
    search_border="rgba(132, 170, 202, 176)",
    search_focus="#97BAE2",
    card_background="#C11B293A",
    card_border="#7596B4CF",
    card_text="#F5F9FF",
    card_meta="#BBCDDE",
    success="#98D5BC",
    success_background="#A144655B",
    failure="#EDB4BE",
    failure_background="#A0593B47",
    danger="#E8A5B0",
    empty_text="#A2B5C8",
)


SUPPORTED_THEME_MODES = ("light", "dark", "system")


def is_system_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def resolve_theme_mode(mode: str = "system", *, system_dark: bool | None = None) -> str:
    if mode == "system":
        if system_dark is None:
            system_dark = is_system_dark()
        return "dark" if system_dark else "light"
    if mode in {"light", "dark"}:
        return mode
    supported = ", ".join(SUPPORTED_THEME_MODES)
    raise ValueError(f"Unsupported theme mode: {mode!r}. Supported theme modes: {supported}")


def get_theme(mode: str = "system", *, system_dark: bool | None = None) -> ThemePalette:
    resolved_mode = resolve_theme_mode(mode, system_dark=system_dark)
    return DARK_THEME if resolved_mode == "dark" else LIGHT_THEME
