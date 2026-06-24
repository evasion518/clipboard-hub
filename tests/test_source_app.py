import ctypes

from src.source_app import SourceAppProvider, SourceInfo, WindowsForegroundApi


class FakeWindowsForegroundApi:
    def __init__(self, *, image_name=r"C:\Program Files\Google\Chrome\Application\chrome.exe", window_title="OpenAI - ChatGPT"):
        self._image_name = image_name
        self._window_title = window_title

    def get_foreground_window(self):
        return object()

    def get_window_text(self, hwnd):
        assert hwnd is not None
        return self._window_title

    def get_window_pid(self, hwnd):
        assert hwnd is not None
        return 4321

    def get_process_image_name(self, pid):
        assert pid == 4321
        return self._image_name


class FailingWindowsForegroundApi:
    def get_foreground_window(self):
        raise OSError("foreground window unavailable")


class RuntimeFailingWindowsForegroundApi(FakeWindowsForegroundApi):
    def get_window_pid(self, hwnd):
        raise RuntimeError("pid unavailable")


class AttributeFailingWindowsForegroundApi(FakeWindowsForegroundApi):
    def get_process_image_name(self, pid):
        raise AttributeError("image name unavailable")


class OSErrorFailingLaterWindowsForegroundApi(FakeWindowsForegroundApi):
    def __init__(self):
        super().__init__()
        self.calls = []

    def get_foreground_window(self):
        self.calls.append("get_foreground_window")
        return super().get_foreground_window()

    def get_window_text(self, hwnd):
        self.calls.append("get_window_text")
        return super().get_window_text(hwnd)

    def get_window_pid(self, hwnd):
        self.calls.append("get_window_pid")
        raise OSError("pid unavailable")

    def get_process_image_name(self, pid):
        self.calls.append("get_process_image_name")
        return super().get_process_image_name(pid)


class FakeFunction:
    def __init__(self):
        self.argtypes = None
        self.restype = None

    def __call__(self, *args, **kwargs):
        raise AssertionError("not expected to be called during signature setup")


class FakeLibrary:
    def __init__(self, names):
        for name in names:
            setattr(self, name, FakeFunction())


def test_windows_api_declares_pointer_safe_signatures(monkeypatch):
    user32 = FakeLibrary(
        [
            "GetForegroundWindow",
            "GetWindowTextLengthW",
            "GetWindowTextW",
            "GetWindowThreadProcessId",
        ]
    )
    kernel32 = FakeLibrary(["OpenProcess", "CloseHandle"])
    psapi = FakeLibrary(["GetProcessImageFileNameW"])
    libraries = {"user32": user32, "kernel32": kernel32, "psapi": psapi}

    def fake_windll(name, use_last_error=True):
        assert use_last_error is True
        return libraries[name]

    monkeypatch.setattr(ctypes, "WinDLL", fake_windll)

    WindowsForegroundApi()

    assert user32.GetForegroundWindow.argtypes == []
    assert user32.GetForegroundWindow.restype is ctypes.c_void_p
    assert user32.GetWindowTextLengthW.argtypes == [ctypes.c_void_p]
    assert user32.GetWindowTextLengthW.restype == ctypes.c_int
    assert user32.GetWindowTextW.argtypes == [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    assert user32.GetWindowTextW.restype == ctypes.c_int
    assert user32.GetWindowThreadProcessId.argtypes == [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    assert user32.GetWindowThreadProcessId.restype == ctypes.c_ulong
    assert kernel32.OpenProcess.argtypes == [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    assert kernel32.OpenProcess.restype is ctypes.c_void_p
    assert kernel32.CloseHandle.argtypes == [ctypes.c_void_p]
    assert kernel32.CloseHandle.restype == ctypes.c_int
    assert psapi.GetProcessImageFileNameW.argtypes == [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong]
    assert psapi.GetProcessImageFileNameW.restype == ctypes.c_ulong


def test_provider_returns_executable_name_and_window_title():
    provider = SourceAppProvider(
        api=FakeWindowsForegroundApi(
            image_name=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            window_title="Inbox - Gmail",
        )
    )

    info = provider.get()

    assert info == SourceInfo(app="chrome.exe", window="Inbox - Gmail")


def test_provider_degrades_to_unknown_when_api_calls_fail():
    provider = SourceAppProvider(api=FailingWindowsForegroundApi())

    info = provider.get()

    assert info == SourceInfo(app="unknown", window=None)


def test_provider_degrades_to_unknown_on_runtime_error_from_later_api_step():
    provider = SourceAppProvider(api=RuntimeFailingWindowsForegroundApi())

    info = provider.get()

    assert info == SourceInfo(app="unknown", window=None)


def test_provider_degrades_to_unknown_on_attribute_error_from_later_api_step():
    provider = SourceAppProvider(api=AttributeFailingWindowsForegroundApi())

    info = provider.get()

    assert info == SourceInfo(app="unknown", window=None)


def test_provider_degrades_to_unknown_on_oserror_from_later_api_step():
    api = OSErrorFailingLaterWindowsForegroundApi()
    provider = SourceAppProvider(api=api)

    info = provider.get()

    assert info == SourceInfo(app="unknown", window=None)
    assert api.calls == [
        "get_foreground_window",
        "get_window_text",
        "get_window_pid",
    ]
