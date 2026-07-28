import pytest

from app.core.sanitize import html_to_plain, sanitize_html


def test_sanitize_strips_script_keeps_formatting() -> None:
    out = sanitize_html("<p>hi <strong>bold</strong></p><script>alert(1)</script>")
    assert "<script>" not in out
    assert "<strong>bold</strong>" in out
    assert "alert(1)" not in out  # script body removed, not just tags


def test_sanitize_drops_event_handlers_and_js_href() -> None:
    out = sanitize_html('<a href="javascript:evil()" onclick="x()">l</a>')
    assert "onclick" not in out
    assert "javascript:" not in out


_OWN_SRC = "/api/v1/exercises/e1/reports/r1/attachments/a1/download"


def test_sanitize_keeps_img_pointing_at_own_attachment_download() -> None:
    out = sanitize_html(f'<img src="{_OWN_SRC}" alt="x">')
    assert f'src="{_OWN_SRC}"' in out
    assert 'alt="x"' in out


@pytest.mark.parametrize(
    "src",
    [
        "https://evil.example/x.png",  # external — exfiltration/tracking vector
        "http://evil.example/x.png",
        "//evil.example/x.png",  # protocol-relative
        "data:image/png;base64,AAAA",  # inline payload smuggling
        "javascript:alert(1)",
        "/api/v1/exercises/e1/reports/r1/attachments/../../../secrets",  # traversal
        "/etc/passwd",
        "api/v1/exercises/e1/reports/r1/attachments/a1/download",  # not root-relative
    ],
)
def test_sanitize_drops_img_src_outside_attachment_path(src: str) -> None:
    out = sanitize_html(f'<img src="{src}" alt="x">')
    assert src not in out
    assert "evil.example" not in out


def test_html_to_plain_strips_all_tags_and_collapses_ws() -> None:
    assert html_to_plain("<p>hello   <strong>world</strong></p>\n<p>two</p>") == "hello world two"


def test_html_to_plain_empty() -> None:
    assert html_to_plain("<p></p>") == ""
