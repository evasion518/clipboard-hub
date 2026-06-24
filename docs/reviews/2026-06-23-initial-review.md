# Code Review — 2026-06-23 初始审查

## Summary
- Files reviewed: 9（5 源文件 + 3 测试文件 + 1 conftest）
- Issues found: 25（Critical: 5, Warning: 9, Suggestion: 11）

---

## Critical Issues

### 1. [src/history_panel.py:153] HTML 重拷使用 setText 而非 setHtml——丢失富文本格式
- **Problem**: `_on_re_copy` 中，当 `item.type == "html"` 时调用 `clipboard.setText(item.content)`，将 HTML 源码以纯文本形式写回剪贴板。粘贴时用户得到的是 `<div>...</div>` 原始标签字符串，而非格式化内容。
- **Impact**: HTML 剪贴板条目的「重新复制」功能完全失效——用户复制一段富文本后无法正确恢复。
- **Fix suggestion**: 改用 `clipboard.setHtml(item.content)`；若需同时兼容纯文本粘贴场景，通过 `QMimeData` 同时设置 `text/html` 和 `text/plain`。

```python
# 修复示例
from PySide6.QtCore import QMimeData
mime = QMimeData()
mime.setHtml(item.content)
mime.setText(strip_html(item.content))  # 需要实现简单的 HTML 剥离
clipboard.setMimeData(mime)
```

### 2. [src/history_panel.py:79–80, 114] 逐条删除按钮（✕）未实现——`item_delete_requested` 信号永不被发射
- **Problem**: 设计文档明确每条记录右侧有 ✕ 删除按钮；代码中 `HistoryList` 定义了 `item_delete_requested` 信号并连接到 `_on_delete_request`，但 `contextMenuEvent` 被 stub 为空 (`pass`)，且未在条目中渲染任何删除按钮。逐条删除功能完全无法通过 UI 触发。
- **Impact**: 用户无法删除单条历史记录，与设计严重不符。
- **Fix suggestion**: 使用 `QListWidget.setItemWidget()` 为每个条目嵌入删除按钮（QPushButton），按钮点击时发射 `item_delete_requested` 信号；样式按设计文档（平时 `#6C7086`，悬浮 `#F38BA8`）。

### 3. [src/main.py:35] `setQuitOnLastWindowClosed(False)` 且无退出机制——应用无法正常退出
- **Problem**: `app.setQuitOnLastWindowClosed(False)` 阻止了窗口关闭时的自动退出。TabBar 和 HistoryPanel 均为 `Qt.Tool` 窗口（无任务栏图标），用户关闭面板后进程持续运行但无任何可见 UI 入口恢复面板，只能通过任务管理器强制终止。
- **Impact**: 用户体验极差，每次运行后残留僵尸进程。
- **Fix suggestion**: 至少实现以下之一：
  - 提供系统托盘图标（`QSystemTrayIcon`）及右键退出菜单
  - 允许 `setQuitOnLastWindowClosed(True)` 并让隐藏不等于关闭
  - 注册全局快捷键退出

### 4. [src/clipboard_watcher.py:62–63] 裸 `except Exception: pass` 静默吞掉所有异常
- **Problem**: `_poll` 方法整体包裹在 `try: ... except Exception: pass` 中。任何剪贴板访问异常、类型错误、逻辑 bug 都被完全静默吞噬，包括开发者自己引入的错误。
- **Impact**: 当剪贴板访问失败时静默跳过是合理设计意图，但当前实现也吞掉了编程错误（如 `AttributeError`、`TypeError`），导致 bug 无法被发现。
- **Fix suggestion**: 仅捕获预期的剪贴板访问异常（如 `RuntimeError`），或至少记录日志/打印 stderr：
```python
except RuntimeError:
    pass  # 剪贴板繁忙，下次重试
except Exception as e:
    import sys
    print(f"[ClipboardWatcher] 未预期错误: {e}", file=sys.stderr)
```

### 5. [src/clipboard_store.py:44–48] `re_copy` 命名误导——方法仅检索条目而非执行「重新复制」
- **Problem**: 设计文档定义 `re_copy(item_id)` 为「调用系统剪贴板 API 写回」。当前实现仅在内部列表中查找并返回 `ClipItem` 对象，实际剪贴板写操作在 `HistoryPanel._on_re_copy` 中完成。方法名与实际职责不符。
- **Impact**: 命名混淆导致代码可读性下降；其他模块调用此方法时可能误解其行为。
- **Fix suggestion**: 重命名为 `get_by_id(item_id) -> ClipItem | None`，将「重新复制」职责保留在 UI 层。

---

## Warnings

### 6. [src/clipboard_watcher.py] `app_source` 始终为 "unknown"——从未尝试获取来源应用
- **Problem**: 设计文档要求 `app_source`「尽力获取」来源应用信息。整个代码库中该字段只被初始化为默认值 `"unknown"`，Watcher 从未尝试获取（如通过 Windows API 获取前台窗口标题）。
- **Impact**: 设计合规性缺失，用户无法获知剪贴内容的来源应用。
- **Fix suggestion**: 在 `_poll` 中通过 `win32gui.GetWindowText(win32gui.GetForegroundWindow())` 获取（Windows 平台），或保持 "unknown" 并添加 TODO。

### 7. [src/history_panel.py:174–175] 面板展开/收起无动画效果
- **Problem**: 设计文档明确要求「下滑动画 (200ms)」和「上滑动画 (150ms)」。当前 `_animate_hide` 仅调用 `self.hide()`，无任何过渡动画。`show_at` 也直接调用 `self.show()`。
- **Impact**: 用户体验与设计预期差距大，面板突兀出现/消失。
- **Fix suggestion**: 使用 `QPropertyAnimation` 对 `geometry` 或 `pos` 属性做动画过渡，或在 `show_at` 时从 `y - height` 位置滑动到目标位置。

### 8. [src/tab_bar.py:40–44] TabBar 初始位置仅在构造时计算一次，不响应屏幕变化
- **Problem**: 设计文档要求「每次展开时重新计算右上角位置」应对多显示器/分辨率变化。当前 `_position_top_right` 仅在 `__init__` 调用，如果 TabBar 被拖动到其他位置、屏幕分辨率变化、或显示器热插拔，位置不会自动更新。
- **Impact**: 多显示器场景下，面板可能出现在错误的屏幕或位置。
- **Fix suggestion**: 在 `HistoryPanel.show_at` 调用前重新计算 TabBar 位置，或监听 `QApplication.primaryScreen().geometryChanged` 信号。

### 9. [src/history_panel.py:120–123] `show_at` 不检查面板是否越屏
- **Problem**: 当 TabBar 被拖到屏幕底部或左侧时，380×480 的面板可能超出屏幕边界，部分内容不可见。
- **Impact**: 在屏幕边缘使用时的可用性问题。
- **Fix suggestion**: 在 `show_at` 中添加边界夹持：
```python
screen_geo = QApplication.primaryScreen().availableGeometry()
x = max(0, min(x, screen_geo.right() - self.width()))
y = max(0, min(y, screen_geo.bottom() - self.height()))
```

### 10. [src/history_panel.py:125–134] 搜索无匹配时缺失「无匹配记录」提示
- **Problem**: 设计文档要求「无匹配时显示 '无匹配记录'」。当前 `_refresh_list` 在搜索结果为空时仅显示空列表，无任何提示文字。
- **Impact**: 用户可能误以为搜索功能未生效或程序出错。
- **Fix suggestion**: 当 `items` 为空时，添加一个不可点击的占位条目显示 "无匹配记录"，或使用 `QListWidget` 的 `setEmptyText` 等效方法（通过叠加 QLabel）。

### 11. [src/history_panel.py:26–46] SearchBox 缺少清空按钮
- **Problem**: 设计文档要求「清空按钮在右侧」。当前 `SearchBox` 仅有输入框，无右侧清空 ✕ 按钮。
- **Impact**: 用户需手动全选删除搜索文本，交互不便。
- **Fix suggestion**: 使用 `QLineEdit.setClearButtonEnabled(True)`（Qt 5.2+ 支持）或添加自定义 `QAction`。

### 12. [src/clipboard_watcher.py:49] HTML 预览用 `[:80]` 截断可能切断标签中间
- **Problem**: `preview = html[:80].replace("\n", " ")`——若 HTML 内容第 80 字符恰好落在标签中间（如 `<div class="contain`），预览显示为破碎的标签字符串。
- **Impact**: 预览可读性差，视觉混乱。
- **Fix suggestion**: 先用简单正则剥离 HTML 标签再截断（如 `re.sub(r'<[^>]*>', '', html)[:80]`），或保留完整结构但标记截断。

### 13. [src/clipboard_store.py:25–30] `add()` 方法不拒绝空内容条目
- **Problem**: 设计文档要求「剪贴板为空 → 跳过，不添加空条目」。当前 Watcher 中对文本做了 `text.strip()` 检查，但对 `ClipboardStore.add()` 本身无守卫。若有模块直接调用 `add(ClipItem(type="text", content="", preview=""))` 会添加空条目。
- **Impact**: 防御性编程不足；理论上可被意外触发。
- **Fix suggestion**: 在 `add()` 开头添加内容非空校验：
```python
if not item.content or (item.type == "text" and not item.content.strip()):
    return
```

### 14. [src/clipboard_watcher.py:29–40] `_poll` 中图片优先级高于文本，但未回退存储文本
- **Problem**: 当剪贴板同时包含图片和文本时，代码优先匹配图片并 `return`，文本版本被忽略。但某些场景下（如 Excel 复制），剪贴板同时有图片（截图）和文本（数据），图片可能对用户意义较小。
- **Impact**: 设计文档未明确优先级策略，当前行为可能丢失用户期望的文本内容。
- **Fix suggestion**: 考虑同时存储图片和文本为两条独立条目，或允许用户配置优先级。至少文档化当前行为。

---

## Suggestions

### 15. [src/clipboard_store.py:8–15] `ClipItem` 缺少 type 枚举约束
- 当前 `type` 字段为自由字符串，无类型安全。建议使用 `typing.Literal["text", "image", "html"]` 或 `StrEnum` 约束合法类型。

### 16. [src/history_panel.py:131–133] 列表条目前景色硬编码为 `Qt.GlobalColor.white`
- 使用 `list_item.setForeground(Qt.GlobalColor.white)` 而非设计 Token `#CDD6F4`。当前效果近似但严格不符合设计 Token 体系，Catppuccin 主题一致性受损。

### 17. [src/history_panel.py:71] HistoryList 字体与设计不符
- 设计文档指定片段预览使用 JetBrains Mono **12px**；代码中使用 `QFont("JetBrains Mono", 10)`（10pt ≈ 13.3px，但 pt≠px，实际渲染可能不同）。且点大小与像素大小换算依赖屏幕 DPI。建议使用 `QFont.setPixelSize(12)`。

### 18. [src/history_panel.py:56] HistoryList 样式表中 `surface` 变量定义但未在 item 样式中使用
- 第 55 行定义了 `surface = COLORS["surface"]` 但 item 的 stylesheet 中直接写死了 `#45475A`（分隔线色）。`surface` 变量在第 68 行的 `hover` 样式中使用。代码意图正确但表面上有未使用变量的嫌疑——实际上是被使用了，但位置靠后不直观。

### 19. [src/clipboard_watcher.py:65–72] `_image_to_bytes` 每次调用都 import PySide6 模块
- `from PySide6.QtCore import QByteArray, QBuffer, QIODevice` 放在方法体内而非文件顶部。虽然 import 有缓存不会重复加载，但违反 PEP 8 规范（import 应在文件顶部）。若意图是延迟加载，可加注释说明。

### 20. [src/history_panel.py:146–148] `_on_re_copy` 中图片解码的 `import base64` 也在方法内
- 同上，应移至文件顶部导入。

### 21. [src/tab_bar.py:63] `mouseMoveEvent` 拖拽时无边界限制
- 用户可将 TabBar 拖到屏幕外导致无法找回。建议限制在 `screen.availableGeometry()` 内。

### 22. [src/clipboard_store.py:39–42] `search()` 每次创建新列表——大数据量下性能退化
- 当前对每个搜索请求完整遍历 `_items` 并创建新列表。对于数百条记录可接受，但若积累数千条（长期运行），建议添加简单索引或限制历史条目数量上限。

### 23. [src/clipboard_store.py:25–30] 去重仅与最新一条比较——可能遗漏非连续重复
- 当前逻辑：与 `_items[0]`（最新一条）比较。如果用户复制顺序为 A → B → A（B 与 A 不同），A 会被重复添加。设计文档写「连续复制相同内容 → 不重复添加」，当前实现符合「连续」语义，但 Watcher 层有独立的 MD5 去重（与上一次贴板内容比较），两层去重逻辑不同。建议统一或明确文档化。

### 24. [tests/test_clipboard_store.py:57–62] `test_items_changed_signal` 未测试 `delete` 触发的信号
- 仅测试了 `add` 触发信号，缺少对 `delete` 发射 `items_changed` 的验证。

### 25. [tests/test_clipboard_watcher.py] 缺少真实剪贴板交互的集成测试
- 现有测试仅检查了内部状态（timer、flag、MD5 函数），未模拟真实剪贴板内容变化（mimeData mock）来验证 `_poll` 的添加行为。设计文档期望覆盖「轮询检测、跳过自身写入、跳过空/超大内容」。

---

## Design Compliance

| 设计要求 | 状态 | 说明 |
|---------|------|------|
| 四大模块 (Store/Watcher/TabBar/Panel) | ✅ | 全部实现 |
| `ClipItem` 数据结构（id/type/content/preview/timestamp/app_source） | ⚠️ | `app_source` 从未被填充 |
| `add` 去重与最新一条比较 | ✅ | 正确实现 |
| `delete` 确认弹窗 | ⚠️ | 弹窗逻辑存在但触发入口（✕ 按钮）缺失 |
| `search` 返回匹配条目 | ✅ | 大小写不敏感匹配 |
| `re_copy` 写回系统剪贴板 | ❌ | HTML 写回使用 `setText` 而非 `setHtml`（见 Critical #1） |
| TabBar 200×30px，置顶，无边框，无任务栏 | ✅ | 正确 |
| TabBar 右上角定位 + 可拖动 | ⚠️ | 定位正确，拖动无边界限制 |
| HistoryPanel 380×480px，置顶，无边框 | ✅ | 正确 |
| 搜索框圆角 8px，`#2A2A3C` 背景 | ✅ | 正确 |
| 类型圆点颜色（文本白/图片蓝/HTML 橙） | ✅ | `TYPE_DOTS` 定义正确但未在渲染中使用 |
| 分隔线 `1px dashed #45475A` | ✅ | 正确 |
| 删除按钮半透明 `#6C7086` / 悬浮 `#F38BA8` | ❌ | 完全未实现 |
| 鼠标移入展开 / 移出 300ms 延迟收起 | ⚠️ | 延迟逻辑存在，但无动画 |
| 下滑动画 200ms / 上滑动画 150ms | ❌ | 未实现 |
| 剪贴板为空跳过 | ✅ | Watcher 中 text 检查了 `strip()` |
| 超长文本预览截断 80 字符 | ✅ | 正确 |
| 超大图片 >10MB 跳过 | ✅ | 正确 |
| 自身 re-copy 跳过 | ✅ | `_is_self_copy` 标志位 |
| 屏幕分辨率/多显示器重新计算位置 | ❌ | 仅在构造时计算一次 |
| 无匹配显示「无匹配记录」 | ❌ | 未实现 |
| 清空按钮在搜索框右侧 | ❌ | 未实现 |
| 字体 JetBrains Mono 12px | ⚠️ | 使用了 10pt 而非 12px |
| 色彩 Token 体系（Catppuccin） | ⚠️ | 大部分正确，个别硬编码 white |

**合规率**: ~18/27 项完全合规，9 项存在偏差或未实现。

---

## Test Coverage

### 已覆盖
| 测试 | 文件 |
|------|------|
| `add` 添加条目并 `get_all` 返回 | `test_clipboard_store.py::test_add_and_get_all` |
| 相同内容去重 | `test_clipboard_store.py::test_deduplicate_same_content` |
| 不同内容均添加 | `test_clipboard_store.py::test_different_content_adds_both` |
| `delete` 删除存在的条目 | `test_clipboard_store.py::test_delete` |
| `delete` 不存在的 ID 不崩溃 | `test_clipboard_store.py::test_delete_nonexistent_does_not_crash` |
| `search` 关键词过滤 | `test_clipboard_store.py::test_search` |
| `items_changed` 信号发射 | `test_clipboard_store.py::test_items_changed_signal` |
| `re_copy` 返回正确条目 | `test_clipboard_store.py::test_re_copy_returns_item` |
| `re_copy` 不存在的 ID 返回 None | `test_clipboard_store.py::test_re_copy_nonexistent_returns_none` |
| MD5 哈希变化检测 | `test_clipboard_watcher.py::test_content_hash_detects_change` |
| Watcher timer 存在且间隔 500ms | `test_clipboard_watcher.py::test_watcher_has_timer` |
| Watcher 初始 `_last_md5` 为 None | `test_clipboard_watcher.py::test_watcher_starts_without_last_md5` |
| `notify_self_copy` 设置标志 | `test_clipboard_watcher.py::test_notify_self_copy_sets_flag` |
| self-copy 模式下跳过轮询 | `test_clipboard_watcher.py::test_poll_skips_when_self_copy` |

### 缺失测试
| 缺失项 | 严重程度 |
|--------|---------|
| `delete` 发射 `items_changed` 信号 | Medium |
| `ClipItem` 默认值（UUID 唯一性、timestamp 合理范围） | Low |
| `ClipboardStore.add()` 拒绝空内容 | Medium |
| Watcher `_poll` 文本/HTML/图片添加流程（mock 剪贴板） | **High** |
| Watcher 跳过 >10MB 图片 | Medium |
| Watcher 跳过空文本剪贴板 | Medium |
| Watcher 跳过自身写入后下一轮恢复检测 | Medium |
| `re_copy` / `get_by_id` 在空 store 中调用 | Low（已有 None 测试） |
| TabBar 拖拽行为 | Low（GUI 手动验证） |
| HistoryPanel 搜索过滤 UI 联动 | Low（GUI 手动验证） |
| HistoryPanel 删除确认弹窗流程 | Low（GUI 手动验证） |
| 多条目插入后的排序正确性（时间倒序） | Low |

---

## 总结

代码实现了设计文档的核心框架——四大模块（ClipboardStore、ClipboardWatcher、TabBar、HistoryPanel）骨架完整，数据流和信号机制正确连接。单元测试覆盖了 Store 层的主要逻辑。

**三个最紧急的问题**：
1. **HTML 重拷丢失格式**（#1）——核心功能缺陷
2. **删除按钮缺失**（#2）——用户无法逐条管理历史
3. **应用无法退出**（#3）——每次运行残留进程

建议按 Critical → Warning → Suggestion 优先级修复，重点先解决上述三项后再进入手动验证阶段。
