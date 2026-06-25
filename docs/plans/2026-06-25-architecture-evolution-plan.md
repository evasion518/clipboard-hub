# Clipboard Hub 架构演进文档

最后更新：2026-06-25

## 1. 当前定位

Clipboard Hub 是一个 Windows 本地 PySide6 剪贴板历史工具。

当前核心能力：

- 轮询系统剪贴板。
- 保存文本、HTML、文件路径文本。
- 使用 SQLite 持久化历史。
- 鼠标悬停屏幕右上角 TabBar 展开历史面板。
- 点击历史项后按纯文本重新写回剪贴板。
- 当前不保存、不预览、不写回图片。

当前约束：

- 历史上限约 1000 条。
- SQLite 只作为本地持久化。
- UI 使用 PySide6，不引入新前端框架。
- 优先保持项目小而清晰，只在真实问题出现后引入更重架构。

## 2. 已完成阶段

### 阶段 1：删除历史负担

已完成：

- 删除 legacy `ClipItem` API、死代码和取消的图片编码入口。
- 测试统一围绕当前 `ClipItem.create(text=...)`、`ClipItem.create(html=...)` 路径。
- 全量测试通过。

### 阶段 2：拆分 UI 模块

已完成：

- `history_panel.py` 拆分到：
  - `src/ui/history_panel.py`
  - `src/ui/history_list.py`
  - `src/ui/history_card.py`
- `theme`、`screen_geometry`、`tab_bar` 迁入 `src/ui/`。
- 根模块保留兼容导出，例如 `src/history_panel.py` 继续导出 UI 类和 helper。
- 全量测试通过。

### 阶段 3：最小日志

已完成：

- 使用 stdlib `logging`。
- 覆盖启动、数据库路径、损坏恢复、剪贴板轮询失败、SQLite 写入失败。
- 默认不记录剪贴板正文。
- 全量测试通过。

## 3. 本轮性能与交互修复

### 用户反馈

- 启动和复制明显卡。
- 鼠标移出面板后需要 1-3 秒才收回。
- 从右上角小光标移动到面板时，面板会立刻收回。
- 在面板内操作后，鼠标移出又可能不收回。

### 实测瓶颈

旧实现中，历史列表每条记录都是一套 QWidget 子树。1000 条历史时：

- 首次展开约 8.2 秒。
- 清空搜索恢复 1000 条约 8.8 秒。

剪贴板轮询也有大内容成本：

- 10MB 文本首次轮询写入约 189ms，重复轮询约 47ms。
- 50MB 文本首次轮询写入约 963ms，重复轮询约 257ms。

SQLite 启动加载不是最大瓶颈：

- 1000 条、约 100MB 历史加载约 122ms。
- 约 200MB 历史加载约 442ms。

### 根因

- `HistoryPanel._refresh_list()` 会清空列表并重建所有行。
- 旧 `HistoryList` 使用 `QListWidget.setItemWidget(...)`，每条历史都创建一个 `HistoryCard` QWidget。
- 旧 `HistoryCard` 每条包含多个 QWidget、layout、stylesheet，之前还包含 `QGraphicsDropShadowEffect`。
- 自动隐藏逻辑把焦点和鼠标位置混在一起，导致“进不了面板”和“操作后不收回”两个相反问题。

## 4. 本轮实际修改

### 4.1 列表改为 model/delegate

修改文件：

- `src/ui/history_list.py`

做了什么：

- `HistoryList` 从 `QListWidget + setItemWidget(...)` 改为 `QListView`。
- 新增 `HistoryListModel(QAbstractListModel)` 保存行数据。
- 新增 `HistoryDelegate(QStyledItemDelegate)` 负责绘制行。
- 行内容不再创建 per-row QWidget。

保留行为：

- 点击普通区域仍触发重新复制。
- 点击右侧动作区域仍触发删除请求。
- 反馈文本、序号、时间仍可显示。
- 搜索、删除、复制流程不改数据层。

### 4.2 删除每行阴影效果

修改文件：

- `src/ui/history_card.py`

做了什么：

- 删除 `QGraphicsDropShadowEffect`。
- `HistoryCard` 目前主要保留给兼容导出和少量旧 helper；实际列表显示走 delegate。

原因：

- 每行图形效果会参与重绘和鼠标移动路径。
- 对剪贴板历史工具来说收益小，成本高。

### 4.3 限制首批渲染数量

修改文件：

- `src/ui/history_panel.py`
- `src/history_panel.py`

做了什么：

- 新增并导出 `RENDER_ITEM_LIMIT = 24`。
- 面板刷新和搜索结果只渲染前 24 条。
- 可见且未搜索时新增记录走增量 prepend，并 trim 到 24 条。

原因：

- 当前面板高度只需要显示少量可见行。
- 用户未明确要求浏览 24 条以后的旧记录。

后续触发条件：

- 如果用户需要浏览更旧记录，再加“加载更多”或分页。
- 暂不引入复杂虚拟滚动、FTS 或后台线程。

### 4.4 修正面板隐藏逻辑

修改文件：

- `src/ui/history_panel.py`

当前规则：

- TabBar 或 Panel 触发离开时，启动短延迟隐藏。
- 真正隐藏前检查鼠标全局位置。
- 鼠标已进入面板：不隐藏。
- 鼠标不在面板内：隐藏。
- 焦点不再阻止隐藏。

解决的问题：

- 鼠标从小光标移动到面板时，不会半路收回。
- 在面板里点击、搜索、复制后，鼠标真正移出仍会收回。

### 4.5 更新测试

修改文件：

- `tests/test_history_panel.py`

新增/调整覆盖：

- 大历史只渲染 `RENDER_ITEM_LIMIT` 条。
- 历史列表不再为每行挂 QWidget，`indexWidget(...) is None`。
- model/delegate 仍保留序号、反馈文本和右侧删除点击。
- 鼠标从小光标移动到面板时不收回。
- 焦点在面板内但鼠标移出时仍收回。
- 复制后反馈和自复制去重逻辑仍可用。

### 4.6 增加一键删除全部历史

修改文件：

- `src/ui/history_panel.py`
- `src/clipboard_store.py`
- `src/sqlite_repository.py`
- `tests/test_history_panel.py`
- `tests/test_clipboard_store.py`
- `tests/test_sqlite_repository.py`

做了什么：

- 在搜索框和历史列表之间新增 `一键删除` 按钮。
- 点击一键删除时弹出确认框，确认后清空全部历史并刷新面板。
- `ClipboardStore.clear()` 清空内存列表、重置总字节数，并发出 `items_changed`。
- `SQLiteRepository.clear()` 使用单条 `DELETE FROM clipboard_items` 清空持久化历史，不改 schema。

当前行为：

- 空历史时一键删除按钮不可用。
- 有历史时按钮可用，确认后面板进入空状态。
- 只清空本地历史记录，不影响当前系统剪贴板内容。

### 4.7 调整单条删除交互

修改文件：

- `src/ui/history_panel.py`
- `tests/test_history_panel.py`

做了什么：

- 单条历史右侧删除动作改为直接删除，不再弹出确认框。
- 删除前仍会清理该条记录的复制反馈状态和反馈计时器。
- 一键删除全部历史仍保留确认框，避免误删全部记录。

## 5. 实测结果

本轮优化前：

- 1000 条历史首次展开约 8.2 秒。
- 清空搜索恢复 1000 条约 8.8 秒。

中间方案：

- 限量 80 条后，首次展开约 0.38 秒。

当前方案：

- `QListView + model/delegate`
- `RENDER_ITEM_LIMIT = 24`
- 无 per-row QWidget

实测：

- 1000 条历史展开约 11.7ms。
- 搜索约 6.6ms。
- 清空搜索约 4.6ms。
- 绘制路径通过 viewport grab 验证。

## 6. 验证

最近一次验证：

```text
pytest -q
138 passed in 2.13s
```

## 7. 当前不做

当前明确不做：

- 不改 SQLite schema。
- 不引入线程池。
- 不引入 asyncio。
- 不引入 SQLite FTS。
- 不做 `AddClipboardFormatListener`。
- 不做插件系统。
- 不做完整分页或加载更多。
- 不恢复图片保存/预览/写回。

原因：

- 当前真实瓶颈已通过列表渲染修复。
- 历史量仍是约 1000 条。
- 搜索 O(n) 仍可接受。
- 没有证据表明 500ms 轮询导致丢复制或明显 CPU/耗电问题。

## 8. 后续触发条件

只有出现以下真实需求时再继续扩展：

- 用户需要浏览 24 条之外的旧记录：加“加载更多”或分页。
- 历史上限提升到几万条且搜索卡顿：再做 SQLite FTS。
- 快速连续复制确认丢失，或 CPU/耗电被测出问题：再做 `AddClipboardFormatListener`。
- schema 出现第二次以上真实变更：再做迁移机制。
- UI 状态继续变复杂且难测：再考虑 ViewModel。

## 9. 维护规则

后续修改请遵守：

- 先读当前代码和测试，不按文档空想重写。
- 每次只改一个真实问题。
- 不新增依赖，除非已有代码和 stdlib 做不到。
- 不引入只有一个实现的抽象接口。
- 不为已取消的图片功能写新代码。
- 每次行为修改必须有测试。
- README 和当前产品口径优先于旧设计文档。

## 10. 最终判断

这个项目不需要更“企业级”的架构。

它需要：

- 更少历史残留。
- 更瘦的 UI。
- 更明确的数据流。
- 更少猜测式扩展点。

事件驱动、FTS、迁移系统都是合理后续方向，但必须由真实问题触发。
