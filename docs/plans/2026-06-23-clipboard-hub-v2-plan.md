# Clipboard Hub V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Clipboard Hub 升级为具备 SQLite 持久化、多格式剪贴板恢复、来源应用、当前屏幕吸附、Fluent 亚克力界面和复制状态反馈的 Windows 桌面工具。

**Architecture:** 将剪贴板记录模型、SQLite 仓储、来源应用检测、剪贴板读写和屏幕几何计算拆成独立模块。`ClipboardStore` 负责业务规则和 UI 信号，`ClipboardWatcher` 只负责捕获，`HistoryPanel` 通过专用 writer 写回多格式内容并显示状态。

**Tech Stack:** Python 3.11、PySide6、标准库 `sqlite3`、Windows `ctypes` API、pytest。

---

## 实施约束

- 工作目录：`D:\Greasionix\clipboard-hub`
- Python：`C:\Users\Administrator\global-venv\Scripts\python.exe`
- GUI 测试统一设置：`$env:QT_QPA_PLATFORM='offscreen'`
- 每个任务遵循测试先行：失败测试 → 最小实现 → 全量回归。
- 当前目录不是 Git 仓库。每个任务的“提交”步骤仅在执行阶段发现 Git 已初始化时运行；否则记录变更文件并继续，不擅自初始化仓库。
- 不实现数据库加密、云同步、OCR、应用黑名单、文件列表复制或 SQLite FTS。

## 文件结构

### 新建

- `src/clip_item.py`：不可变剪贴板记录模型、内容指纹、大小和预览辅助函数。
- `src/sqlite_repository.py`：SQLite schema、CRUD、载入、统计、淘汰和损坏恢复。
- `src/source_app.py`：Windows 前台进程名和窗口标题获取。
- `src/clipboard_codec.py`：`QMimeData` 与 `ClipItem` 之间的双向转换。
- `src/screen_geometry.py`：显示器选择、吸附点和面板边界计算。
- `src/theme.py`：深浅主题 token 与 Fluent 样式。
- `tests/test_clip_item.py`
- `tests/test_sqlite_repository.py`
- `tests/test_source_app.py`
- `tests/test_clipboard_codec.py`
- `tests/test_screen_geometry.py`
- `tests/test_history_panel.py`
- `tests/test_main.py`

### 修改

- `src/clipboard_store.py`：改用新模型和仓储，执行去重、搜索与容量淘汰。
- `src/clipboard_watcher.py`：捕获同一次复制的全部 MIME 格式和精确自复制匹配。
- `src/tab_bar.py`：当前屏幕吸附和 Fluent 胶囊外观。
- `src/history_panel.py`：420px Fluent 面板、卡片元数据、缩略图和状态反馈。
- `src/main.py`：数据库路径、降级模式、服务装配和退出检查点。
- `tests/test_clipboard_store.py`
- `tests/test_clipboard_watcher.py`
- `tests/conftest.py`
- `README.md`
- `docs/specs/2026-06-23-clipboard-hub-v2-design.md`

---

### Task 1: 建立 V2 剪贴板记录模型

**Files:**
- Create: `src/clip_item.py`
- Create: `tests/test_clip_item.py`
- Modify: `src/clipboard_store.py`

- [ ] **Step 1: 写模型失败测试**

```python
# tests/test_clip_item.py
from src.clip_item import ClipItem, build_content_hash, build_preview


def test_clip_item_calculates_size_and_hash():
    item = ClipItem.create(
        text="hello",
        html="<b>hello</b>",
        image_png=b"\x89PNG",
        source_app="chrome.exe",
        source_window="Example",
    )
    assert item.size_bytes == len("hello".encode()) + len("<b>hello</b>".encode()) + 4
    assert item.content_hash == build_content_hash("hello", "<b>hello</b>", b"\x89PNG")


def test_build_preview_prefers_text_then_html_then_image():
    assert build_preview("plain", "<b>rich</b>", None) == "plain"
    assert build_preview(None, "<b>rich</b>", None) == "rich"
    assert build_preview(None, None, b"png", image_size=(12, 8)) == "图片 (12×8)"


def test_clip_item_requires_at_least_one_payload():
    try:
        ClipItem.create()
    except ValueError as exc:
        assert str(exc) == "clip item requires content"
    else:
        raise AssertionError("ValueError was not raised")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clip_item.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'src.clip_item'`.

- [ ] **Step 3: 实现模型与辅助函数**

```python
# src/clip_item.py
from __future__ import annotations

import hashlib
import html as html_module
import re
import time
import uuid
from dataclasses import dataclass, field


def strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html_module.unescape(without_tags).split())


def build_content_hash(
    text: str | None,
    html: str | None,
    image_png: bytes | None,
) -> str:
    digest = hashlib.sha256()
    for name, payload in (
        (b"text", text.encode("utf-8") if text is not None else None),
        (b"html", html.encode("utf-8") if html is not None else None),
        (b"image", image_png),
    ):
        digest.update(name)
        if payload is None:
            digest.update(b"\x00")
        else:
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return digest.hexdigest()


def build_preview(
    text: str | None,
    html: str | None,
    image_png: bytes | None,
    image_size: tuple[int, int] | None = None,
) -> str:
    if text and text.strip():
        return " ".join(text.split())[:80]
    if html and strip_html(html):
        return strip_html(html)[:80]
    if image_png is not None:
        if image_size:
            return f"图片 ({image_size[0]}×{image_size[1]})"
        return "图片"
    raise ValueError("clip item requires content")


@dataclass(frozen=True, slots=True)
class ClipItem:
    text: str | None = None
    html: str | None = None
    image_png: bytes | None = None
    preview: str = ""
    source_app: str = "unknown"
    source_window: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    content_hash: str = ""
    size_bytes: int = 0

    @classmethod
    def create(
        cls,
        *,
        text: str | None = None,
        html: str | None = None,
        image_png: bytes | None = None,
        preview: str | None = None,
        source_app: str = "unknown",
        source_window: str | None = None,
        image_size: tuple[int, int] | None = None,
        id: str | None = None,
        timestamp: float | None = None,
    ) -> "ClipItem":
        if not any((text and text.strip(), html and html.strip(), image_png)):
            raise ValueError("clip item requires content")
        size_bytes = (
            len(text.encode("utf-8")) if text is not None else 0
        ) + (
            len(html.encode("utf-8")) if html is not None else 0
        ) + (
            len(image_png) if image_png is not None else 0
        )
        return cls(
            text=text,
            html=html,
            image_png=image_png,
            preview=preview or build_preview(text, html, image_png, image_size),
            source_app=source_app or "unknown",
            source_window=source_window,
            id=id or str(uuid.uuid4()),
            timestamp=time.time() if timestamp is None else timestamp,
            content_hash=build_content_hash(text, html, image_png),
            size_bytes=size_bytes,
        )
```

- [ ] **Step 4: 让 Store 从新模块导入模型**

在 `src/clipboard_store.py` 删除旧 `ClipItem` dataclass，加入：

```python
from .clip_item import ClipItem
```

此步骤只迁移导入，暂时保留 Store 的其余行为，避免一次改动过大。

- [ ] **Step 5: 运行模型和现有 Store 测试**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clip_item.py tests/test_clipboard_store.py -v
```

Expected: 新模型测试通过；旧 Store 测试因构造参数变化失败，失败清单作为 Task 3 的迁移输入。

- [ ] **Step 6: 提交**

```powershell
git add src/clip_item.py src/clipboard_store.py tests/test_clip_item.py
git commit -m "feat: add v2 clipboard item model"
```

仅在 `git status` 成功时执行。

---

### Task 2: 实现 SQLite 仓储

**Files:**
- Create: `src/sqlite_repository.py`
- Create: `tests/test_sqlite_repository.py`

- [ ] **Step 1: 写仓储失败测试**

```python
# tests/test_sqlite_repository.py
from src.clip_item import ClipItem
from src.sqlite_repository import SQLiteRepository


def test_repository_round_trip(tmp_path):
    path = tmp_path / "clipboard.db"
    repo = SQLiteRepository(path)
    item = ClipItem.create(
        text="plain",
        html="<b>plain</b>",
        image_png=b"png",
        source_app="chrome.exe",
        source_window="Page",
        timestamp=123.0,
    )
    repo.insert(item)
    repo.close()

    reopened = SQLiteRepository(path)
    loaded = reopened.load_all()
    assert loaded == [item]


def test_repository_delete_and_totals(tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    first = ClipItem.create(text="a")
    second = ClipItem.create(text="bb")
    repo.insert(first)
    repo.insert(second)
    assert repo.totals() == (2, 3)
    repo.delete(first.id)
    assert repo.load_all() == [second]
    assert repo.totals() == (1, 2)


def test_repository_delete_oldest(tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    oldest = ClipItem.create(text="old", timestamp=1)
    newest = ClipItem.create(text="new", timestamp=2)
    repo.insert(oldest)
    repo.insert(newest)
    removed = repo.delete_oldest()
    assert removed == oldest.id
    assert repo.load_all() == [newest]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_sqlite_repository.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: 实现 schema、CRUD 和检查点**

```python
# src/sqlite_repository.py
from __future__ import annotations

import sqlite3
from pathlib import Path

from .clip_item import ClipItem


SCHEMA = """
CREATE TABLE IF NOT EXISTS clipboard_items (
    id TEXT PRIMARY KEY,
    text_content TEXT,
    html_content TEXT,
    image_png BLOB,
    preview TEXT NOT NULL,
    created_at REAL NOT NULL,
    source_app TEXT NOT NULL DEFAULT 'unknown',
    source_window TEXT,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clipboard_items_created_at
ON clipboard_items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clipboard_items_content_hash
ON clipboard_items(content_hash);
"""


class SQLiteRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def insert(self, item: ClipItem) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO clipboard_items (
                    id, text_content, html_content, image_png, preview,
                    created_at, source_app, source_window, content_hash, size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id, item.text, item.html, item.image_png, item.preview,
                    item.timestamp, item.source_app, item.source_window,
                    item.content_hash, item.size_bytes,
                ),
            )

    def delete(self, item_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM clipboard_items WHERE id = ?", (item_id,)
            )
        return cursor.rowcount > 0

    def delete_oldest(self) -> str | None:
        row = self._connection.execute(
            "SELECT id FROM clipboard_items ORDER BY created_at ASC, rowid ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        self.delete(row[0])
        return row[0]

    def load_all(self) -> list[ClipItem]:
        rows = self._connection.execute(
            """
            SELECT id, text_content, html_content, image_png, preview,
                   created_at, source_app, source_window
            FROM clipboard_items
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
        return [
            ClipItem.create(
                id=row[0], text=row[1], html=row[2], image_png=row[3],
                preview=row[4], timestamp=row[5], source_app=row[6],
                source_window=row[7],
            )
            for row in rows
        ]

    def totals(self) -> tuple[int, int]:
        count, size = self._connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM clipboard_items"
        ).fetchone()
        return int(count), int(size)

    def checkpoint(self) -> None:
        self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self) -> None:
        self._connection.close()
```

- [ ] **Step 4: 运行仓储测试**

Run:

```powershell
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_sqlite_repository.py -v
```

Expected: all tests pass.

- [ ] **Step 5: 增加损坏数据库恢复测试和实现**

追加测试：

```python
def test_open_with_recovery_backs_up_corrupt_database(tmp_path):
    path = tmp_path / "clipboard.db"
    path.write_bytes(b"not sqlite")
    repo = SQLiteRepository.open_with_recovery(path)
    assert repo.load_all() == []
    assert list(tmp_path.glob("clipboard.db.corrupt-*"))
```

在 `SQLiteRepository` 增加：

```python
    @classmethod
    def open_with_recovery(cls, path: str | Path) -> "SQLiteRepository":
        path = Path(path)
        try:
            return cls(path)
        except sqlite3.DatabaseError:
            if path.exists():
                suffix = __import__("time").strftime("%Y%m%d-%H%M%S")
                path.replace(path.with_name(f"{path.name}.corrupt-{suffix}"))
            return cls(path)
```

- [ ] **Step 6: 运行测试并提交**

Run:

```powershell
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_sqlite_repository.py -v
```

Expected: all pass.

```powershell
git add src/sqlite_repository.py tests/test_sqlite_repository.py
git commit -m "feat: persist clipboard history in sqlite"
```

---

### Task 3: 改造 ClipboardStore 并实施容量限制

**Files:**
- Modify: `src/clipboard_store.py`
- Modify: `tests/test_clipboard_store.py`

- [ ] **Step 1: 用 V2 接口重写 Store 测试**

```python
# tests/test_clipboard_store.py
from PySide6.QtTest import QSignalSpy

from src.clip_item import ClipItem
from src.clipboard_store import ClipboardStore
from src.sqlite_repository import SQLiteRepository


def make_store(tmp_path, *, max_items=1000, max_bytes=200 * 1024 * 1024):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    return ClipboardStore(repo, max_items=max_items, max_bytes=max_bytes)


def test_store_loads_existing_items(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    repo.insert(ClipItem.create(text="saved", timestamp=1))
    store = ClipboardStore(repo)
    assert [item.text for item in store.get_all()] == ["saved"]


def test_store_persists_add_and_delete(qapp, tmp_path):
    store = make_store(tmp_path)
    item = ClipItem.create(text="hello")
    assert store.add(item) is True
    assert store.delete(item.id) is True
    assert store.get_all() == []


def test_store_skips_consecutive_duplicate(qapp, tmp_path):
    store = make_store(tmp_path)
    assert store.add(ClipItem.create(text="same")) is True
    assert store.add(ClipItem.create(text="same")) is False
    assert len(store.get_all()) == 1


def test_store_evicts_oldest_by_count(qapp, tmp_path):
    store = make_store(tmp_path, max_items=2)
    store.add(ClipItem.create(text="one", timestamp=1))
    store.add(ClipItem.create(text="two", timestamp=2))
    store.add(ClipItem.create(text="three", timestamp=3))
    assert [item.text for item in store.get_all()] == ["three", "two"]


def test_store_evicts_oldest_by_bytes(qapp, tmp_path):
    store = make_store(tmp_path, max_bytes=4)
    store.add(ClipItem.create(text="aa", timestamp=1))
    store.add(ClipItem.create(text="bbb", timestamp=2))
    assert [item.text for item in store.get_all()] == ["bbb"]


def test_search_includes_html_source_and_window(qapp, tmp_path):
    store = make_store(tmp_path)
    store.add(ClipItem.create(
        html="<b>Invoice</b>",
        source_app="chrome.exe",
        source_window="Accounting",
    ))
    assert len(store.search("invoice")) == 1
    assert len(store.search("chrome")) == 1
    assert len(store.search("accounting")) == 1


def test_delete_emits_only_when_item_existed(qapp, tmp_path):
    store = make_store(tmp_path)
    spy = QSignalSpy(store.items_changed)
    assert store.delete("missing") is False
    assert spy.count() == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clipboard_store.py -v
```

Expected: constructor and V2 field failures.

- [ ] **Step 3: 实现 Store**

```python
# src/clipboard_store.py
from PySide6.QtCore import QObject, Signal

from .clip_item import ClipItem, strip_html
from .sqlite_repository import SQLiteRepository


class ClipboardStore(QObject):
    items_changed = Signal()

    def __init__(
        self,
        repository: SQLiteRepository | None = None,
        *,
        max_items: int = 1000,
        max_bytes: int = 200 * 1024 * 1024,
        parent=None,
    ):
        super().__init__(parent)
        self._repository = repository
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._items = repository.load_all() if repository else []
        self._enforce_limits()

    def add(self, item: ClipItem) -> bool:
        if self._items and self._items[0].content_hash == item.content_hash:
            return False
        self._items.insert(0, item)
        if self._repository:
            self._repository.insert(item)
        self._enforce_limits()
        self.items_changed.emit()
        return True

    def delete(self, item_id: str) -> bool:
        before = len(self._items)
        self._items = [item for item in self._items if item.id != item_id]
        changed = len(self._items) != before
        if changed and self._repository:
            self._repository.delete(item_id)
        if changed:
            self.items_changed.emit()
        return changed

    def get_all(self) -> list[ClipItem]:
        return list(self._items)

    def get_by_id(self, item_id: str) -> ClipItem | None:
        return next((item for item in self._items if item.id == item_id), None)

    def search(self, keyword: str) -> list[ClipItem]:
        needle = keyword.casefold().strip()
        if not needle:
            return self.get_all()
        return [
            item for item in self._items
            if needle in "\n".join(filter(None, (
                item.text,
                strip_html(item.html) if item.html else None,
                item.preview,
                item.source_app,
                item.source_window,
            ))).casefold()
        ]

    def _enforce_limits(self) -> None:
        while self._items and (
            len(self._items) > self._max_items
            or sum(item.size_bytes for item in self._items) > self._max_bytes
        ):
            oldest = self._items.pop()
            if self._repository:
                self._repository.delete(oldest.id)
```

- [ ] **Step 4: 运行 Store 与仓储测试**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clipboard_store.py tests/test_sqlite_repository.py -v
```

Expected: all pass.

- [ ] **Step 5: 提交**

```powershell
git add src/clipboard_store.py tests/test_clipboard_store.py
git commit -m "feat: add persistent store retention rules"
```

---

### Task 4: 获取 Windows 来源应用

**Files:**
- Create: `src/source_app.py`
- Create: `tests/test_source_app.py`

- [ ] **Step 1: 写可注入 API 的失败测试**

```python
# tests/test_source_app.py
from src.source_app import SourceAppProvider


class FakeWinApi:
    def foreground_window(self):
        return 10

    def window_title(self, hwnd):
        assert hwnd == 10
        return "Example Page"

    def process_id(self, hwnd):
        return 20

    def process_image_name(self, process_id):
        assert process_id == 20
        return r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def test_source_app_returns_executable_and_title():
    source = SourceAppProvider(FakeWinApi()).get()
    assert source.app == "chrome.exe"
    assert source.window == "Example Page"


def test_source_app_degrades_to_unknown():
    class BrokenApi(FakeWinApi):
        def foreground_window(self):
            raise OSError("denied")

    source = SourceAppProvider(BrokenApi()).get()
    assert source.app == "unknown"
    assert source.window is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_source_app.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: 实现 provider 和 Windows API adapter**

```python
# src/source_app.py
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceInfo:
    app: str = "unknown"
    window: str | None = None


class WindowsForegroundApi:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def foreground_window(self) -> int:
        return ctypes.windll.user32.GetForegroundWindow()

    def window_title(self, hwnd: int) -> str | None:
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value or None

    def process_id(self, hwnd: int) -> int:
        process_id = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return int(process_id.value)

    def process_image_name(self, process_id: int) -> str | None:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            self.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id
        )
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return None
            return buffer.value
        finally:
            kernel32.CloseHandle(handle)


class SourceAppProvider:
    def __init__(self, api=None):
        self._api = api or WindowsForegroundApi()

    def get(self) -> SourceInfo:
        try:
            hwnd = self._api.foreground_window()
            title = self._api.window_title(hwnd)
            process_id = self._api.process_id(hwnd)
            image_name = self._api.process_image_name(process_id)
            app = Path(image_name).name if image_name else "unknown"
            return SourceInfo(app=app, window=title)
        except (OSError, RuntimeError, AttributeError):
            return SourceInfo()
```

- [ ] **Step 4: 运行测试并提交**

Run:

```powershell
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_source_app.py -v
```

Expected: all pass.

```powershell
git add src/source_app.py tests/test_source_app.py
git commit -m "feat: capture clipboard source application"
```

---

### Task 5: 实现多格式剪贴板编解码

**Files:**
- Create: `src/clipboard_codec.py`
- Create: `tests/test_clipboard_codec.py`

- [ ] **Step 1: 写 QMimeData 双向测试**

```python
# tests/test_clipboard_codec.py
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QImage

from src.clipboard_codec import ClipboardCodec


def test_decode_keeps_text_html_and_image(qapp):
    mime = QMimeData()
    mime.setText("plain")
    mime.setHtml("<b>plain</b>")
    image = QImage(2, 3, QImage.Format_ARGB32)
    image.fill(0xFF336699)
    mime.setImageData(image)

    item = ClipboardCodec.decode(mime, source_app="chrome.exe", source_window="Page")
    assert item.text == "plain"
    assert item.html == "<b>plain</b>"
    assert item.image_png.startswith(b"\x89PNG")
    assert item.source_app == "chrome.exe"


def test_encode_restores_all_formats(qapp):
    original = QMimeData()
    original.setText("plain")
    original.setHtml("<b>plain</b>")
    item = ClipboardCodec.decode(original)
    encoded = ClipboardCodec.encode(item)
    assert encoded.text() == "plain"
    assert encoded.html() == "<b>plain</b>"


def test_decode_rejects_empty_mime(qapp):
    assert ClipboardCodec.decode(QMimeData()) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clipboard_codec.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: 实现 codec**

```python
# src/clipboard_codec.py
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData
from PySide6.QtGui import QImage

from .clip_item import ClipItem


class ClipboardCodec:
    MAX_IMAGE_BYTES = 10 * 1024 * 1024

    @staticmethod
    def image_to_png(image: QImage) -> bytes | None:
        array = QByteArray()
        buffer = QBuffer(array)
        if not buffer.open(QIODevice.WriteOnly):
            return None
        if not image.save(buffer, "PNG"):
            return None
        data = bytes(array)
        return data if len(data) <= ClipboardCodec.MAX_IMAGE_BYTES else None

    @classmethod
    def decode(
        cls,
        mime: QMimeData,
        *,
        source_app: str = "unknown",
        source_window: str | None = None,
    ) -> ClipItem | None:
        text = mime.text() if mime.hasText() and mime.text().strip() else None
        html = mime.html() if mime.hasHtml() and mime.html().strip() else None
        image_png = None
        image_size = None
        if mime.hasImage():
            image = mime.imageData()
            if isinstance(image, QImage) and not image.isNull():
                image_png = cls.image_to_png(image)
                if image_png:
                    image_size = (image.width(), image.height())
        if not any((text, html, image_png)):
            return None
        return ClipItem.create(
            text=text,
            html=html,
            image_png=image_png,
            source_app=source_app,
            source_window=source_window,
            image_size=image_size,
        )

    @staticmethod
    def encode(item: ClipItem) -> QMimeData:
        mime = QMimeData()
        if item.text is not None:
            mime.setText(item.text)
        if item.html is not None:
            mime.setHtml(item.html)
        if item.image_png is not None:
            image = QImage()
            if not image.loadFromData(item.image_png, "PNG"):
                raise ValueError("invalid PNG payload")
            mime.setImageData(image)
        return mime
```

- [ ] **Step 4: 运行 codec 测试并提交**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clipboard_codec.py -v
```

Expected: all pass.

```powershell
git add src/clipboard_codec.py tests/test_clipboard_codec.py
git commit -m "feat: preserve clipboard mime formats"
```

---

### Task 6: 改造 ClipboardWatcher 与精确自复制跳过

**Files:**
- Modify: `src/clipboard_watcher.py`
- Modify: `tests/test_clipboard_watcher.py`

- [ ] **Step 1: 写 Watcher 行为测试**

```python
# tests/test_clipboard_watcher.py
from PySide6.QtCore import QMimeData

from src.clip_item import ClipItem
from src.clipboard_store import ClipboardStore
from src.clipboard_watcher import ClipboardWatcher
from src.source_app import SourceInfo


class FakeClipboard:
    def __init__(self, mime):
        self._mime = mime

    def mimeData(self):
        return self._mime


class FakeSourceProvider:
    def get(self):
        return SourceInfo("chrome.exe", "Page")


def test_poll_adds_one_multiformat_item(qapp):
    mime = QMimeData()
    mime.setText("plain")
    mime.setHtml("<b>plain</b>")
    store = ClipboardStore()
    watcher = ClipboardWatcher(
        store,
        clipboard=FakeClipboard(mime),
        source_provider=FakeSourceProvider(),
        autostart=False,
    )
    watcher.poll()
    item = store.get_all()[0]
    assert item.text == "plain"
    assert item.html == "<b>plain</b>"
    assert item.source_app == "chrome.exe"


def test_self_copy_skips_only_matching_hash(qapp):
    first = ClipItem.create(text="first")
    second_mime = QMimeData()
    second_mime.setText("second")
    store = ClipboardStore()
    watcher = ClipboardWatcher(
        store,
        clipboard=FakeClipboard(second_mime),
        source_provider=FakeSourceProvider(),
        autostart=False,
    )
    watcher.notify_self_copy(first.content_hash)
    watcher.poll()
    assert [item.text for item in store.get_all()] == ["second"]


def test_self_copy_matching_hash_is_skipped_once(qapp):
    item = ClipItem.create(text="same")
    mime = QMimeData()
    mime.setText("same")
    store = ClipboardStore()
    watcher = ClipboardWatcher(
        store,
        clipboard=FakeClipboard(mime),
        source_provider=FakeSourceProvider(),
        autostart=False,
    )
    watcher.notify_self_copy(item.content_hash)
    watcher.poll()
    assert store.get_all() == []
    assert watcher.pending_self_hash is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clipboard_watcher.py -v
```

Expected: constructor and method failures.

- [ ] **Step 3: 实现 Watcher**

```python
# src/clipboard_watcher.py
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from .clipboard_codec import ClipboardCodec
from .clipboard_store import ClipboardStore
from .source_app import SourceAppProvider


class ClipboardWatcher(QObject):
    def __init__(
        self,
        store: ClipboardStore,
        *,
        clipboard=None,
        source_provider=None,
        autostart: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._store = store
        self._clipboard = clipboard or QApplication.clipboard()
        self._source_provider = source_provider or SourceAppProvider()
        self.pending_self_hash: str | None = None
        self._last_seen_hash: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.poll)
        if autostart:
            self._timer.start()

    def poll(self) -> None:
        try:
            source = self._source_provider.get()
            item = ClipboardCodec.decode(
                self._clipboard.mimeData(),
                source_app=source.app,
                source_window=source.window,
            )
        except (RuntimeError, OSError, AttributeError, ValueError):
            return
        if item is None:
            return
        if self.pending_self_hash == item.content_hash:
            self.pending_self_hash = None
            self._last_seen_hash = item.content_hash
            return
        self.pending_self_hash = None
        if self._last_seen_hash == item.content_hash:
            return
        self._last_seen_hash = item.content_hash
        self._store.add(item)

    def notify_self_copy(self, content_hash: str) -> None:
        self.pending_self_hash = content_hash
```

- [ ] **Step 4: 运行 Watcher 与 codec 测试**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_clipboard_watcher.py tests/test_clipboard_codec.py -v
```

Expected: all pass.

- [ ] **Step 5: 提交**

```powershell
git add src/clipboard_watcher.py tests/test_clipboard_watcher.py
git commit -m "feat: capture multi-format clipboard changes"
```

---

### Task 7: 实现当前显示器几何计算与 TabBar 吸附

**Files:**
- Create: `src/screen_geometry.py`
- Create: `tests/test_screen_geometry.py`
- Modify: `src/tab_bar.py`

- [ ] **Step 1: 写纯几何失败测试**

```python
# tests/test_screen_geometry.py
from PySide6.QtCore import QPoint, QRect, QSize

from src.screen_geometry import (
    choose_screen,
    panel_position,
    top_right_position,
)


def test_choose_screen_uses_tab_center():
    left = QRect(0, 0, 1920, 1080)
    right = QRect(1920, 0, 1920, 1080)
    assert choose_screen(QPoint(2500, 20), [left, right]) == right


def test_top_right_position_stays_inside_screen():
    screen = QRect(1920, 0, 1920, 1080)
    assert top_right_position(screen, QSize(120, 6)) == QPoint(3719, 0)


def test_panel_opens_upward_when_bottom_space_is_insufficient():
    screen = QRect(0, 0, 800, 600)
    position = panel_position(
        tab_rect=QRect(680, 590, 120, 6),
        panel_size=QSize(420, 520),
        screen=screen,
    )
    assert position.y() == 70
    assert 0 <= position.x() <= 380
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_screen_geometry.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: 实现纯函数**

```python
# src/screen_geometry.py
from PySide6.QtCore import QPoint, QRect, QSize


def choose_screen(point: QPoint, geometries: list[QRect]) -> QRect:
    for geometry in geometries:
        if geometry.contains(point):
            return geometry
    return min(
        geometries,
        key=lambda geometry: (
            geometry.center().x() - point.x()
        ) ** 2 + (
            geometry.center().y() - point.y()
        ) ** 2,
    )


def top_right_position(screen: QRect, size: QSize) -> QPoint:
    return QPoint(screen.right() - size.width() + 1, screen.top())


def panel_position(tab_rect: QRect, panel_size: QSize, screen: QRect) -> QPoint:
    x = tab_rect.right() - panel_size.width() + 1
    x = max(screen.left(), min(x, screen.right() - panel_size.width() + 1))
    below_y = tab_rect.bottom() + 1
    above_y = tab_rect.top() - panel_size.height()
    y = below_y if below_y + panel_size.height() - 1 <= screen.bottom() else above_y
    y = max(screen.top(), min(y, screen.bottom() - panel_size.height() + 1))
    return QPoint(x, y)
```

- [ ] **Step 4: 运行几何测试**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_screen_geometry.py -v
```

Expected: all pass.

- [ ] **Step 5: 改造 TabBar**

在 `src/tab_bar.py`：

- 将固定尺寸改为 `120×6`。
- 增加 `_current_screen()`，使用 `QGuiApplication.screenAt(self.geometry().center())`，无结果时回退 `primaryScreen()`。
- `_snap_to_top_right()` 使用当前屏幕的 `availableGeometry()` 和 `top_right_position()`。
- 拖动期间将高度设为 10px，释放后动画结束恢复 6px。
- 监听 `screenAdded`、`screenRemoved` 和各 screen 的 `availableGeometryChanged`，重新夹持位置。

核心实现：

```python
    def _current_screen(self):
        return (
            QApplication.screenAt(self.geometry().center())
            or QApplication.primaryScreen()
        )

    def _snap_target(self) -> QPoint:
        screen = self._current_screen()
        return top_right_position(screen.availableGeometry(), self.size())
```

- [ ] **Step 6: 运行全部非 UI 测试并提交**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_screen_geometry.py tests/test_clipboard_store.py -v
```

Expected: all pass.

```powershell
git add src/screen_geometry.py src/tab_bar.py tests/test_screen_geometry.py
git commit -m "feat: snap tab to its current display"
```

---

### Task 8: 建立 Fluent 主题和历史卡片

**Files:**
- Create: `src/theme.py`
- Modify: `src/history_panel.py`
- Create: `tests/test_history_panel.py`

- [ ] **Step 1: 写面板结构和反馈失败测试**

```python
# tests/test_history_panel.py
from src.clip_item import ClipItem
from src.clipboard_store import ClipboardStore
from src.history_panel import HistoryPanel


class FakeWatcher:
    def __init__(self):
        self.hashes = []

    def notify_self_copy(self, value):
        self.hashes.append(value)


class FakeWriter:
    def __init__(self, succeeds=True):
        self.succeeds = succeeds
        self.items = []

    def write(self, item):
        self.items.append(item)
        if not self.succeeds:
            raise RuntimeError("busy")


def test_panel_enables_search_clear_button(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher(), FakeWriter())
    assert panel.search_box.isClearButtonEnabled()


def test_copy_success_sets_temporary_success_state(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", source_app="chrome.exe", timestamp=1)
    store.add(item)
    watcher = FakeWatcher()
    writer = FakeWriter()
    panel = HistoryPanel(store, watcher, writer)
    panel.copy_item(item.id)
    assert panel.feedback_for(item.id) == "copied"
    assert watcher.hashes == [item.content_hash]


def test_copy_failure_sets_failure_state_without_self_copy(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello")
    store.add(item)
    watcher = FakeWatcher()
    panel = HistoryPanel(store, watcher, FakeWriter(succeeds=False))
    panel.copy_item(item.id)
    assert panel.feedback_for(item.id) == "failed"
    assert watcher.hashes == []
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_history_panel.py -v
```

Expected: constructor and public API failures.

- [ ] **Step 3: 创建主题 token**

```python
# src/theme.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    panel: str
    surface: str
    surface_hover: str
    border: str
    text: str
    muted: str
    accent: str
    danger: str


DARK = Theme(
    panel="rgba(24, 26, 32, 238)",
    surface="rgba(255, 255, 255, 12)",
    surface_hover="rgba(255, 255, 255, 22)",
    border="rgba(255, 255, 255, 32)",
    text="#F4F6FB",
    muted="#9DA5B4",
    accent="#6EA8FE",
    danger="#FF6B81",
)

LIGHT = Theme(
    panel="rgba(245, 247, 251, 242)",
    surface="rgba(0, 0, 0, 8)",
    surface_hover="rgba(0, 0, 0, 16)",
    border="rgba(0, 0, 0, 26)",
    text="#20242C",
    muted="#657080",
    accent="#2563EB",
    danger="#D92D4A",
)
```

- [ ] **Step 4: 拆分并重写 HistoryPanel**

在 `src/history_panel.py` 建立以下公开结构：

```python
class ClipboardWriter:
    def __init__(self, clipboard=None):
        self._clipboard = clipboard or QApplication.clipboard()

    def write(self, item: ClipItem) -> None:
        self._clipboard.setMimeData(ClipboardCodec.encode(item))


class ItemCard(QWidget):
    copy_requested = Signal(str)
    delete_requested = Signal(str)

    def set_feedback(self, state: str | None) -> None:
        self._feedback = state
        self._feedback_label.setText(
            "✓ 已复制" if state == "copied"
            else "复制失败" if state == "failed"
            else ""
        )
        self.update()


class HistoryPanel(QWidget):
    def __init__(self, store, watcher, writer=None, parent=None):
        super().__init__(parent)
        self._store = store
        self._watcher = watcher
        self._writer = writer or ClipboardWriter()
        self._feedback: dict[str, str] = {}
        self._cards: dict[str, ItemCard] = {}
        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText("搜索剪贴板历史")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self.refresh)
        self._list = QListWidget(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self._search_box)
        layout.addWidget(self._list)
        self._store.items_changed.connect(self.refresh)
        self.refresh()

    @property
    def search_box(self):
        return self._search_box

    def feedback_for(self, item_id: str) -> str | None:
        return self._feedback.get(item_id)

    def copy_item(self, item_id: str) -> None:
        item = self._store.get_by_id(item_id)
        if item is None:
            return
        try:
            self._writer.write(item)
        except (RuntimeError, OSError, ValueError):
            self._set_feedback(item_id, "failed")
            return
        self._watcher.notify_self_copy(item.content_hash)
        self._set_feedback(item_id, "copied")

    def _set_feedback(self, item_id: str, state: str) -> None:
        self._feedback[item_id] = state
        card = self._cards.get(item_id)
        if card is not None:
            card.set_feedback(state)
        QTimer.singleShot(1200, lambda: self._clear_feedback(item_id, state))

    def _clear_feedback(self, item_id: str, expected_state: str) -> None:
        if self._feedback.get(item_id) != expected_state:
            return
        self._feedback.pop(item_id, None)
        card = self._cards.get(item_id)
        if card is not None:
            card.set_feedback(None)

    def refresh(self) -> None:
        keyword = self._search_box.text().strip()
        items = self._store.search(keyword) if keyword else self._store.get_all()
        self._list.clear()
        self._cards.clear()
        for item in items:
            row = QListWidgetItem(self._list)
            card = ItemCard(item)
            card.copy_requested.connect(self.copy_item)
            card.delete_requested.connect(self._delete_item)
            row.setSizeHint(card.sizeHint())
            self._list.setItemWidget(row, card)
            self._cards[item.id] = card

    def _delete_item(self, item_id: str) -> None:
        if QMessageBox.question(
            self,
            "确认删除",
            "确定要删除这条记录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes:
            self._store.delete(item_id)
```

具体布局要求：

- 面板宽 420px，高度 `min(520, screen.availableGeometry().height() - 24)`。
- `SearchBox.setClearButtonEnabled(True)`。
- 卡片左侧：图片缩略图或文本/HTML 图标。
- 卡片正文最多两行。
- 元数据：格式化应用名 + 相对时间。
- `source_window` 放在 card tooltip。
- 删除按钮默认隐藏，`enterEvent`/`leaveEvent` 控制显示。
- `_set_feedback()` 使用 `QTimer.singleShot(1200, lambda: self._clear_feedback(item_id, state))` 清除状态。
- show/hide 使用 `windowOpacity` 和 `pos` 动画，分别 160ms/120ms。

- [ ] **Step 5: 运行面板测试**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_history_panel.py -v
```

Expected: all pass.

- [ ] **Step 6: 提交**

```powershell
git add src/theme.py src/history_panel.py tests/test_history_panel.py
git commit -m "feat: redesign clipboard panel with fluent cards"
```

---

### Task 9: 整合数据库路径、降级模式和退出检查点

**Files:**
- Modify: `src/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: 写应用服务装配失败测试**

```python
# tests/test_main.py
from pathlib import Path

from src.main import default_database_path, open_repository


def test_default_database_path_uses_local_app_data(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Test\AppData\Local")
    assert default_database_path() == Path(
        r"C:\Users\Test\AppData\Local\ClipboardHub\clipboard.db"
    )


def test_open_repository_returns_none_when_database_cannot_open(monkeypatch, tmp_path):
    def fail(_path):
        raise OSError("read only")

    monkeypatch.setattr(
        "src.main.SQLiteRepository.open_with_recovery",
        fail,
    )
    assert open_repository(tmp_path / "clipboard.db") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_main.py -v
```

Expected: import failures.

- [ ] **Step 3: 实现路径和降级函数**

```python
# src/main.py
import logging
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from .clipboard_store import ClipboardStore
from .clipboard_watcher import ClipboardWatcher
from .history_panel import ClipboardWriter, HistoryPanel
from .sqlite_repository import SQLiteRepository
from .tab_bar import TabBar


LOGGER = logging.getLogger("clipboard_hub")


def default_database_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "ClipboardHub" / "clipboard.db"


def open_repository(path: Path) -> SQLiteRepository | None:
    try:
        return SQLiteRepository.open_with_recovery(path)
    except (OSError, RuntimeError):
        LOGGER.exception("SQLite unavailable; using memory-only mode")
        return None
```

- [ ] **Step 4: 更新 ClipboardHub 装配**

```python
class ClipboardHub:
    def __init__(self, database_path: Path | None = None):
        self._repository = open_repository(database_path or default_database_path())
        self._store = ClipboardStore(self._repository)
        self._watcher = ClipboardWatcher(self._store)
        self._writer = ClipboardWriter()
        self._tab = TabBar()
        self._panel = HistoryPanel(self._store, self._watcher, self._writer)
        self._tab.panel_show_requested.connect(self._on_tab_enter)
        self._tab.panel_hide_requested.connect(self._on_tab_leave)
        self._tab.position_changed.connect(self._on_tab_moved)
        self._setup_tray()
        self._tab.show()

    def shutdown(self) -> None:
        if self._repository is not None:
            self._repository.checkpoint()
            self._repository.close()
```

在入口连接：

```python
app.aboutToQuit.connect(hub.shutdown)
```

`_on_tab_enter()` 使用 `screen_geometry.panel_position()` 计算位置，不能继续直接使用 `tab_geo.bottom()`。

- [ ] **Step 5: 运行 main、几何和全量测试**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_main.py tests/test_screen_geometry.py tests -v
```

Expected: all pass.

- [ ] **Step 6: 提交**

```powershell
git add src/main.py tests/test_main.py
git commit -m "feat: integrate persistent clipboard services"
```

---

### Task 10: 系统主题跟随、时间格式和界面细节

**Files:**
- Modify: `src/theme.py`
- Modify: `src/history_panel.py`
- Modify: `src/tab_bar.py`
- Modify: `tests/test_history_panel.py`

- [ ] **Step 1: 写主题与相对时间测试**

```python
# tests/test_history_panel.py
from src.history_panel import format_app_name, format_relative_time


def test_format_app_name():
    assert format_app_name("chrome.exe") == "Chrome"
    assert format_app_name("Code.exe") == "Code"
    assert format_app_name("unknown") == "未知应用"


def test_format_relative_time():
    assert format_relative_time(100, now=100) == "刚刚"
    assert format_relative_time(40, now=100) == "1 分钟前"
    assert format_relative_time(100, now=7300) == "2 小时前"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_history_panel.py -v
```

Expected: missing helper failures.

- [ ] **Step 3: 实现格式化和主题选择**

```python
# src/theme.py
from PySide6.QtGui import QGuiApplication


def current_theme() -> Theme:
    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", lambda: None)()
    if scheme is not None and getattr(scheme, "name", "") == "Light":
        return LIGHT
    return DARK
```

```python
# src/history_panel.py
def format_app_name(value: str) -> str:
    if not value or value == "unknown":
        return "未知应用"
    stem = value.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    stem = stem[:-4] if stem.lower().endswith(".exe") else stem
    return stem[:1].upper() + stem[1:]


def format_relative_time(timestamp: float, *, now: float | None = None) -> str:
    current = time.time() if now is None else now
    seconds = max(0, int(current - timestamp))
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return datetime.fromtimestamp(timestamp).strftime("%m-%d %H:%M")
```

将 `current_theme()` 应用到 TabBar、Panel、SearchBox 和 ItemCard；监听系统 color scheme 变化时重新应用样式。

- [ ] **Step 4: 运行测试并提交**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests/test_history_panel.py tests/test_screen_geometry.py -v
```

Expected: all pass.

```powershell
git add src/theme.py src/history_panel.py src/tab_bar.py tests/test_history_panel.py
git commit -m "feat: follow Windows theme and polish metadata"
```

---

### Task 11: 文档、全量验证和人工验收

**Files:**
- Modify: `README.md`
- Modify: `docs/specs/2026-06-23-clipboard-hub-v2-design.md`
- Create: `docs/reviews/2026-06-23-v2-verification.md`

- [ ] **Step 1: 更新 README**

README 必须明确包含：

```markdown
## 数据与隐私

历史记录保存在 `%LOCALAPPDATA%\ClipboardHub\clipboard.db`。
数据库不加密，也不会上传或同步。剪贴板可能包含密码、令牌和私人内容，
请只在可信的 Windows 账户中使用。

默认最多保留 1000 条记录，并将有效内容限制为 200 MiB。
单张编码后超过 10 MiB 的图片不会保存。
```

同时更新功能列表：多格式恢复、来源应用、多显示器、复制反馈和系统主题。

- [ ] **Step 2: 运行静态语法检查**

Run:

```powershell
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m py_compile `
  src\clip_item.py src\sqlite_repository.py src\source_app.py `
  src\clipboard_codec.py src\clipboard_store.py src\clipboard_watcher.py `
  src\screen_geometry.py src\theme.py src\tab_bar.py `
  src\history_panel.py src\main.py
```

Expected: exit code 0 and no output.

- [ ] **Step 3: 运行完整自动测试**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m pytest tests -v
```

Expected: all tests pass.

- [ ] **Step 4: 启动应用进行人工验收**

Run:

```powershell
& 'C:\Users\Administrator\global-venv\Scripts\python.exe' -m src.main
```

逐项验证：

- 复制浏览器富文本后，只生成一条历史；Word 粘贴保留格式，记事本粘贴得到纯文本。
- 复制图片后显示缩略图；超过 10MiB 的 PNG 不保存。
- 卡片显示来源应用、相对时间，悬停可看到窗口标题。
- 点击卡片显示 `✓ 已复制` 约 1.2 秒，面板保持打开。
- 模拟写回失败时显示 `复制失败`。
- 搜索正文、HTML 文本、应用名和窗口标题均能命中。
- 搜索框清空按钮恢复完整列表。
- 在两个显示器间拖动 TabBar，松手后吸附到所在显示器右上角。
- 屏幕底部空间不足时，面板向上展开且不越界。
- 深浅系统主题切换后界面可读。
- 托盘退出并重启，历史、格式、来源和时间仍存在。
- 插入超过 1000 条测试记录后只保留最新 1000 条。
- 内容总量超过 200MiB 后从最旧记录开始淘汰。

- [ ] **Step 5: 写验证报告**

创建 `docs/reviews/2026-06-23-v2-verification.md`。报告必须记录实际命令、退出码、pytest 通过数量，以及每项人工验证的实际结果和证据。使用以下固定结构：

```markdown
# Clipboard Hub V2 Verification

## Automated
- Syntax command and exit code
- Pytest command, passed count, failed count

## Manual
- Multi-format clipboard result and tested applications
- Persistence after restart result
- Source application result
- Copy feedback result
- Multi-monitor snap result
- Theme readability result
- Retention limits result

## Remaining Issues
- 写“无”，或逐项记录复现步骤、期望结果和实际结果。
```

不得在未实际验证时填写 PASS。

- [ ] **Step 6: 更新设计状态并提交**

只有自动和人工验收均完成后，将 V2 设计文档状态更新为：

```markdown
> 状态：✅ 已实施并验证
```

```powershell
git add README.md docs/specs/2026-06-23-clipboard-hub-v2-design.md docs/reviews/2026-06-23-v2-verification.md
git commit -m "docs: verify clipboard hub v2"
```

---

## 计划自检

- 持久化、重启恢复和损坏恢复：Task 2、3、9。
- 1000 条与 200MiB 限制：Task 3。
- 多格式捕获和恢复：Task 5、6、8。
- 精确自复制去重：Task 6。
- 来源应用和窗口标题：Task 4、6、8。
- 当前显示器吸附与越界：Task 7、9。
- Fluent 主题、卡片、缩略图和反馈：Task 8、10。
- 数据库降级与退出检查点：Task 9。
- 隐私说明和完整验收：Task 11。
- 未包含 V2 明确排除的功能。
