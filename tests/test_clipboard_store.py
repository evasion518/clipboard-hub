import inspect

from PySide6.QtTest import QSignalSpy
from src.clipboard_store import ClipboardStore, ClipItem
from src.sqlite_repository import SQLiteRepository


def test_add_and_get_all(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="hello", preview="hello")
    store.add(item)
    items = store.get_all()
    assert len(items) == 1
    assert items[0].text == "hello"


def test_deduplicate_same_content(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="same", preview="same"))
    store.add(ClipItem.create(text="same", preview="same"))
    assert len(store.get_all()) == 1


def test_different_content_adds_both(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="a", preview="a"))
    store.add(ClipItem.create(text="b", preview="b"))
    assert len(store.get_all()) == 2
    assert store.get_all()[0].text == "b"


def test_delete(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="del", preview="del")
    store.add(item)
    store.delete(item.id)
    assert len(store.get_all()) == 0


def test_clear_removes_all_items_and_emits_once(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        store = ClipboardStore(repository=repo)
        store.add(ClipItem.create(text="a", id="first", timestamp=1.0))
        store.add(ClipItem.create(text="bb", id="second", timestamp=2.0))
        spy = QSignalSpy(store.items_changed)

        assert store.clear() is True

        assert store.get_all() == []
        assert repo.load_all() == []
        assert spy.count() == 1
    finally:
        repo.close()


def test_delete_nonexistent_does_not_crash(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="x", preview="x"))
    store.delete("nonexistent-id")
    assert len(store.get_all()) == 1


def test_search(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="apple pie", preview="apple pie"))
    store.add(ClipItem.create(text="banana", preview="banana"))
    store.add(ClipItem.create(html="<div>apple</div>", preview="<div>apple</div>"))
    results = store.search("apple")
    assert len(results) == 2
    results = store.search("banana")
    assert len(results) == 1
    results = store.search("xyz")
    assert len(results) == 0


def test_deduplicate_uses_v2_identity_not_legacy_content_only(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="same text", html="<b>one</b>"))
    store.add(ClipItem.create(text="same text", html="<b>two</b>"))

    assert len(store.get_all()) == 2


def test_deduplicate_treats_empty_present_fields_as_same_identity(qapp):
    store = ClipboardStore()
    store.add(ClipItem.create(text="same text"))
    store.add(ClipItem.create(text="same text", html="", image_png=b""))

    assert len(store.get_all()) == 1


def test_store_loads_existing_items_from_repository(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        older = ClipItem.create(text="older", id="older", timestamp=1.0)
        newer = ClipItem.create(text="newer", id="newer", timestamp=2.0)
        repo.insert(older)
        repo.insert(newer)

        store = ClipboardStore(repository=repo)

        assert store.get_all() == [newer, older]
    finally:
        repo.close()


def test_init_signature_matches_v2_contract():
    parameters = list(inspect.signature(ClipboardStore.__init__).parameters.values())

    assert [parameter.name for parameter in parameters] == [
        "self",
        "repository",
        "max_items",
        "max_bytes",
        "parent",
    ]


def test_add_and_delete_persist_through_repository(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        store = ClipboardStore(repository=repo)
        item = ClipItem.create(text="persist me", id="persisted", timestamp=3.0)

        assert store.add(item) is True
        assert repo.load_all() == [item]

        assert store.delete(item.id) is True
        assert repo.load_all() == []
    finally:
        repo.close()


def test_consecutive_duplicate_content_hash_is_skipped(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        store = ClipboardStore(repository=repo)
        first = ClipItem.create(text="same text", id="first", timestamp=1.0)
        duplicate = ClipItem.create(text="same text", id="duplicate", timestamp=2.0)
        spy = QSignalSpy(store.items_changed)

        assert store.add(first) is True
        assert store.add(duplicate) is False

        assert store.get_all() == [first]
        assert repo.load_all() == [first]
        assert spy.count() == 1
    finally:
        repo.close()


def test_evicts_oldest_item_when_max_items_exceeded(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        store = ClipboardStore(repository=repo, max_items=2)
        oldest = ClipItem.create(text="oldest", id="oldest", timestamp=1.0)
        middle = ClipItem.create(text="middle", id="middle", timestamp=2.0)
        newest = ClipItem.create(text="newest", id="newest", timestamp=3.0)

        assert store.add(oldest) is True
        assert store.add(middle) is True
        assert store.add(newest) is True

        assert store.get_all() == [newest, middle]
        assert repo.load_all() == [newest, middle]
    finally:
        repo.close()


def test_evicts_oldest_items_when_max_bytes_exceeded(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        first = ClipItem.create(text="12345", id="first", timestamp=1.0)
        second = ClipItem.create(text="67890", id="second", timestamp=2.0)
        third = ClipItem.create(text="abcde", id="third", timestamp=3.0)
        store = ClipboardStore(repository=repo, max_bytes=first.size_bytes + second.size_bytes)

        assert store.add(first) is True
        assert store.add(second) is True
        assert store.add(third) is True

        assert store.get_all() == [third, second]
        assert repo.load_all() == [third, second]
    finally:
        repo.close()


def test_oversized_single_item_add_returns_false_and_keeps_existing_history(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        keep = ClipItem.create(text="keep", id="keep", timestamp=1.0)
        too_large = ClipItem.create(text="toolarge", id="too-large", timestamp=2.0)
        store = ClipboardStore(repository=repo, max_bytes=too_large.size_bytes - 1)
        spy = QSignalSpy(store.items_changed)

        assert store.add(keep) is True
        assert spy.count() == 1

        assert store.add(too_large) is False
        assert spy.count() == 1
        assert store.get_all() == [keep]
        assert repo.load_all() == [keep]
    finally:
        repo.close()


def test_startup_load_enforces_max_items(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        oldest = ClipItem.create(text="oldest", id="oldest", timestamp=1.0)
        middle = ClipItem.create(text="middle", id="middle", timestamp=2.0)
        newest = ClipItem.create(text="newest", id="newest", timestamp=3.0)
        repo.insert(oldest)
        repo.insert(middle)
        repo.insert(newest)

        store = ClipboardStore(repository=repo, max_items=2)

        assert store.get_all() == [newest, middle]
        assert repo.load_all() == [newest, middle]
    finally:
        repo.close()


def test_startup_load_enforces_max_bytes(qapp, tmp_path):
    repo = SQLiteRepository(tmp_path / "clipboard.db")
    try:
        first = ClipItem.create(text="12345", id="first", timestamp=1.0)
        second = ClipItem.create(text="67890", id="second", timestamp=2.0)
        third = ClipItem.create(text="abcde", id="third", timestamp=3.0)
        repo.insert(first)
        repo.insert(second)
        repo.insert(third)

        store = ClipboardStore(repository=repo, max_bytes=second.size_bytes + third.size_bytes)

        assert store.get_all() == [third, second]
        assert repo.load_all() == [third, second]
    finally:
        repo.close()


def test_search_includes_html_plain_preview_and_source_metadata(qapp):
    store = ClipboardStore()
    html_item = ClipItem.create(
        html="<p>Hello <b>world</b></p>",
        preview="Markup preview",
        source_app="chrome.exe",
        source_window="Documentation Tab",
    )
    text_item = ClipItem.create(
        text="plain body",
        preview="Visible Preview",
        source_app="notepad.exe",
        source_window="Notes",
    )
    store.add(html_item)
    store.add(text_item)

    assert store.search("world") == [html_item]
    assert store.search("markup preview") == [html_item]
    assert store.search("chrome.exe") == [html_item]
    assert store.search("documentation tab") == [html_item]
    assert store.search("visible preview") == [text_item]
    assert store.search("notes") == [text_item]


def test_delete_emits_only_when_item_existed(qapp):
    store = ClipboardStore()
    item = ClipItem.create(text="x", id="item-1")
    store.add(item)
    spy = QSignalSpy(store.items_changed)

    assert store.delete(item.id) is True
    assert spy.count() == 1

    assert store.delete(item.id) is False
    assert spy.count() == 1


def test_items_changed_signal(qapp):
    store = ClipboardStore()
    spy = QSignalSpy(store.items_changed)
    assert store.add(ClipItem.create(text="x", preview="x")) is True
    assert spy.count() == 1
