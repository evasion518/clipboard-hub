# 学习笔记：codex vs 我的实现差距分析

> 日期: 2026-06-23  
> 来源: 逐文件阅读 codex 代码后总结

---

## 一、整体架构差异

| | 我的实现 | codex |
|---|---------|-------|
| 源文件数 | 4 个扁平文件 | 7 个模块，职责垂直切分 |
| 持久化 | 无 | SQLite + WAL + 损坏恢复 |
| 模型 | 简单的 dataclass，3 个字段 | frozen dataclass，多格式共存，兼容层 |
| 编解码 | 内联在 watcher/panel 里 | 独立 ClipboardCodec 类 |
| 来源追踪 | 无 | Windows API (ctypes 调 user32/kernel32/psapi) |
| 测试 | 14 个，GUI 未测 | 25 个，全覆盖到 history_panel |

---

## 二、逐模块学习要点

### 2.1 ClipItem — 多格式共存模型

**我的做法：** 每个条目只存一种格式 (`type + content`)，文本/图片/HTML 互斥。

**codex 的做法：** 三种格式共存于同一个对象：
```python
@dataclass(frozen=True)
class ClipItem:
    text: str | None      # 纯文本
    html: str | None      # 富文本
    image_png: bytes | None  # 图片原始 PNG
    image_size: tuple[int, int] | None
    preview: str
    source_app: str
    source_window: str | None
```

**好处：** 剪贴板经常同时包含多种格式（比如从网页复制既有 HTML 又有纯文本）。多格式共存意味着回写时可以恢复原始富文本。我那种"存一丢二"会导致格式丢失。

**可复用技巧：**
- `frozen=True` — 不可变对象，线程安全，哈希可缓存
- `__init__` 中用 `object.__setattr__` 绕过 frozen 限制
- `_coerce_legacy_inputs` — 兼容旧版 `type+content` 协议，平滑升级
- `content_hash` 用 SHA256 跨所有格式联合哈希，比 MD5 碰撞风险低
- `build_preview` 优先级链：text > html 纯文本 > image 尺寸

### 2.2 ClipboardCodec — 独立编解码层

**我的做法：** 编解码逻辑散落在 watcher（读剪贴板）和 panel（写回剪贴板）里，代码重复。

**codex 的做法：** 单一 `ClipboardCodec` 类：
```python
class ClipboardCodec:
    MAX_IMAGE_BYTES = 10 * 1024 * 1024

    @staticmethod
    def decode(mime: QMimeData, source_app, source_window) -> ClipItem | None
    @staticmethod
    def encode(item: ClipItem) -> QMimeData
    @staticmethod
    def image_to_png(image) -> bytes | None
```

**好处：** 
- 读写双向逻辑集中，改一处生效两处
- 单元测试可以对 codec 独立测，不需要真实剪贴板
- `decode` 返回 `None` 表示空内容，watcher 只需检查返回值

**可复用技巧：**
- 优先用 `mime.data("image/png")` 获取原始 PNG 字节，避免二次编码损失
- `encode` 同时设置 `setData("image/png", ...)` 和 `setImageData(...)`，兼容不同程序
- `image_to_png` 有完整的空值/失败链：`None → QImage() → null → buffer 失败 → 超大 → None`

### 2.3 SourceAppProvider — Windows API 调用

**我的做法：** 无来源追踪，`app_source` 始终为 `"unknown"`。

**codex 的做法：** 通过 `ctypes` 调用 Win32 API：
```
user32.GetForegroundWindow → 获取前台窗口句柄
user32.GetWindowThreadProcessId → 获取进程 ID
kernel32.OpenProcess → 打开进程
psapi.GetProcessImageFileNameW → 获取进程 EXE 路径
```

**可复用技巧：**
- API 调用封装在独立的 `WindowsForegroundApi` 类，方便 mock 测试
- `SourceAppProvider` 可接受 `api` 参数注入，测试时替换为假 API
- 异常全部捕获，返回 `SourceInfo(app="unknown")` 作为降级
- `PureWindowsPath(image_name).name` 提取文件名（如 `chrome.exe`）
- 用 `PROCESS_QUERY_LIMITED_INFORMATION` 最小权限打开进程，避免权限问题

### 2.4 SQLiteRepository — 持久化 + 损坏恢复

**我的做法：** 无持久化。

**codex 的做法：**
```python
class SQLiteRepository:
    def __init__(path)           # 建表 + WAL 模式
    def open_with_recovery(path) # 损坏时备份 + 重建
    def insert(item)             # INSERT OR REPLACE
    def delete(item_id) -> bool  # 按 ID 删除
    def delete_oldest()          # 容量淘汰（删最旧一条）
    def load_all() -> list       # 全部加载按时间倒序
    def totals() -> (count, bytes) # 统计
    def checkpoint()             # WAL checkpoint
    def close()
```

**可复用技巧：**
- `PRAGMA journal_mode=WAL` — 写不阻塞读，崩溃恢复更强
- `open_with_recovery` 类方法：捕获 `sqlite3.DatabaseError` → 重命名损坏文件为 `.corrupt-时间戳` → 重建空库
- `INSERT OR REPLACE` — 幂等插入，相同 ID 直接覆盖
- `delete_oldest` — 容量管理的基础，调用方只需设上限 + 循环调用
- `with self._connection:` — 自动事务管理
- `checkpoint()` — 手动 WAL 合并，适合退出时调用确保数据落盘

### 2.5 ClipboardWatcher — 状态机去重

**我的做法：** 简单 MD5 + `_is_self_copy` 布尔标志。

**codex 的做法：**
```python
class ClipboardWatcher:
    pending_self_hash: str | None  # 待跳过的自复制哈希
    _last_seen_hash: str | None    # 上次看到的哈希
    last_exception: Exception | None  # 异常可见性

    def poll():
        1. decode(mime) → item
        2. 空 → 清除 _last_seen_hash
        3. pending_self_hash == item.content_hash → 跳过（自复制）
        4. 有其他 pending → 清除（内容已变）
        5. _last_seen_hash == item.content_hash → 跳过（去重）
        6. store.add(item) → 更新 _last_seen_hash
```

**好处：**
- `pending_self_hash` 存的是哈希值而非布尔值——即使自复制后剪贴板被外部修改，也能正确清除 pending 状态
- `last_exception` 公开，调用方可以读取诊断
- `autostart=False` 选项，测试时可以先构造 Watcher 再手动启动 timer
- clipboard/source_provider 可注入，方便测试

---

## 三、设计模式提取

### 模式 1：冻结值对象 + 兼容层
```python
@dataclass(frozen=True)
class Value:
    # 新字段
    # __init__ 接受旧字段，内部转换
    # create() 工厂方法（推荐入口）
    # object.__setattr__ 绕过 frozen
```

### 模式 2：Codec 分离
```
[系统剪贴板] → ClipboardCodec.decode() → ClipItem
[ClipItem]   → ClipboardCodec.encode() → 系统剪贴板
```
编解码独立于存储和 UI，可单独测试。

### 模式 3：Repository 模式
```
[ClipItem] → SQLiteRepository.insert/delete/load_all
```
存储逻辑与业务逻辑分离，后面换存储方案（JSON、云端）只需换 Repository 实现。

### 模式 4：Provider + API 注入
```python
class SourceAppProvider:
    def __init__(self, api=None):  # 可注入 mock
        self._api = api or RealAPI()
```
API 调用封装在可替换的类里，测试时注入假实现。

### 模式 5：损坏恢复
```python
try:
    repo = SQLiteRepository(path)
except DatabaseError:
    backup = path.rename("corrupt-timestamp")
    repo = SQLiteRepository(path)  # 重建空库
```

---

## 四、我应该改进的地方

1. **多格式共存** — 剪贴板同时有 text+html 时应该都保存，而不是只存一种
2. **Codec 独立** — 编解码不应该散落在 watcher 和 panel 里
3. **值对象不可变** — `frozen=True` 减少 bug
4. **异常可见性** — 不要 `pass`，至少记录 `last_exception`
5. **依赖注入** — 方便测试，timer/clipboard/source 都应该可注入
6. **持久化** — SQLite 一行 pip install 都不需要
7. **WAL 模式** — 性能远超默认 journal
8. **损坏恢复** — 文件损坏不应该导致程序崩溃或数据全丢
