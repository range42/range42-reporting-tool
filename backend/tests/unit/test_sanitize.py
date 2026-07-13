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


def test_html_to_plain_strips_all_tags_and_collapses_ws() -> None:
    assert html_to_plain("<p>hello   <strong>world</strong></p>\n<p>two</p>") == "hello world two"


def test_html_to_plain_empty() -> None:
    assert html_to_plain("<p></p>") == ""
