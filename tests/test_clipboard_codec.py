from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage
from PySide6.QtCore import QMimeData

from src.clip_item import ClipItem
from src.clipboard_codec import ClipboardCodec


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
    item = ClipItem.create(
        text="plain text",
        html="<div>rich text</div>",
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
    item = ClipItem.create(
        text="plain text",
        html="<div>rich text</div>",
    )

    mime = ClipboardCodec.encode(item)

    assert mime.hasText()
    assert not mime.hasHtml()
    assert not mime.hasImage()
    assert bytes(mime.data("image/png")) == b""
