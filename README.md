# Clipboard Hub

Windows 桌面剪贴板历史工具。程序会轮询系统剪贴板，记录文本、HTML 和文件路径文本；鼠标悬停右上角 TabBar 可展开历史面板，点击条目可按纯文本重新写回剪贴板。

## 运行

```bash
pip install -r requirements.txt
python -m src.main
```

## 打包为可执行文件

```bash
pip install pyinstaller
pyinstaller clipboard_hub_launcher.spec
```

输出在 `dist/Clipboard Hub/` 目录，双击 `Clipboard Hub.exe` 即可运行。整个文件夹 (约 153 MB) 可直接分发给其他 Windows 用户，无需安装 Python。

## 当前实现

- 使用 SQLite 持久化历史记录，启动时自动恢复。
- 单条记录可保存 `text/plain` 和 `text/html`；文件剪贴板会显示为本地路径文本。
- 历史保留策略为最多 1000 条、总内容大小最多 200 MiB。
- 图片剪贴板不再作为图片入库，也不会作为图片写回；如果剪贴板内容是文件，则显示文件路径。
- 通过 Windows 前台窗口 API 采集来源应用名和窗口标题；失败时记为 `unknown`。
- TabBar 可拖动，松手 600ms 后吸附到其当前所在屏幕的右上角。
- 历史面板支持搜索、逐条直接删除、重新复制、一键删除全部历史，以及成功/失败短暂视觉反馈。
- 一键删除按钮位于搜索框和历史列表之间，点击后需要确认；单条删除不再弹确认框。
- 当前界面已按“冷白微蓝 / iOS 透明玻璃 / 紧凑文本列表”方向做过一轮美化，历史项采用紧凑复制框、倒序序号、两行渐隐、柔和分割线和等高删除按钮，复制后会显示 `已复制`，鼠标移出面板后可正常收回。
- 退出时执行 SQLite WAL checkpoint，正常重启后可恢复历史。

## 持久化位置

默认数据库文件名为 `clipboard_hub.db`。路径按以下顺序解析：

1. `QStandardPaths.AppDataLocation`
2. `QStandardPaths.GenericDataLocation / Clipboard Hub`
3. `%LOCALAPPDATA%\Clipboard Hub`
4. `XDG_DATA_HOME/clipboard-hub`
5. `~/.local/share/clipboard-hub`

在常见 Windows 环境下，通常会落在类似下面的位置：

```text
C:\Users\<User>\AppData\Roaming\Clipboard Hub\clipboard_hub.db
```

## 已知限制

- 目前只支持文本、HTML 和文件路径文本；不支持图片保存/写回、RTF、OCR、全局快捷键。
- 去重只针对“连续两次内容指纹相同”的情况，非连续重复记录仍会保留。
- 来源应用保存的是原始可执行文件名，例如 `Code.exe`、`chrome.exe`，未做更友好的名称映射；当前 UI 默认不展示来源应用或窗口标题，但搜索仍可命中这些字段。
- TabBar 只在拖动释放后重新吸附；当前未监听显示器热插拔或分辨率变化事件。
- HistoryPanel 当前为固定 `420×520`，不会按屏幕高度动态缩放，也没有展开/收起动画。
- 主题默认走 `system`，会跟随系统深浅主题；但当前视觉设计重点仍优先围绕浅色主题打磨。

## 设计偏好档案

如果后续还要继续做界面美化或保持同一风格，请先看这份档案：

- [docs/preferences/2026-06-24-ui-style-profile.md](/D:/Greasionix/clipboard-hub/docs/preferences/2026-06-24-ui-style-profile.md)

里面记录了这次界面迭代里确认过的审美方向、组件偏好、文案风格和实现边界，方便后续直接延续同一种做法。

后续产品化改进路线记录在 V2 设计文档中：

- [docs/specs/2026-06-23-clipboard-hub-v2-design.md](/D:/Greasionix/clipboard-hub/docs/specs/2026-06-23-clipboard-hub-v2-design.md)

## 隐私提醒

剪贴板历史可能包含密码、令牌、链接和私人内容。当前实现仅保存在本机 SQLite 中，不加密、不同步、也不会上传。
