from PySide6.QtCore import QMimeData

from src.clip_item import ClipItem, strip_html


class ClipboardCodec:
    @staticmethod
    def decode(
        mime: QMimeData,
        source_app: str = "unknown",
        source_window: str | None = None,
    ) -> ClipItem | None:
        text = ClipboardCodec._text_from_mime(mime)
        html = mime.html() if mime.hasHtml() and mime.html() != "" else None
        if text is None and html is None:
            return None

        return ClipItem.create(
            text=text,
            html=html,
            source_app=source_app,
            source_window=source_window,
        )

    @staticmethod
    def encode(item: ClipItem) -> QMimeData:
        mime = QMimeData()
        text = ClipboardCodec.copy_text_for_item(item)
        if text is not None:
            mime.setText(text)
        return mime

    @staticmethod
    def copy_text_for_item(item: ClipItem) -> str | None:
        if item.text is not None:
            return item.text
        if item.html is not None:
            stripped = strip_html(item.html)
            return stripped or item.preview or None
        return item.preview or None

    @staticmethod
    def self_copy_hash(item: ClipItem) -> str | None:
        text = ClipboardCodec.copy_text_for_item(item)
        if text is None or not text.strip():
            return None
        return ClipItem.create(text=text).content_hash

    @staticmethod
    def _text_from_mime(mime: QMimeData) -> str | None:
        if mime.hasText() and mime.text().strip():
            text = mime.text().strip()
            if not ClipboardCodec._looks_like_url_list(text):
                return text
        if mime.hasUrls():
            paths = [
                url.toLocalFile().replace("\\", "/")
                for url in mime.urls()
                if url.isLocalFile() and url.toLocalFile()
            ]
            if paths:
                return "\n".join(paths)
        if mime.hasText() and mime.text().strip():
            return mime.text().strip()
        return None

    @staticmethod
    def _looks_like_url_list(text: str) -> bool:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return bool(lines) and all(line.startswith("file:") for line in lines)
