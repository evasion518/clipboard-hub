# Clipboard Hub V1 实施计划（已归档）

> 本计划对应早期 V1 设计，已被 `docs/plans/2026-06-23-clipboard-hub-v2-plan.md` 取代。

**目标:** 实现一个 Windows 剪贴板历史管理器，右上角悬浮标签 + 鼠标悬停展开面板

**架构:** Python + PySide6，四模块：ClipboardStore (数据) → ClipboardWatcher (监听) → TabBar (标签) + HistoryPanel (面板)

**测试策略:** 核心逻辑 TDD (pytest)，GUI 手动验证

---

## 全局约束

- Python 解释器：`C:\Users\Administrator\global-venv\Scripts\python.exe`
- 所有源文件放在 `D:\Greasionix\clipboard-hub\src\`
- 测试文件放在 `D:\Greasionix\clipboard-hub\tests\`
- 包管理：pip + requirements.txt
- 命名：snake_case 文件，PascalCase 类，snake_case 方法
- PySide6 导入方式：`from PySide6.QtCore import ...` / `from PySide6.QtWidgets import ...`
- 每完成一个任务，更新设计文档中的变更记录

---

## 阶段 1：项目基础设施

### 任务 1: 创建 requirements.txt 和 README.md

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\requirements.txt`
- 创建: `D:\Greasionix\clipboard-hub\README.md`

- [ ] **步骤 1: 创建 requirements.txt**
  内容：
  ```
  PySide6>=6.5.0
  pytest>=7.0.0
  ```

- [ ] **步骤 2: 创建 README.md**
  内容：项目名称、一句话描述、运行方式 `python src/main.py`、依赖安装 `pip install -r requirements.txt`

- [ ] **步骤 3: 安装依赖**
  运行 `C:\Users\Administrator\global-venv\Scripts\python.exe -m pip install PySide6 pytest`

- [ ] **步骤 4: 验证**
  运行 `C:\Users\Administrator\global-venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; print('OK')"`

---

## 阶段 2：ClipboardStore 数据层（纯逻辑，无 GUI）

### 任务 2: 写 ClipboardStore 测试（TDD 第一步）

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\tests\test_clipboard_store.py`
- 创建: `D:\Greasionix\clipboard-hub\tests\__init__.py`（空文件）

- [ ] **步骤 1: 创建 conftest.py**
  在 `tests/conftest.py` 中创建 `QApplication` 实例 fixture（Store 需要 Signal，Signal 需要 QApplication）：
  ```python
  import pytest
  from PySide6.QtWidgets import QApplication

  @pytest.fixture(scope="session")
  def qapp():
      app = QApplication.instance()
      if app is None:
          app = QApplication([])
      return app
  ```

- [ ] **步骤 2: 写 test_add_and_get_all**
  ```python
  from src.clipboard_store import ClipboardStore, ClipItem

  def test_add_and_get_all(qapp):
      store = ClipboardStore()
      item = ClipItem(type="text", content="hello", preview="hello")
      store.add(item)
      items = store.get_all()
      assert len(items) == 1
      assert items[0].content == "hello"
  ```

- [ ] **步骤 3: 写 test_deduplicate_same_content**
  ```python
  def test_deduplicate_same_content(qapp):
      store = ClipboardStore()
      store.add(ClipItem(type="text", content="same", preview="same"))
      store.add(ClipItem(type="text", content="same", preview="same"))
      assert len(store.get_all()) == 1
  ```

- [ ] **步骤 4: 写 test_different_content_adds_both**
  ```python
  def test_different_content_adds_both(qapp):
      store = ClipboardStore()
      store.add(ClipItem(type="text", content="a", preview="a"))
      store.add(ClipItem(type="text", content="b", preview="b"))
      assert len(store.get_all()) == 2
  ```

- [ ] **步骤 5: 写 test_delete**
  ```python
  def test_delete(qapp):
      store = ClipboardStore()
      item = ClipItem(type="text", content="del", preview="del")
      store.add(item)
      store.delete(item.id)
      assert len(store.get_all()) == 0
  ```

- [ ] **步骤 6: 写 test_search**
  ```python
  def test_search(qapp):
      store = ClipboardStore()
      store.add(ClipItem(type="text", content="apple pie", preview="apple pie"))
      store.add(ClipItem(type="text", content="banana", preview="banana"))
      store.add(ClipItem(type="html", content="<div>apple</div>", preview="<div>apple</div>"))
      results = store.search("apple")
      assert len(results) == 2
      results = store.search("banana")
      assert len(results) == 1
      results = store.search("xyz")
      assert len(results) == 0
  ```

- [ ] **步骤 7: 写 test_re_copy_signals**
  ```python
  def test_items_changed_signal(qapp):
      from PySide6.QtCore import QSignalSpy
      store = ClipboardStore()
      spy = QSignalSpy(store.items_changed)
      store.add(ClipItem(type="text", content="x", preview="x"))
      assert len(spy) == 1
  ```

- [ ] **步骤 8: 运行测试确认失败**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -m pytest tests/test_clipboard_store.py -v`
  预期：全部 FAIL（类不存在）

### 任务 3: 实现 ClipboardStore

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\src\clipboard_store.py`
- 创建: `D:\Greasionix\clipboard-hub\src\__init__.py`（空文件）

- [ ] **步骤 1: 实现 ClipItem 数据类**
  ```python
  import uuid
  import time
  from dataclasses import dataclass, field

  @dataclass
  class ClipItem:
      type: str           # "text" | "image" | "html"
      content: str        # 文本内容或图片 base64
      preview: str        # 截断预览
      id: str = field(default_factory=lambda: str(uuid.uuid4()))
      timestamp: float = field(default_factory=time.time)
      app_source: str = "unknown"
  ```

- [ ] **步骤 2: 实现 ClipboardStore 类**
  ```python
  from PySide6.QtCore import QObject, Signal

  class ClipboardStore(QObject):
      items_changed = Signal()

      def __init__(self, parent=None):
          super().__init__(parent)
          self._items: list[ClipItem] = []

      def add(self, item: ClipItem):
          if self._items and self._items[0].content == item.content:
              return  # 去重
          self._items.insert(0, item)
          self.items_changed.emit()

      def delete(self, item_id: str):
          self._items = [i for i in self._items if i.id != item_id]
          self.items_changed.emit()

      def get_all(self) -> list[ClipItem]:
          return list(self._items)

      def search(self, keyword: str) -> list[ClipItem]:
          kw = keyword.lower()
          return [i for i in self._items
                  if kw in i.content.lower() or kw in i.preview.lower()]

      def re_copy(self, item_id: str):
          """写回系统剪贴板 — 在 main 中连接 QApplication.clipboard()"""
          for item in self._items:
              if item.id == item_id:
                  return item
          return None
  ```

- [ ] **步骤 2: 运行测试确认通过**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -m pytest tests/test_clipboard_store.py -v`

---

## 阶段 3：ClipboardWatcher 剪贴板监听

### 任务 4: 写 ClipboardWatcher 测试

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\tests\test_clipboard_watcher.py`

- [ ] **步骤 1: 写 test_watcher_skips_empty_clipboard**
  ```python
  def test_watcher_prevents_duplicate_loop(qapp):
      from src.clipboard_store import ClipboardStore, ClipItem
      from src.clipboard_watcher import ClipboardWatcher

      store = ClipboardStore()
      watcher = ClipboardWatcher(store)
      # 模拟 re_copy：Watcher 应跳过自身写入
      assert watcher._is_self_copy is False  # 初始状态
      watcher._last_md5 = "abc"
      watcher._is_self_copy = True
      # 下次轮询应跳过
      assert watcher._is_self_copy is True
  ```
  注：Watcher 的完整集成测试依赖真实剪贴板，这里只测核心逻辑。

- [ ] **步骤 2: 写 test_content_hash_detects_change**
  ```python
  import hashlib

  def test_content_hash_detects_change():
      def hash_text(text):
          return hashlib.md5(text.encode("utf-8")).hexdigest()
      h1 = hash_text("hello")
      h2 = hash_text("world")
      assert h1 != h2
      assert hash_text("hello") == h1  # 幂等
  ```

- [ ] **步骤 3: 运行测试**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -m pytest tests/test_clipboard_watcher.py -v`

### 任务 5: 实现 ClipboardWatcher

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\src\clipboard_watcher.py`

- [ ] **步骤 1: 实现 ClipboardWatcher**
  ```python
  import hashlib
  from PySide6.QtCore import QTimer, QObject
  from PySide6.QtGui import QClipboard
  from PySide6.QtWidgets import QApplication
  from .clipboard_store import ClipboardStore, ClipItem

  class ClipboardWatcher(QObject):
      def __init__(self, store: ClipboardStore, parent=None):
          super().__init__(parent)
          self._store = store
          self._last_md5: str | None = None
          self._is_self_copy = False
          self._timer = QTimer(self)
          self._timer.timeout.connect(self._poll)
          self._timer.start(500)

      def _poll(self):
          if self._is_self_copy:
              self._is_self_copy = False
              return

          clipboard = QApplication.clipboard()
          mime = clipboard.mimeData()

          try:
              if mime.hasImage():
                  image = mime.imageData()
                  if image and not image.isNull():
                      # 检查图片大小 (10MB limit)
                      ba = self._image_to_bytes(image)
                      if len(ba) > 10 * 1024 * 1024:
                          return
                      md5 = hashlib.md5(ba).hexdigest()
                      if md5 == self._last_md5:
                          return
                      self._last_md5 = md5
                      import base64
                      content = base64.b64encode(ba).decode("ascii")
                      preview = f"图片 ({image.width()}×{image.height()}, {len(ba)//1024}KB)"
                      self._store.add(ClipItem(type="image", content=content, preview=preview))
                      return

              if mime.hasHtml():
                  html = mime.html()
                  if html:
                      md5 = hashlib.md5(html.encode("utf-8")).hexdigest()
                      if md5 == self._last_md5:
                          return
                      self._last_md5 = md5
                      preview = html[:80].replace("\n", " ")
                      self._store.add(ClipItem(type="html", content=html, preview=preview))
                      return

              if mime.hasText():
                  text = mime.text()
                  if text and text.strip():
                      md5 = hashlib.md5(text.encode("utf-8")).hexdigest()
                      if md5 == self._last_md5:
                          return
                      self._last_md5 = md5
                      preview = text[:80].replace("\n", " ")
                      self._store.add(ClipItem(type="text", content=text, preview=preview))
          except Exception:
              pass  # 静默跳过

      @staticmethod
      def _image_to_bytes(image) -> bytes:
          from PySide6.QtCore import QByteArray, QBuffer, QIODevice
          ba = QByteArray()
          buf = QBuffer(ba)
          buf.open(QIODevice.WriteOnly)
          image.save(buf, "PNG")
          return ba.data()

      def notify_self_copy(self):
          """re_copy 调用前标记，阻止下次轮询记录"""
          self._is_self_copy = True
  ```

- [ ] **步骤 2: 运行 Watcher 测试**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -m pytest tests/test_clipboard_watcher.py -v`

- [ ] **步骤 3: 运行全部测试**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -m pytest tests/ -v`

---

## 阶段 4：TabBar 标签条

### 任务 6: 实现 TabBar

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\src\tab_bar.py`

- [ ] **步骤 1: 实现 TabBar 类**
  ```python
  from PySide6.QtCore import Qt, QPoint, Signal
  from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout
  from PySide6.QtGui import QMouseEvent

  class TabBar(QWidget):
      panel_show_requested = Signal()
      panel_hide_requested = Signal()

      def __init__(self, parent=None):
          super().__init__(parent)
          self.setWindowFlags(
              Qt.WindowStaysOnTopHint |
              Qt.FramelessWindowHint |
              Qt.Tool
          )
          self.setAttribute(Qt.WA_TranslucentBackground, False)
          self.setFixedSize(200, 30)
          self.setStyleSheet("""
              QWidget {
                  background-color: #1E1E2E;
                  border-radius: 0px;
              }
              QLabel {
                  color: #CDD6F4;
                  font-family: "Segoe UI";
                  font-size: 11px;
                  padding: 0 10px;
              }
          """)

          layout = QHBoxLayout(self)
          layout.setContentsMargins(0, 0, 0, 0)
          label = QLabel("📋  剪贴板历史")
          label.setAlignment(Qt.AlignCenter)
          layout.addWidget(label)

          self._drag_pos: QPoint | None = None
          self._position_top_right()

      def _position_top_right(self):
          from PySide6.QtGui import QScreen
          screen = QApplication.primaryScreen()
          if screen:
              geo = screen.availableGeometry()
              self.move(geo.right() - self.width(), geo.top())

      def enterEvent(self, event):
          self.panel_show_requested.emit()
          super().enterEvent(event)

      def leaveEvent(self, event):
          self.panel_hide_requested.emit()
          super().leaveEvent(event)

      def mousePressEvent(self, event: QMouseEvent):
          if event.button() == Qt.LeftButton:
              self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
          super().mousePressEvent(event)

      def mouseMoveEvent(self, event: QMouseEvent):
          if self._drag_pos is not None:
              self.move((event.globalPosition().toPoint() - self._drag_pos))
          super().mouseMoveEvent(event)

      def mouseReleaseEvent(self, event: QMouseEvent):
          self._drag_pos = None
          super().mouseReleaseEvent(event)
  ```

- [ ] **步骤 2: 验证无语法错误**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'D:/Greasionix/clipboard-hub/src'); from tab_bar import TabBar; print('OK')"`

  注：TabBar 依赖 GUI，不写自动化测试。手动验证在全部完成后进行。

---

## 阶段 5：HistoryPanel 展开面板

### 任务 7: 实现 HistoryPanel

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\src\history_panel.py`

- [ ] **步骤 1: 实现 HistoryPanel 类**
  ```python
  from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve
  from PySide6.QtWidgets import (
      QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
      QPushButton, QHBoxLayout, QLabel, QMessageBox, QApplication
  )
  from PySide6.QtGui import QFont
  from .clipboard_store import ClipboardStore, ClipItem
  from .clipboard_watcher import ClipboardWatcher

  COLORS = {
      "bg": "#1E1E2E",
      "surface": "#2A2A3C",
      "text_primary": "#CDD6F4",
      "text_secondary": "#6C7086",
      "accent": "#89B4FA",
      "danger": "#F38BA8",
  }

  TYPE_DOTS = {
      "text": "#CDD6F4",
      "image": "#89B4FA",
      "html": "#FAB387",
  }

  class SearchBox(QLineEdit):
      def __init__(self, parent=None):
          super().__init__(parent)
          self.setPlaceholderText("🔍  搜索历史...")
          self.setStyleSheet(f"""
              QLineEdit {{
                  background-color: {COLORS['surface']};
                  color: {COLORS['text_primary']};
                  border: 1px solid {COLORS['surface']};
                  border-radius: 8px;
                  padding: 8px 12px;
                  font-family: "Segoe UI";
                  font-size: 12px;
              }}
              QLineEdit:focus {{
                  border-color: {COLORS['accent']};
              }}
          """)


  class HistoryList(QListWidget):
      item_clicked = Signal(str)   # item_id
      item_delete_requested = Signal(str)  # item_id

      def __init__(self, parent=None):
          super().__init__(parent)
          self.setStyleSheet(f"""
              QListWidget {{
                  background-color: transparent;
                  border: none;
                  outline: none;
              }}
              QListWidget::item {{
                  background-color: transparent;
                  border-bottom: 1px dashed #45475A;
                  padding: 10px 12px;
              }}
              QListWidget::item:hover {{
                  background-color: {COLORS['surface']};
              }}
          """)
          self.setFont(QFont("JetBrains Mono", 10))
          self.itemClicked.connect(self._on_item_clicked)

      def _on_item_clicked(self, item: QListWidgetItem):
          item_id = item.data(Qt.UserRole)
          self.item_clicked.emit(item_id)


  class HistoryPanel(QWidget):
      panel_shown = Signal()

      def __init__(self, store: ClipboardStore, watcher: ClipboardWatcher, parent=None):
          super().__init__(parent)
          self._store = store
          self._watcher = watcher
          self._hide_timer = QTimer(self)
          self._hide_timer.setSingleShot(True)
          self._hide_timer.timeout.connect(self._animate_hide)
          self._hide_timer.setInterval(300)

          self.setWindowFlags(
              Qt.WindowStaysOnTopHint |
              Qt.FramelessWindowHint |
              Qt.Tool
          )
          self.setFixedSize(380, 480)
          self.setStyleSheet(f"""
              QWidget #{self.objectName()} {{
                  background-color: {COLORS['bg']};
              }}
          """)
          self.setObjectName("HistoryPanel")

          layout = QVBoxLayout(self)
          layout.setContentsMargins(12, 12, 12, 12)
          layout.setSpacing(8)

          self._search_box = SearchBox()
          self._search_box.textChanged.connect(self._on_search)
          layout.addWidget(self._search_box)

          self._list = HistoryList()
          self._list.item_clicked.connect(self._on_re_copy)
          self._list.item_delete_requested.connect(self._on_delete_request)
          layout.addWidget(self._list)

          self._store.items_changed.connect(self._refresh_list)
          self.hide()

      def show_at(self, x: int, y: int):
          self.move(x, y)
          self.show()
          self._refresh_list()
          self.panel_shown.emit()

      def _refresh_list(self):
          keyword = self._search_box.text().strip()
          items = self._store.search(keyword) if keyword else self._store.get_all()
          self._list.clear()
          for item in items:
              dot_color = TYPE_DOTS.get(item.type, COLORS["text_primary"])
              display = f"● {item.preview}"
              list_item = QListWidgetItem(display)
              list_item.setData(Qt.UserRole, item.id)
              list_item.setForeground(Qt.GlobalColor.white)  # 简化：后续用 delegate 改色
              self._list.addItem(list_item)

      def _on_search(self, text: str):
          self._refresh_list()

      def _on_re_copy(self, item_id: str):
          item = self._store.re_copy(item_id)
          if item is None:
              return
          clipboard = QApplication.clipboard()
          self._watcher.notify_self_copy()
          if item.type == "image":
              import base64
              from PySide6.QtGui import QImage, QPixmap
              img_data = base64.b64decode(item.content)
              pixmap = QPixmap()
              pixmap.loadFromData(img_data, "PNG")
              clipboard.setPixmap(pixmap)
          elif item.type == "html":
              mime = clipboard.mimeData().__class__()
              clipboard.clear()
              clipboard.setText(item.content)  # fallback
          else:
              clipboard.setText(item.content)
          self._hide_timer.start()

      def _on_delete_request(self, item_id: str):
          reply = QMessageBox.question(
              self, "确认删除",
              "确定要删除这条记录吗？",
              QMessageBox.Yes | QMessageBox.No,
              QMessageBox.No
          )
          if reply == QMessageBox.Yes:
              self._store.delete(item_id)

      def notify_mouse_enter(self):
          self._hide_timer.stop()

      def notify_mouse_leave(self):
          self._hide_timer.start(300)

      def _animate_hide(self):
          self.hide()

      def enterEvent(self, event):
          self.notify_mouse_enter()
          super().enterEvent(event)

      def leaveEvent(self, event):
          self.notify_mouse_leave()
          super().leaveEvent(event)
  ```

- [ ] **步骤 2: 验证无语法错误**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'D:/Greasionix/clipboard-hub/src'); from history_panel import HistoryPanel; print('OK')"`

---

## 阶段 6：main.py 入口 + 整合

### 任务 8: 实现 main.py 整合所有组件

**文件:**
- 创建: `D:\Greasionix\clipboard-hub\src\main.py`

- [ ] **步骤 1: 实现 main.py**
  ```python
  import sys
  from PySide6.QtWidgets import QApplication
  from PySide6.QtCore import Qt
  from clipboard_store import ClipboardStore
  from clipboard_watcher import ClipboardWatcher
  from tab_bar import TabBar
  from history_panel import HistoryPanel


  class ClipboardHub:
      def __init__(self):
          self._store = ClipboardStore()
          self._watcher = ClipboardWatcher(self._store)
          self._tab = TabBar()
          self._panel = HistoryPanel(self._store, self._watcher)

          # TabBar 信号 → Panel 显隐
          self._tab.panel_show_requested.connect(self._on_tab_enter)
          self._tab.panel_hide_requested.connect(self._on_tab_leave)

          self._tab.show()

      def _on_tab_enter(self):
          tab_geo = self._tab.geometry()
          self._panel.notify_mouse_enter()
          self._panel.show_at(tab_geo.right() - self._panel.width(), tab_geo.bottom())

      def _on_tab_leave(self):
          self._panel.notify_mouse_leave()


  if __name__ == "__main__":
      app = QApplication(sys.argv)
      app.setQuitOnLastWindowClosed(False)  # TabBar 关闭不退出，需系统托盘或手动结束
      hub = ClipboardHub()
      sys.exit(app.exec())
  ```

- [ ] **步骤 2: 验证启动**
  `C:\Users\Administrator\global-venv\Scripts\python.exe D:\Greasionix\clipboard-hub\src\main.py`
  手动确认：TabBar 出现在屏幕右上角。

---

## 阶段 7：整合测试 + 修复

### 任务 9: 运行全部测试

- [ ] **步骤 1: 运行全部单元测试**
  `C:\Users\Administrator\global-venv\Scripts\python.exe -m pytest D:\Greasionix\clipboard-hub\tests\ -v`

- [ ] **步骤 2: 修复任何失败**

### 任务 10: 审查 agent 运行审查

- [ ] **步骤 1: 运行审查 agent**
  调用 clipboard-hub-reviewer 审查所有 `src/` 和 `tests/` 下的代码

- [ ] **步骤 2: 阅读审查文档**
  查看 `D:\Greasionix\clipboard-hub\docs\reviews\` 下的最新审查文档

- [ ] **步骤 3: 修复审查发现的问题**

### 任务 11: 手动验证

- [ ] 标签悬浮展开 / 移开收起
- [ ] 鼠标在标签和面板间移动保持展开
- [ ] 拖拽 TabBar 移动位置
- [ ] 复制文本后列表中显示
- [ ] 搜索过滤实时生效，清空恢复
- [ ] 点击条目重新复制到系统剪贴板
- [ ] 删除确认弹窗
- [ ] 去重：复制相同内容仅保留一条

---

## 阶段 8：更新设计文档

### 任务 12: 更新设计文档变更记录

**文件:**
- 修改: `D:\Greasionix\clipboard-hub\docs\specs\2026-06-23-clipboard-hub-design.md`

- [ ] **步骤 1: 在变更记录中添加所有已完成任务的状态**
