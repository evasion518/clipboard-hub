from PySide6.QtCore import QBuffer, QIODevice, QUrl
from PySide6.QtGui import QImage
from PySide6.QtCore import QMimeData

from src.clip_item import ClipItem
from src.clipboard_codec import ClipboardCodec


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    return bytes(buffer.data())


def test_decode_preserves_text_and_html_but_ignores_images(qapp):
    mime = QMimeData()
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xFF00FF00)

    mime.setText("hello")
    mime.setHtml("<p><b>hello</b></p>")
    mime.setImageData(image)

    item = ClipboardCodec.decode(
        mime,
        source_app="Chrome",
        source_window="Docs",
    )

    assert item is not None
    assert item.text == "hello"
    assert item.html == "<p><b>hello</b></p>"
    assert item.image_png is None
    assert item.image_size is None
    assert item.source_app == "Chrome"
    assert item.source_window == "Docs"


def test_encode_restores_only_plain_text(qapp):
    image = QImage(4, 1, QImage.Format.Format_ARGB32)
    image.fill(0xFFFF0000)
    png_bytes = _png_bytes(image)
    item = ClipItem.create(
        text="plain text",
        html="<div>rich text</div>",
        image_png=png_bytes,
        image_size=(4, 1),
    )

    mime = ClipboardCodec.encode(item)
    round_tripped = ClipboardCodec.decode(mime)

    assert mime.hasText()
    assert not mime.hasHtml()
    assert not mime.hasImage()
    assert mime.text() == "plain text"
    assert round_tripped is not None
    assert round_tripped.text == item.text
    assert round_tripped.html is None
    assert round_tripped.image_png is None
    assert round_tripped.image_size is None


def test_decode_returns_none_for_empty_mime_data(qapp):
    mime = QMimeData()

    assert ClipboardCodec.decode(mime) is None


def test_decode_returns_none_for_effectively_empty_text_and_html(qapp):
    mime = QMimeData()
    mime.setText("   ")
    mime.setHtml("")

    assert ClipboardCodec.decode(mime) is None


def test_image_to_png_returns_none_for_none_and_null_image(qapp):
    assert ClipboardCodec.image_to_png(None) is None
    assert ClipboardCodec.image_to_png(QImage()) is None


def test_decode_ignores_png_bytes_but_keeps_other_formats(qapp):
    mime = QMimeData()
    mime.setText("hello")
    mime.setHtml("<p>hello</p>")
    mime.setData("image/png", b"not-a-real-png")

    item = ClipboardCodec.decode(mime)

    assert item is not None
    assert item.text == "hello"
    assert item.html == "<p>hello</p>"
    assert item.image_png is None
    assert item.image_size is None


def test_decode_returns_none_for_image_only_clipboard(qapp):
    mime = QMimeData()
    image = QImage(5, 3, QImage.Format.Format_ARGB32)
    image.fill(0xFF224466)
    mime.setImageData(image)

    assert ClipboardCodec.decode(mime) is None


def test_image_to_png_enforces_max_image_bytes(qapp):
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(0xFF123456)
    original_limit = ClipboardCodec.MAX_IMAGE_BYTES
    ClipboardCodec.MAX_IMAGE_BYTES = 1
    try:
        assert ClipboardCodec.image_to_png(image) is None
    finally:
        ClipboardCodec.MAX_IMAGE_BYTES = original_limit


def test_decode_drops_oversized_png_payload_but_preserves_text_and_html(qapp):
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(0xFFABCDEF)
    png_bytes = _png_bytes(image)
    mime = QMimeData()
    mime.setText("plain")
    mime.setHtml("<b>plain</b>")
    mime.setData("image/png", png_bytes)

    original_limit = ClipboardCodec.MAX_IMAGE_BYTES
    ClipboardCodec.MAX_IMAGE_BYTES = len(png_bytes) - 1
    try:
        item = ClipboardCodec.decode(mime)
    finally:
        ClipboardCodec.MAX_IMAGE_BYTES = original_limit

    assert item is not None
    assert item.text == "plain"
    assert item.html == "<b>plain</b>"
    assert item.image_png is None
    assert item.image_size is None


def test_decode_file_urls_as_plain_text_paths(qapp):
    mime = QMimeData()
    mime.setUrls(
        [
            QUrl.fromLocalFile(r"C:\Users\Test\Desktop\a.txt"),
            QUrl.fromLocalFile(r"D:\Work\b.png"),
        ]
    )

    item = ClipboardCodec.decode(mime)

    assert item is not None
    assert item.text == "C:/Users/Test/Desktop/a.txt\nD:/Work/b.png"
    assert item.preview == "C:/Users/Test/Desktop/a.txt\nD:/Work/b.png"
    assert item.html is None
    assert item.image_png is None
    assert item.image_size is None


def test_decode_prefers_explicit_text_over_file_urls(qapp):
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(0xFF778899)
    mime = QMimeData()
    mime.setText("already text")
    mime.setUrls([QUrl.fromLocalFile(r"C:\Users\Test\Desktop\a.txt")])
    mime.setImageData(image)

    item = ClipboardCodec.decode(mime)

    assert item is not None
    assert item.text == "already text"
    assert item.image_png is None


def test_encode_skips_html_and_image_payloads(qapp):
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(0xFF445566)
    png_bytes = _png_bytes(image)
    item = ClipItem.create(
        text="plain text",
        html="<div>rich text</div>",
        image_png=png_bytes,
        image_size=(4, 4),
    )

    original_limit = ClipboardCodec.MAX_IMAGE_BYTES
    ClipboardCodec.MAX_IMAGE_BYTES = len(png_bytes) - 1
    try:
        mime = ClipboardCodec.encode(item)
    finally:
        ClipboardCodec.MAX_IMAGE_BYTES = original_limit

    assert mime.hasText()
    assert not mime.hasHtml()
    assert not mime.hasImage()
    assert bytes(mime.data("image/png")) == b""
