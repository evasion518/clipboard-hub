from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .clip_item import ClipItem


SCHEMA = """
CREATE TABLE IF NOT EXISTS clipboard_items (
    id TEXT PRIMARY KEY,
    text_content TEXT,
    html_content TEXT,
    image_png BLOB,
    image_width INTEGER,
    image_height INTEGER,
    preview TEXT NOT NULL,
    created_at REAL NOT NULL,
    source_app TEXT NOT NULL DEFAULT 'unknown',
    source_window TEXT,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clipboard_items_created_at
ON clipboard_items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clipboard_items_content_hash
ON clipboard_items(content_hash);
"""


class SQLiteRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = None
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)
            connection.commit()
        except Exception:
            connection.close()
            raise
        self._connection = connection

    @classmethod
    def open_with_recovery(cls, path: str | Path) -> "SQLiteRepository":
        db_path = Path(path)
        try:
            return cls(db_path)
        except sqlite3.DatabaseError:
            backup_path = db_path.with_name(f"{db_path.name}.corrupt-{_timestamp_suffix()}")
            if db_path.exists():
                db_path.replace(backup_path)
            return cls(db_path)

    def insert(self, item: ClipItem) -> None:
        image_width, image_height = _split_image_size(item.image_size)
        with self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO clipboard_items (
                    id,
                    text_content,
                    html_content,
                    image_png,
                    image_width,
                    image_height,
                    preview,
                    created_at,
                    source_app,
                    source_window,
                    content_hash,
                    size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.text,
                    item.html,
                    item.image_png,
                    image_width,
                    image_height,
                    item.preview,
                    item.timestamp,
                    item.source_app,
                    item.source_window,
                    item.content_hash,
                    item.size_bytes,
                ),
            )

    def delete(self, item_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM clipboard_items WHERE id = ?",
                (item_id,),
            )
        return cursor.rowcount > 0

    def delete_oldest(self) -> str | None:
        row = self._connection.execute(
            """
            SELECT id
            FROM clipboard_items
            ORDER BY created_at ASC, rowid ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        self.delete(row[0])
        return str(row[0])

    def load_all(self) -> list[ClipItem]:
        rows = self._connection.execute(
            """
            SELECT
                id,
                text_content,
                html_content,
                image_png,
                image_width,
                image_height,
                preview,
                created_at,
                source_app,
                source_window,
                content_hash,
                size_bytes
            FROM clipboard_items
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
        return [
            ClipItem(
                id=row[0],
                text=row[1],
                html=row[2],
                image_png=row[3],
                image_size=_join_image_size(row[4], row[5]),
                preview=row[6],
                timestamp=row[7],
                source_app=row[8],
                source_window=row[9],
                content_hash=row[10],
                size_bytes=row[11],
            )
            for row in rows
        ]

    def totals(self) -> tuple[int, int]:
        count, size_bytes = self._connection.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(size_bytes), 0)
            FROM clipboard_items
            """
        ).fetchone()
        return int(count), int(size_bytes)

    def checkpoint(self) -> None:
        self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def _split_image_size(image_size: tuple[int, int] | None) -> tuple[int | None, int | None]:
    if image_size is None:
        return None, None
    return image_size


def _join_image_size(width: int | None, height: int | None) -> tuple[int, int] | None:
    if width is None or height is None:
        return None
    return int(width), int(height)


def _timestamp_suffix() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")
