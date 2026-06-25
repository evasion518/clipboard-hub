from src.clip_item import ClipItem
from src.sqlite_repository import SQLiteRepository


def test_round_trip_insert_load_all_close_reopen(tmp_path):
    path = tmp_path / "clipboard.db"
    item = ClipItem.create(
        text="plain text",
        html="<b>plain text</b>",
        image_png=b"\x89PNG\r\n\x1a\n",
        image_size=(12, 8),
        preview="custom preview",
        source_app="chrome.exe",
        source_window="Example page",
        id="item-1",
        timestamp=123.456,
    )

    repo = SQLiteRepository(path)
    repo.insert(item)
    repo.close()

    reopened = SQLiteRepository(path)
    try:
        assert reopened.load_all() == [item]
    finally:
        reopened.close()


def test_repository_uses_wal_with_normal_synchronous_for_low_latency(tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        assert repo._connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert repo._connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    finally:
        repo.close()


def test_delete(tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        first = ClipItem.create(text="a", id="first", timestamp=1.0)
        second = ClipItem.create(text="bb", id="second", timestamp=2.0)

        repo.insert(first)
        repo.insert(second)

        repo.delete(first.id)

        assert repo.load_all() == [second]
    finally:
        repo.close()


def test_clear_deletes_all_items(tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        repo.insert(ClipItem.create(text="a", id="first", timestamp=1.0))
        repo.insert(ClipItem.create(text="bb", id="second", timestamp=2.0))

        repo.clear()

        assert repo.load_all() == []
    finally:
        repo.close()


def test_open_with_recovery_backs_up_corrupt_database_and_returns_empty_repo(tmp_path):
    path = tmp_path / "clipboard.db"
    path.write_bytes(b"not a sqlite database")

    repo = SQLiteRepository.open_with_recovery(path)
    try:
        assert repo.load_all() == []
    finally:
        repo.close()

    backups = list(tmp_path.glob("clipboard.db.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"not a sqlite database"


def test_open_with_recovery_logs_database_recovery(tmp_path, caplog):
    path = tmp_path / "clipboard.db"
    path.write_bytes(b"not a sqlite database")

    with caplog.at_level("WARNING", logger="clipboard_hub"):
        repo = SQLiteRepository.open_with_recovery(path)
    try:
        messages = [record.getMessage() for record in caplog.records]
        assert any(message.startswith("Database recovery created backup at ") for message in messages)
    finally:
        repo.close()


def test_insert_logs_sqlite_write_failure(tmp_path, caplog):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    item = ClipItem.create(text="do not log this", id="item-1")
    repo.close()

    with caplog.at_level("ERROR", logger="clipboard_hub"):
        try:
            repo.insert(item)
        except Exception:
            pass

    messages = [record.getMessage() for record in caplog.records]
    assert "SQLite write failed" in messages
    assert all("do not log this" not in message for message in messages)
