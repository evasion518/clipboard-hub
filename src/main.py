import os
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .clipboard_store import ClipboardStore
from .clipboard_watcher import ClipboardWatcher
from .history_panel import HistoryPanel
from .sqlite_repository import SQLiteRepository
from .tab_bar import TabBar


APP_ORGANIZATION = "Greasionix"
APP_NAME = "Clipboard Hub"


def _configure_application_identity(app=None) -> None:
    app = app or QApplication.instance()
    if app is None:
        return

    set_organization_name = getattr(app, "setOrganizationName", None)
    if callable(set_organization_name):
        set_organization_name(APP_ORGANIZATION)

    set_application_name = getattr(app, "setApplicationName", None)
    if callable(set_application_name):
        set_application_name(APP_NAME)


def _default_database_path() -> Path:
    file_name = "clipboard_hub.db"

    app_data_location = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if app_data_location:
        return Path(app_data_location) / file_name

    generic_data_location = QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)
    if generic_data_location:
        return Path(generic_data_location) / APP_NAME / file_name

    if local_app_data := os.environ.get("LOCALAPPDATA"):
        return Path(local_app_data) / APP_NAME / file_name
    if xdg_data_home := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg_data_home) / "clipboard-hub" / file_name
    return Path.home() / ".local" / "share" / "clipboard-hub" / file_name


class ClipboardHub:
    def __init__(self, db_path: str | Path | None = None):
        _configure_application_identity()
        self._shutdown_complete = False
        self._panel_position: tuple[int, int] | None = None
        self._repository = SQLiteRepository.open_with_recovery(db_path or _default_database_path())
        self._store = ClipboardStore(repository=self._repository)
        self._watcher = ClipboardWatcher(self._store)
        self._tab = TabBar()
        self._panel = HistoryPanel(self._store, self._watcher, theme_mode="system")

        self._tab.panel_show_requested.connect(self._on_tab_enter)
        self._tab.panel_hide_requested.connect(self._on_tab_leave)
        self._tab.position_changed.connect(self._on_tab_moved)

        self._setup_tray()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)
        self._tab.show()

    def _setup_tray(self):
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("Clipboard Hub")
        icon = QApplication.style().standardIcon(QStyle.SP_FileIcon)
        self._tray.setIcon(icon)

        menu = QMenu()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(QApplication.quit)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def shutdown(self):
        if self._shutdown_complete:
            return

        self._shutdown_complete = True
        self._quiesce_watcher()
        try:
            self._repository.checkpoint()
        finally:
            self._repository.close()

    def _quiesce_watcher(self):
        stop = getattr(self._watcher, "stop", None)
        if callable(stop):
            stop()
            return

        timer = getattr(self._watcher, "_timer", None)
        if timer is not None and hasattr(timer, "stop"):
            timer.stop()

    def _on_tab_enter(self):
        self._panel.notify_mouse_enter()
        self._panel.show_at(*self._tab.current_panel_position())

    def _on_tab_moved(self, x: int, y: int):
        self._panel_position = (x, y)
        if self._panel.isVisible():
            self._panel.move(x, y)

    def _on_tab_leave(self):
        self._panel.notify_mouse_leave()


def main():
    app = QApplication(sys.argv)
    _configure_application_identity(app)
    app.setQuitOnLastWindowClosed(False)
    hub = ClipboardHub()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
