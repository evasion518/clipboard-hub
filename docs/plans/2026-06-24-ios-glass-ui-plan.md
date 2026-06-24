# Clipboard Hub iOS 透明玻璃 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Clipboard Hub 的主面板、搜索框和历史卡片改造成偏白微蓝的 iOS 透明玻璃视觉，同时保持现有交互、结构和业务逻辑不变。

**Architecture:** 这次改造只动视觉层：先在 `src/theme.py` 中新增玻璃风配色 token，再在 `src/history_panel.py` 中把面板绘制、搜索框样式、卡片样式和徽标样式切换到统一的玻璃材质语言。测试继续以 `tests/test_history_panel.py` 为主，锁定“不改行为、只改观感”的边界。

**Tech Stack:** Python 3.11、PySide6、pytest

---

## 文件结构

- Modify: `D:\Greasionix\clipboard-hub\src\theme.py`
  - 负责定义 light/dark/system 下的玻璃风颜色 token
- Modify: `D:\Greasionix\clipboard-hub\src\history_panel.py`
  - 负责主面板绘制、搜索框样式、卡片样式、时间/反馈徽标玻璃化
- Modify: `D:\Greasionix\clipboard-hub\tests\test_history_panel.py`
  - 负责锁定玻璃风改造后的样式与既有交互不回退
- Modify: `D:\Greasionix\clipboard-hub\docs\preferences\2026-06-24-ui-style-profile.md`
  - 负责沉淀本次视觉方向与默认实现策略

---

### Task 1: 先把玻璃风视觉目标写成失败测试

**Files:**
- Modify: `D:\Greasionix\clipboard-hub\tests\test_history_panel.py`

- [ ] **Step 1: 写主面板和搜索框玻璃风失败测试**

```python
def test_panel_uses_glass_theme_tokens(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    assert "rgba" in panel._theme.panel_background
    assert panel._theme.panel_background != "#f4eee7"
    assert panel._theme.search_background.startswith("rgba")


def test_search_box_uses_glass_like_border_and_background(qapp):
    panel = HistoryPanel(ClipboardStore(), FakeWatcher())

    style = panel.search_box.styleSheet()
    assert "background-color" in style
    assert "border" in style
    assert "border-radius: 16px" in style
```

- [ ] **Step 2: 写历史卡片玻璃风失败测试**

```python
def test_history_card_uses_glass_spacing_and_soft_shadow(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", source_app="Code.exe")
    store.add(item)
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    card = panel._list._cards[item.id]
    effect = card.graphicsEffect()

    assert effect is not None
    assert effect.blurRadius() >= 30
    assert panel._list.spacing() >= 18


def test_time_badge_uses_glass_style_tokens(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", source_app="Code.exe")
    store.add(item)
    panel = HistoryPanel(store, FakeWatcher())
    panel.show_at(0, 0)

    card = panel._list._cards[item.id]
    time_label = card.findChild(QLabel, "timeLabel")

    assert time_label is not None
    assert "background-color" in time_label.styleSheet()
    assert "border-radius" in time_label.styleSheet()
```

- [ ] **Step 3: 运行定向测试确认先失败**

Run: `pytest tests/test_history_panel.py -q`

Expected: 至少出现与旧暖灰 token 或旧阴影参数相关的断言失败。

- [ ] **Step 4: 提交**

```powershell
git add tests/test_history_panel.py
git commit -m "test: lock ios glass panel styling"
```

---

### Task 2: 在 theme.py 中切换到 iOS 透明玻璃 token

**Files:**
- Modify: `D:\Greasionix\clipboard-hub\src\theme.py`
- Test: `D:\Greasionix\clipboard-hub\tests\test_history_panel.py`

- [ ] **Step 1: 写最小 token 改动**

```python
LIGHT_THEME = ThemePalette(
    panel_background="rgba(244, 248, 255, 214)",
    panel_border_start="rgba(255, 255, 255, 235)",
    panel_border_end="rgba(170, 198, 255, 150)",
    search_background="rgba(255, 255, 255, 150)",
    search_text="#16324f",
    search_border="rgba(255, 255, 255, 185)",
    search_focus="rgba(120, 170, 255, 210)",
    card_background="rgba(255, 255, 255, 132)",
    card_border="rgba(255, 255, 255, 165)",
    card_text="#16283d",
    card_meta="#48627c",
    success="#3f7ddf",
    success_background="rgba(223, 236, 255, 170)",
    failure="#c96c86",
    failure_background="rgba(255, 232, 238, 170)",
    danger="#b85f78",
    empty_text="#6f87a0",
)
```

- [ ] **Step 2: 同步 dark token，保持 system 模式可用**

```python
DARK_THEME = ThemePalette(
    panel_background="rgba(26, 34, 46, 224)",
    panel_border_start="rgba(255, 255, 255, 70)",
    panel_border_end="rgba(120, 165, 255, 95)",
    search_background="rgba(255, 255, 255, 18)",
    search_text="#eef4ff",
    search_border="rgba(255, 255, 255, 42)",
    search_focus="rgba(144, 188, 255, 180)",
    card_background="rgba(255, 255, 255, 12)",
    card_border="rgba(255, 255, 255, 34)",
    card_text="#f4f8ff",
    card_meta="#bfd0e7",
    success="#9ac0ff",
    success_background="rgba(64, 110, 180, 65)",
    failure="#f0b1c1",
    failure_background="rgba(122, 64, 83, 68)",
    danger="#f0a7bb",
    empty_text="#9fb3cc",
)
```

- [ ] **Step 3: 运行定向测试确认 token 层通过**

Run: `pytest tests/test_history_panel.py -q`

Expected: 与主题 token 相关的测试通过，若仍有失败则集中在 `history_panel.py` 的旧样式。

- [ ] **Step 4: 提交**

```powershell
git add src/theme.py tests/test_history_panel.py
git commit -m "feat: add ios glass theme tokens"
```

---

### Task 3: 让主面板和搜索框变成玻璃材质

**Files:**
- Modify: `D:\Greasionix\clipboard-hub\src\history_panel.py`
- Test: `D:\Greasionix\clipboard-hub\tests\test_history_panel.py`

- [ ] **Step 1: 写主面板绘制最小实现**

```python
def paintEvent(self, event):
    painter = QPainter(self)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = self.rect().adjusted(1, 1, -2, -2)

    fill = QColor(self._theme.panel_background)
    painter.setBrush(QBrush(fill))

    gradient = QLinearGradient(0, 0, self.width(), self.height())
    gradient.setColorAt(0.0, QColor(self._theme.panel_border_start))
    gradient.setColorAt(1.0, QColor(self._theme.panel_border_end))
    painter.setPen(QPen(gradient, 1.2))
    painter.drawRoundedRect(rect, 24, 24)
```

- [ ] **Step 2: 写搜索框玻璃样式最小实现**

```python
self.setStyleSheet(
    f"""
    QLineEdit {{
        background-color: {theme.search_background};
        color: {theme.search_text};
        border: 1px solid {theme.search_border};
        border-radius: 16px;
        padding: 14px 16px;
        font-family: "Segoe UI";
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border: 1px solid {theme.search_focus};
        background-color: {theme.card_background};
    }}
    QLineEdit::placeholder {{
        color: {theme.empty_text};
    }}
    """
)
```

- [ ] **Step 3: 运行定向测试确认主面板/搜索框通过**

Run: `pytest tests/test_history_panel.py -q`

Expected: 面板与搜索框相关测试通过；若仍失败，剩余问题应主要在卡片层。

- [ ] **Step 4: 提交**

```powershell
git add src/history_panel.py tests/test_history_panel.py
git commit -m "feat: render glass panel and search box"
```

---

### Task 4: 让历史卡片、时间徽标和反馈徽标玻璃化

**Files:**
- Modify: `D:\Greasionix\clipboard-hub\src\history_panel.py`
- Test: `D:\Greasionix\clipboard-hub\tests\test_history_panel.py`

- [ ] **Step 1: 先写卡片阴影与边界最小实现**

```python
shadow = QGraphicsDropShadowEffect(self)
shadow.setBlurRadius(36)
shadow.setOffset(0, 12)
shadow.setColor(QColor(72, 112, 168, 28))
self.setGraphicsEffect(shadow)
```

```python
self.setStyleSheet(
    f"""
    HistoryCard {{
        background-color: {background};
        border: 1px solid {border};
        border-radius: 22px;
    }}
    """
)
```

- [ ] **Step 2: 再写时间徽标和反馈徽标玻璃样式**

```python
self._time_label.setStyleSheet(
    f"""
    color: {theme.card_meta};
    background-color: {theme.search_background};
    border: 1px solid {theme.card_border};
    border-radius: 999px;
    padding: 4px 10px;
    font-family: 'Segoe UI';
    font-size: 10px;
    font-weight: 600;
    """
)
```

```python
self._feedback_label.setStyleSheet(
    f"""
    color: {self._theme.success};
    background-color: {self._theme.success_background};
    border: 1px solid {self._theme.success};
    border-radius: 999px;
    padding: 3px 10px;
    font-family: 'Segoe UI';
    font-size: 11px;
    font-weight: 600;
    """
)
```

- [ ] **Step 3: 运行定向测试确认卡片层通过**

Run: `pytest tests/test_history_panel.py -q`

Expected: `tests/test_history_panel.py` 全部通过。

- [ ] **Step 4: 提交**

```powershell
git add src/history_panel.py tests/test_history_panel.py
git commit -m "feat: apply ios glass styling to history cards"
```

---

### Task 5: 全量验证并同步文档

**Files:**
- Modify: `D:\Greasionix\clipboard-hub\docs\preferences\2026-06-24-ui-style-profile.md`
- Modify: `D:\Greasionix\clipboard-hub\docs\specs\2026-06-23-clipboard-hub-v2-design.md`

- [ ] **Step 1: 运行语法校验**

Run: `$files = Get-ChildItem -Path 'D:\Greasionix\clipboard-hub\src','D:\Greasionix\clipboard-hub\tests' -Filter '*.py' -Recurse | ForEach-Object { $_.FullName }; python -m py_compile $files`

Expected: exit code 0，且无输出。

- [ ] **Step 2: 运行完整测试**

Run: `pytest tests -q`

Expected: 全部通过。

- [ ] **Step 3: 同步文档中的实现状态**

```markdown
- 当前主面板、搜索框与历史卡片已切换为偏白微蓝的 iOS 透明玻璃材质
- 玻璃化改造不影响现有搜索、复制、删除、隐藏与系统主题跟随逻辑
```

- [ ] **Step 4: 提交**

```powershell
git add docs/preferences/2026-06-24-ui-style-profile.md docs/specs/2026-06-23-clipboard-hub-v2-design.md
git commit -m "docs: record ios glass ui implementation"
```

---

## 计划自检

- spec 覆盖：
  - 主面板玻璃化：Task 2、Task 3
  - 搜索框玻璃化：Task 2、Task 3
  - 历史卡片玻璃化：Task 2、Task 4
  - 内容优先/不加回标签：Task 4 约束
  - 不改逻辑与结构：各任务文件范围已限制在 theme/history_panel/tests/docs
- placeholder 扫描：
  - 无 “TBD / TODO / later” 占位
  - 每个任务都包含文件、命令和期望结果
- 类型与命名一致性：
  - 统一沿用 `ThemePalette`、`HistoryPanel`、`HistoryCard`、`SearchBox`
  - 测试路径统一使用 `tests/test_history_panel.py`
