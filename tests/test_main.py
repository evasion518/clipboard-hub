from pathlib import Path

import pytest

import src.main as main_module


class _Signal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class _FakeAction:
    def __init__(self):
        self.triggered = _Signal()


class _FakeMenu:
    def __init__(self):
        self.actions = []

    def addAction(self, _label):
        action = _FakeAction()
        self.actions.append(action)
        return action


class _FakeTray:
    instances = []

    def __init__(self):
        self.tooltip = None
        self.icon = None
        self.menu = None
        self.shown = False
        _FakeTray.instances.append(self)

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setIcon(self, icon):
        self.icon = icon

    def setContextMenu(self, menu):
        self.menu = menu

    def show(self):
        self.shown = True


class _FakeApp:
    aboutToQuit = _Signal()
    quit_calls = 0
    organization_name = None
    application_name = None

    @classmethod
    def instance(cls):
        return cls

    @classmethod
    def style(cls):
        return cls

    @classmethod
    def standardIcon(cls, *_args, **_kwargs):
        return "icon"

    @classmethod
    def quit(cls):
        cls.quit_calls += 1

    @classmethod
    def setOrganizationName(cls, name):
        cls.organization_name = name

    @classmethod
    def setApplicationName(cls, name):
        cls.application_name = name


class _FakeStyle:
    SP_FileIcon = object()


class _FakeGeometry:
    def right(self):
        return 200

    def bottom(self):
        return 50


class _FakeTabBar:
    def __init__(self):
        self.panel_show_requested = _Signal()
        self.panel_hide_requested = _Signal()
        self.position_changed = _Signal()
        self.show_calls = 0
        self.current_position = (1500, 6)

    def show(self):
        self.show_calls += 1

    def geometry(self):
        return _FakeGeometry()

    def current_panel_position(self):
        return self.current_position


class _FakeHistoryPanel:
    def __init__(self, store, watcher, **kwargs):
        self.store = store
        self.watcher = watcher
        self.kwargs = kwargs
        self.show_at_calls = []

    def notify_mouse_enter(self):
        pass

    def show_at(self, *args):
        self.show_at_calls.append(args)

    def isVisible(self):
        return False

    def move(self, *_args):
        pass

    def notify_mouse_leave(self):
        pass

    def width(self):
        return 100


class _FakeWatcher:
    def __init__(self, store):
        self.store = store


class _FakeTimer:
    def __init__(self, calls):
        self._calls = calls

    def stop(self):
        self._calls.append("watcher.stop")


@pytest.fixture
def patched_main(monkeypatch):
    _FakeTray.instances.clear()
    _FakeApp.aboutToQuit = _Signal()
    _FakeApp.quit_calls = 0
    _FakeApp.organization_name = None
    _FakeApp.application_name = None

    monkeypatch.setattr(main_module, "QApplication", _FakeApp)
    monkeypatch.setattr(main_module, "QSystemTrayIcon", _FakeTray)
    monkeypatch.setattr(main_module, "QMenu", _FakeMenu)
    monkeypatch.setattr(main_module, "QStyle", _FakeStyle)
    monkeypatch.setattr(main_module, "TabBar", _FakeTabBar)
    monkeypatch.setattr(main_module, "HistoryPanel", _FakeHistoryPanel)
    monkeypatch.setattr(main_module, "ClipboardWatcher", _FakeWatcher)


def test_clipboard_hub_uses_recovery_opened_repository_for_store(monkeypatch, patched_main, tmp_path):
    db_path = tmp_path / "hub.db"
    repository = object()
    calls = []

    def fake_open_with_recovery(path):
        calls.append(("open", path))
        return repository

    def fail_constructor(*_args, **_kwargs):
        raise AssertionError("raw SQLiteRepository constructor should not be used")

    def fake_store(*, repository=None, **_kwargs):
        calls.append(("store", repository))
        return object()

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(fake_open_with_recovery))
    monkeypatch.setattr(main_module, "ClipboardStore", fake_store)
    monkeypatch.setattr(main_module, "_default_database_path", lambda: db_path)

    hub = main_module.ClipboardHub()

    assert hub is not None
    assert calls == [("open", db_path), ("store", repository)]


def test_clipboard_hub_logs_startup_and_database_path(monkeypatch, patched_main, tmp_path, caplog):
    db_path = tmp_path / "hub.db"

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: object()))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "_default_database_path", lambda: db_path)

    with caplog.at_level("INFO", logger="clipboard_hub"):
        main_module.ClipboardHub()

    messages = [record.getMessage() for record in caplog.records]
    assert "Clipboard Hub starting" in messages
    assert f"Using database at {db_path}" in messages


def test_clipboard_hub_configures_qt_application_identity(monkeypatch, patched_main, tmp_path):
    repository = object()

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: repository))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "_default_database_path", lambda: tmp_path / "hub.db")

    main_module.ClipboardHub()

    assert _FakeApp.organization_name == "Greasionix"
    assert _FakeApp.application_name == "Clipboard Hub"


def test_clipboard_hub_constructs_history_panel_in_system_theme(monkeypatch, patched_main, tmp_path):
    repository = object()
    created_panels = []

    class CapturingHistoryPanel(_FakeHistoryPanel):
        def __init__(self, store, watcher, **kwargs):
            super().__init__(store, watcher, **kwargs)
            created_panels.append(self)

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: repository))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "HistoryPanel", CapturingHistoryPanel)
    monkeypatch.setattr(main_module, "_default_database_path", lambda: tmp_path / "hub.db")

    main_module.ClipboardHub()

    assert len(created_panels) == 1
    assert created_panels[0].kwargs["theme_mode"] == "system"


def test_clipboard_hub_shows_panel_at_last_tab_computed_position(monkeypatch, patched_main, tmp_path):
    repository = object()
    created_panels = []

    class CapturingHistoryPanel(_FakeHistoryPanel):
        def __init__(self, store, watcher, **kwargs):
            super().__init__(store, watcher, **kwargs)
            created_panels.append(self)

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: repository))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "HistoryPanel", CapturingHistoryPanel)
    monkeypatch.setattr(main_module, "_default_database_path", lambda: tmp_path / "hub.db")

    hub = main_module.ClipboardHub()
    hub._tab.current_position = (1400, 106)
    hub._on_tab_enter()

    assert created_panels[0].show_at_calls[-1] == (1400, 106)


def test_clipboard_hub_derives_database_path_when_not_provided(monkeypatch, patched_main, tmp_path):
    derived_path = tmp_path / "derived.db"
    seen = []

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: seen.append(path) or object()))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "_default_database_path", lambda: derived_path)

    main_module.ClipboardHub()

    assert seen == [derived_path]


def test_app_exit_checkpoints_and_closes_repository_once(monkeypatch, patched_main, tmp_path):
    class FakeRepository:
        def __init__(self):
            self.calls = []

        def checkpoint(self):
            self.calls.append("checkpoint")

        def close(self):
            self.calls.append("close")

    repository = FakeRepository()

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: repository))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "_default_database_path", lambda: tmp_path / "hub.db")

    main_module.ClipboardHub()
    tray = _FakeTray.instances[-1]

    tray.menu.actions[0].triggered.emit()
    assert _FakeApp.quit_calls == 1
    assert repository.calls == []

    _FakeApp.aboutToQuit.emit()
    assert repository.calls == ["checkpoint", "close"]

    _FakeApp.aboutToQuit.emit()
    assert repository.calls == ["checkpoint", "close"]


def test_explicit_db_path_takes_precedence_over_default(monkeypatch, patched_main, tmp_path):
    explicit_path = tmp_path / "explicit.db"
    default_path = tmp_path / "default.db"
    seen = []

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: seen.append(path) or object()))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "_default_database_path", lambda: default_path)

    main_module.ClipboardHub(db_path=explicit_path)

    assert seen == [explicit_path]


def test_default_database_path_uses_qt_appdata_location(monkeypatch):
    class FakeStandardPaths:
        AppDataLocation = object()

        @staticmethod
        def writableLocation(kind):
            assert kind is FakeStandardPaths.AppDataLocation
            return r"C:\Users\Test\AppData\Roaming\Clipboard Hub"

    monkeypatch.setattr(main_module, "QStandardPaths", FakeStandardPaths)

    path = main_module._default_database_path()

    assert path == Path(r"C:\Users\Test\AppData\Roaming\Clipboard Hub") / "clipboard_hub.db"


def test_default_database_path_falls_back_to_qt_generic_data_location(monkeypatch):
    class FakeStandardPaths:
        AppDataLocation = object()
        GenericDataLocation = object()

        @staticmethod
        def writableLocation(kind):
            if kind is FakeStandardPaths.AppDataLocation:
                return ""
            if kind is FakeStandardPaths.GenericDataLocation:
                return r"C:\Users\Test\AppData\Roaming"
            raise AssertionError(f"unexpected kind: {kind!r}")

    monkeypatch.setattr(main_module, "QStandardPaths", FakeStandardPaths)

    path = main_module._default_database_path()

    assert path == Path(r"C:\Users\Test\AppData\Roaming") / "Clipboard Hub" / "clipboard_hub.db"


def test_default_database_path_falls_back_to_localappdata(monkeypatch):
    class FakeStandardPaths:
        AppDataLocation = object()
        GenericDataLocation = object()

        @staticmethod
        def writableLocation(kind):
            if kind is FakeStandardPaths.AppDataLocation:
                return ""
            if kind is FakeStandardPaths.GenericDataLocation:
                return ""
            raise AssertionError(f"unexpected kind: {kind!r}")

    monkeypatch.setattr(main_module, "QStandardPaths", FakeStandardPaths)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Test\AppData\Local")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    path = main_module._default_database_path()

    assert path == Path(r"C:\Users\Test\AppData\Local") / "Clipboard Hub" / "clipboard_hub.db"


def test_default_database_path_falls_back_to_xdg_data_home(monkeypatch):
    class FakeStandardPaths:
        AppDataLocation = object()
        GenericDataLocation = object()

        @staticmethod
        def writableLocation(kind):
            if kind is FakeStandardPaths.AppDataLocation:
                return ""
            if kind is FakeStandardPaths.GenericDataLocation:
                return ""
            raise AssertionError(f"unexpected kind: {kind!r}")

    monkeypatch.setattr(main_module, "QStandardPaths", FakeStandardPaths)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/home/test/.local/share")

    path = main_module._default_database_path()

    assert path == Path("/home/test/.local/share") / "clipboard-hub" / "clipboard_hub.db"


def test_default_database_path_final_fallback_uses_home_directory_app_data_style_location(monkeypatch):
    class FakeStandardPaths:
        AppDataLocation = object()
        GenericDataLocation = object()

        @staticmethod
        def writableLocation(kind):
            if kind is FakeStandardPaths.AppDataLocation:
                return ""
            if kind is FakeStandardPaths.GenericDataLocation:
                return ""
            raise AssertionError(f"unexpected kind: {kind!r}")

    monkeypatch.setattr(main_module, "QStandardPaths", FakeStandardPaths)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(main_module.Path, "home", staticmethod(lambda: Path("/users/tester")))

    path = main_module._default_database_path()

    assert path == Path("/users/tester") / ".local" / "share" / "clipboard-hub" / "clipboard_hub.db"


def test_shutdown_quiesces_watcher_before_checkpoint_and_close(monkeypatch, patched_main, tmp_path):
    calls = []

    class FakeRepository:
        def checkpoint(self):
            calls.append("repo.checkpoint")

        def close(self):
            calls.append("repo.close")

    class FakeWatcher:
        def __init__(self, store):
            self.store = store
            self._timer = _FakeTimer(calls)

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: FakeRepository()))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "ClipboardWatcher", FakeWatcher)
    monkeypatch.setattr(main_module, "_default_database_path", lambda: tmp_path / "hub.db")

    hub = main_module.ClipboardHub()
    hub.shutdown()

    assert calls == ["watcher.stop", "repo.checkpoint", "repo.close"]


def test_shutdown_closes_repository_if_checkpoint_raises_and_stays_idempotent(monkeypatch, patched_main, tmp_path):
    calls = []

    class CheckpointBoom(RuntimeError):
        pass

    class FakeRepository:
        def checkpoint(self):
            calls.append("repo.checkpoint")
            raise CheckpointBoom("boom")

        def close(self):
            calls.append("repo.close")

    class FakeWatcher:
        def __init__(self, store):
            self.store = store
            self._timer = _FakeTimer(calls)

    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: FakeRepository()))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "ClipboardWatcher", FakeWatcher)
    monkeypatch.setattr(main_module, "_default_database_path", lambda: tmp_path / "hub.db")

    hub = main_module.ClipboardHub()

    with pytest.raises(CheckpointBoom):
        hub.shutdown()

    assert calls == ["watcher.stop", "repo.checkpoint", "repo.close"]

    hub.shutdown()
    assert calls == ["watcher.stop", "repo.checkpoint", "repo.close"]


def test_clipboard_hub_does_not_store_unused_panel_position(monkeypatch, patched_main, tmp_path):
    monkeypatch.setattr(main_module.SQLiteRepository, "open_with_recovery", staticmethod(lambda path: object()))
    monkeypatch.setattr(main_module, "ClipboardStore", lambda *, repository=None, **_kwargs: object())
    monkeypatch.setattr(main_module, "ClipboardWatcher", lambda store: object())
    monkeypatch.setattr(main_module, "_default_database_path", lambda: tmp_path / "hub.db")

    hub = main_module.ClipboardHub()
    hub._on_tab_moved(10, 20)

    assert not hasattr(hub, "_panel_position")
