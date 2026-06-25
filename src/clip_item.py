import hashlib
import re
import time
import uuid
from dataclasses import dataclass
from html import unescape


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    text = unescape(text)
    return " ".join(text.split())


def _normalize_text(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    return text


def _normalize_html(html: str | None) -> str | None:
    if html is None or html == "":
        return None
    return html


def _normalize_image(image_png: bytes | None) -> bytes | None:
    if not image_png:
        return None
    return image_png


def _normalize_payloads(
    *,
    text: str | None = None,
    html: str | None = None,
    image_png: bytes | None = None,
) -> tuple[str | None, str | None, bytes | None]:
    return _normalize_text(text), _normalize_html(html), _normalize_image(image_png)


def build_preview(
    *,
    text: str | None = None,
    html: str | None = None,
    image_png: bytes | None = None,
    image_size: tuple[int, int] | None = None,
) -> str:
    if text and text.strip():
        return text.strip()
    if html and strip_html(html):
        return strip_html(html)
    if image_png:
        if image_size is not None:
            width, height = image_size
            return f"[Image {width}x{height}]"
        return "[Image]"
    return ""


def _has_meaningful_payload(*, text: str | None = None, html: str | None = None, image_png: bytes | None = None) -> bool:
    return any(value is not None for value in _normalize_payloads(text=text, html=html, image_png=image_png))


def _iter_present_payloads(*, text: str | None = None, html: str | None = None, image_png: bytes | None = None):
    text, html, image_png = _normalize_payloads(text=text, html=html, image_png=image_png)
    if text is not None:
        yield "text", text.encode("utf-8")
    if html is not None:
        yield "html", html.encode("utf-8")
    if image_png is not None:
        yield "image", image_png


def _hash_payloads(*, text: str | None = None, html: str | None = None, image_png: bytes | None = None) -> str:
    raw = b"\x00".join(label.encode("utf-8") + b":" + payload for label, payload in _iter_present_payloads(text=text, html=html, image_png=image_png))
    return hashlib.sha256(raw).hexdigest()


def _payload_size(*, text: str | None = None, html: str | None = None, image_png: bytes | None = None) -> int:
    return sum(len(payload) for _, payload in _iter_present_payloads(text=text, html=html, image_png=image_png))


@dataclass(frozen=True, init=False)
class ClipItem:
    text: str | None
    html: str | None
    image_png: bytes | None
    image_size: tuple[int, int] | None
    preview: str
    source_app: str
    source_window: str | None
    id: str
    timestamp: float
    content_hash: str
    size_bytes: int

    def __init__(
        self,
        *,
        text: str | None = None,
        html: str | None = None,
        image_png: bytes | None = None,
        image_size: tuple[int, int] | None = None,
        preview: str | None = None,
        source_app: str = "unknown",
        source_window: str | None = None,
        id: str | None = None,
        timestamp: float | None = None,
        content_hash: str | None = None,
        size_bytes: int | None = None,
    ):
        text, html, image_png = _normalize_payloads(text=text, html=html, image_png=image_png)

        if not _has_meaningful_payload(text=text, html=html, image_png=image_png):
            raise ValueError("clip item requires content")

        object.__setattr__(self, "text", text)
        object.__setattr__(self, "html", html)
        object.__setattr__(self, "image_png", image_png)
        object.__setattr__(self, "image_size", image_size)
        object.__setattr__(self, "preview", preview if preview is not None else build_preview(text=text, html=html, image_png=image_png, image_size=image_size))
        object.__setattr__(self, "source_app", source_app)
        object.__setattr__(self, "source_window", source_window)
        object.__setattr__(self, "id", id or str(uuid.uuid4()))
        object.__setattr__(self, "timestamp", time.time() if timestamp is None else timestamp)
        object.__setattr__(self, "content_hash", content_hash or _hash_payloads(text=text, html=html, image_png=image_png))
        object.__setattr__(self, "size_bytes", _payload_size(text=text, html=html, image_png=image_png) if size_bytes is None else size_bytes)

    @classmethod
    def create(
        cls,
        *,
        text: str | None = None,
        html: str | None = None,
        image_png: bytes | None = None,
        image_size: tuple[int, int] | None = None,
        preview: str | None = None,
        source_app: str = "unknown",
        source_window: str | None = None,
        id: str | None = None,
        timestamp: float | None = None,
    ) -> "ClipItem":
        return cls(
            text=text,
            html=html,
            image_png=image_png,
            image_size=image_size,
            preview=preview,
            source_app=source_app,
            source_window=source_window,
            id=id,
            timestamp=timestamp,
        )
