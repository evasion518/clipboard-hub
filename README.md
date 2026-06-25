# Clipboard Hub v2

Windows 桌面剪贴板历史工具。系统托盘常驻，轮询系统剪贴板并记录文本、HTML 和文件路径；鼠标悬停屏幕右上角 TabBar 展开历史面板，支持搜索、复制、删除。

## 快速开始

### 直接运行

下载 [最新 Release](https://github.com/evasion518/clipboard-hub/releases/latest) 中的 `Clipboard-Hub-v2.zip`，解压后双击 `Clipboard Hub.exe` 即可，无需安装 Python。

### 从源码运行

```bash
pip install -r requirements.txt
python -m src.main
```

### 打包为可执行文件

```bash
pip install pyinstaller
pyinstaller clipboard_hub_launcher.spec
```

输出在 `dist/Clipboard Hub/`，整个文件夹可直接分发。

## v2 更新内容

### 架构重构
- UI 层拆分为独立模块：`geometry` / `history_card` / `history_list` / `history_panel` / `tab_bar` / `theme`
- 历史列表改为 `QPainter` delegate 自绘渲染，性能显著提升，不再为每条记录创建独立 Widget
- 新增 `SourceAppProvider`，通过 Win32 API 采集前台应用名和窗口标题
- `ClipboardCodec` 解码/编码分离，支持自复制去重（self-copy detection）
- `ClipboardStore` 增加 `items_changed` 信号，容量/字节数双重保留策略

### 主题系统
- 明 (`LIGHT_THEME`) / 暗 (`DARK_THEME`) / 跟随系统 (`system`) 三模式
- 冷白微蓝玻璃态面板 + 柔和渐变边框
- 复制反馈标签（成功 `已复制` / 失败 `复制失败`）短暂显示后自动消失

### 数据库
- SQLite WAL 模式 + `synchronous=NORMAL`，低延迟写入
- `open_with_recovery` 工厂方法：检测到损坏时自动备份并重建
- 退出时执行 `wal_checkpoint(TRUNCATE)`，保证下次启动可正常恢复

### 测试
- 140 个测试用例，覆盖 ClipItem / Codec / Store / Watcher / HistoryPanel / Main / Geometry / SQLiteRepository
- 使用 QSignalSpy 验证 Qt 信号行为
- 使用 monkeypatch 隔离外部依赖（QApplication、Clipboard API、文件系统）

## 当前实现

- SQLite 持久化，最多 1000 条 / 200 MiB，超出自动淘汰最旧记录。
- 支持 `text/plain`、`text/html`、文件路径（URL 列表转为路径文本）。
- 图片剪贴板不作为图片入库/写回。
- 去重：连续相同内容指纹（SHA-256）只保留一条；非连续重复仍保留。
- TabBar 可拖动，松手 600ms 后吸附到当前屏幕右上角。
- 历史面板固定 `420×520`，显示最近 24 条，支持搜索过滤。
- 单条删除直接生效，一键删除全部需确认。
- 鼠标移出面板自动收起。

## 持久化位置

默认数据库 `clipboard_hub.db`，路径解析顺序：

1. `QStandardPaths.AppDataLocation`
2. `QStandardPaths.GenericDataLocation / Clipboard Hub`
3. `%LOCALAPPDATA%\Clipboard Hub`
4. `XDG_DATA_HOME/clipboard-hub`
5. `~/.local/share/clipboard-hub`

Windows 下通常在：

```text
C:\Users\<User>\AppData\Roaming\Clipboard Hub\clipboard_hub.db
```

## 已知限制

- 仅支持文本、HTML 和文件路径；不支持图片保存/写回、RTF、OCR、全局快捷键。
- 去重仅针对连续相同内容指纹，非连续重复仍保留。
- 来源应用保存为原始可执行文件名（如 `Code.exe`），未做友好映射。
- TabBar 仅在拖动释放后吸附，未监听显示器热插拔或分辨率变化。
- 面板固定 `420×520`，无自适应缩放或展开动画。

## 设计文档

- [UI 风格档案](docs/preferences/2026-06-24-ui-style-profile.md)
- [V2 设计文档](docs/specs/2026-06-23-clipboard-hub-v2-design.md)
- [架构演进计划](docs/plans/2026-06-25-architecture-evolution-plan.md)

## 隐私提醒

剪贴板历史可能包含密码、令牌等敏感内容。所有数据仅保存在本机 SQLite 中，不加密、不同步、不上传。
