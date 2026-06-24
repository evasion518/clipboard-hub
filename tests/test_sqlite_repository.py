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


def test_delete_and_totals(tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        first = ClipItem.create(text="a", id="first", timestamp=1.0)
        second = ClipItem.create(text="bb", id="second", timestamp=2.0)

        repo.insert(first)
        repo.insert(second)

        assert repo.totals() == (2, first.size_bytes + second.size_bytes)

        repo.delete(first.id)

        assert repo.load_all() == [second]
        assert repo.totals() == (1, second.size_bytes)
    finally:
        repo.close()


def test_delete_oldest(tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        oldest = ClipItem.create(text="old", id="oldest", timestamp=1.0)
        newest = ClipItem.create(text="new", id="newest", timestamp=2.0)

        repo.insert(oldest)
        repo.insert(newest)

        assert repo.delete_oldest() == oldest.id
        assert repo.load_all() == [newest]
        assert repo.totals() == (1, newest.size_bytes)
    finally:
        repo.close()


def test_open_with_recovery_backs_up_corrupt_database_and_returns_empty_repo(tmp_path):
    path = tmp_path / "clipboard.db"
    path.write_bytes(b"not a sqlite database")

    repo = SQLiteRepository.open_with_recovery(path)
    try:
        assert repo.load_all() == []
        assert repo.totals() == (0, 0)
    finally:
        repo.close()

    backups = list(tmp_path.glob("clipboard.db.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"not a sqlite database"
