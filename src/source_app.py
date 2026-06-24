from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass(frozen=True, slots=True)
class SourceInfo:
    app: str = "unknown"
    window: str | None = None


class WindowsForegroundApi:
    def __init__(self):
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        self._user32.GetForegroundWindow.argtypes = []
        self._user32.GetForegroundWindow.restype = ctypes.c_void_p

        self._user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        self._user32.GetWindowTextLengthW.restype = ctypes.c_int

        self._user32.GetWindowTextW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_int,
        ]
        self._user32.GetWindowTextW.restype = ctypes.c_int

        self._user32.GetWindowThreadProcessId.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        self._kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            ctypes.c_int,
            wintypes.DWORD,
        ]
        self._kernel32.OpenProcess.restype = ctypes.c_void_p

        self._kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.restype = ctypes.c_int

        self._psapi.GetProcessImageFileNameW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            wintypes.DWORD,
        ]
        self._psapi.GetProcessImageFileNameW.restype = wintypes.DWORD

    def get_foreground_window(self):
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            raise OSError("GetForegroundWindow failed")
        return hwnd

    def get_window_text(self, hwnd) -> str | None:
        length = self._user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = self._user32.GetWindowTextW(hwnd, buffer, len(buffer))
        if copied <= 0:
            return None
        return buffer.value or None

    def get_window_pid(self, hwnd) -> int:
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            raise OSError("GetWindowThreadProcessId failed")
        return int(pid.value)

    def get_process_image_name(self, pid: int) -> str:
        process = self._kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not process:
            raise OSError("OpenProcess failed")
        try:
            size = wintypes.DWORD(260)
            buffer = ctypes.create_unicode_buffer(size.value)
            ok = self._psapi.GetProcessImageFileNameW(process, buffer, size.value)
            if ok == 0:
                raise OSError("GetProcessImageFileNameW failed")
            return buffer.value
        finally:
            self._kernel32.CloseHandle(process)


class SourceAppProvider:
    def __init__(self, api=None):
        self._api = api or WindowsForegroundApi()

    def get(self) -> SourceInfo:
        try:
            hwnd = self._api.get_foreground_window()
            window = self._api.get_window_text(hwnd)
            pid = self._api.get_window_pid(hwnd)
            image_name = self._api.get_process_image_name(pid)
        except (OSError, RuntimeError, AttributeError):
            return SourceInfo()

        app = PureWindowsPath(image_name).name or "unknown"
        return SourceInfo(app=app, window=window)
