# Clipboard Hub V2 Verification

## Automated

- Syntax command: `python -m py_compile src\__init__.py src\clip_item.py src\clipboard_codec.py src\clipboard_store.py src\clipboard_watcher.py src\history_panel.py src\main.py src\screen_geometry.py src\source_app.py src\sqlite_repository.py src\tab_bar.py src\theme.py`
- Syntax result: exit code 0
- Pytest command: `pytest tests -q`
- Pytest result: 111 passed, 0 failed

## Code-aligned findings

- SQLite persistence is implemented and loaded on startup.
- Database uses WAL and checkpoints on shutdown.
- Corrupt databases are renamed to `clipboard_hub.db.corrupt-<timestamp>` and recreated.
- Retention limits are enforced at 1000 items and `200 × 1024 × 1024` bytes.
- Oversized single items are rejected instead of evicting all history.
- Clipboard items can preserve text, HTML, and PNG in one record.
- Source application and window title are captured on Windows when available.
- TabBar snapping logic is implemented for the current display after drag release.
- History cards show success/failure feedback when re-copy succeeds or fails.
- HistoryPanel and TabBar both follow system theme updates.
- History items are localized in Chinese and use a polished light Fluent card style.
- Image history items render a balanced preview card with upper preview area and lower metadata area.

## Manual

Not completed in this verification pass.

Pending checks:

- Multi-format clipboard result across real Windows apps
- Persistence after restart in a live app session
- Source application accuracy in real foreground-window scenarios
- Copy feedback visuals in a live UI session
- Multi-monitor snap behavior on actual displays
- Theme readability on the target desktop
- Retention limits in an interactive long-running session

## Remaining Issues

- Manual acceptance is still pending; this file only reflects automated verification.
- Source window titles are shown directly in card metadata, so privacy impact is higher than the original design assumed.
- Clipboard polling is timer-based, not OS event based.
- HistoryPanel remains fixed at `420 × 520` and does not yet scale to shorter screens.
