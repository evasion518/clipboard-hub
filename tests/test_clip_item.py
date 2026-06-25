import hashlib

import pytest

from src.clip_item import ClipItem, build_preview


def test_create_accepts_image_size_id_timestamp_and_computes_aggregate_fields():
    item = ClipItem.create(
        text="hello",
        html="<b>x</b>",
        image_png=b"\x89PNG",
        image_size=(320, 200),
        id="clip-1",
        timestamp=123.45,
    )

    expected_hash = hashlib.sha256(
        b"text:hello\x00html:<b>x</b>\x00image:\x89PNG"
    ).hexdigest()

    assert item.id == "clip-1"
    assert item.timestamp == 123.45
    assert item.image_size == (320, 200)
    assert item.size_bytes == (
        len("hello".encode("utf-8"))
        + len("<b>x</b>".encode("utf-8"))
        + len(b"\x89PNG")
    )
    assert item.content_hash == expected_hash


def test_build_preview_prefers_text_then_html_plain_text_then_image_label_with_dimensions():
    assert build_preview(text="  hello world  ") == "hello world"
    assert build_preview(html="<p>Hello <b>world</b></p>") == "Hello world"
    assert build_preview(image_png=b"\x89PNG\r\n\x1a\n") == "[Image]"
    assert build_preview(image_png=b"\x89PNG\r\n\x1a\n", image_size=(640, 480)) == "[Image 640x480]"


@pytest.mark.parametrize("html", ["<img src='x'>", "<div></div>"])
def test_create_accepts_non_empty_html_even_when_plain_text_preview_is_empty(html):
    item = ClipItem.create(html=html)

    assert item.html == html
    assert item.size_bytes == len(html.encode("utf-8"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"text": ""},
        {"html": ""},
        {"image_png": b""},
        {"text": "", "html": "", "image_png": b""},
    ],
)
def test_create_without_non_empty_payload_raises_value_error(kwargs):
    with pytest.raises(ValueError, match="clip item requires content"):
        ClipItem.create(**kwargs)


def test_create_skips_empty_leading_payloads():
    item = ClipItem.create(text="   ", html="<b>fallback</b>")

    assert item.text is None
    assert item.html == "<b>fallback</b>"


def test_empty_present_fields_do_not_change_identity():
    base = ClipItem.create(text="hello")
    with_empty_fields = ClipItem.create(text="hello", html="", image_png=b"")

    assert with_empty_fields.text == "hello"
    assert with_empty_fields.html is None
    assert with_empty_fields.size_bytes == base.size_bytes
    assert with_empty_fields.content_hash == base.content_hash
