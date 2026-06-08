from app.core.sanitize_policy import ALLOWED_ATTRS, ALLOWED_TAGS


def test_allowed_tags_non_empty_and_covers_core() -> None:
    assert ALLOWED_TAGS
    assert "table" in ALLOWED_TAGS
    assert "code" in ALLOWED_TAGS
    assert "img" in ALLOWED_TAGS


def test_allowed_attrs_non_empty() -> None:
    assert ALLOWED_ATTRS
    assert "href" in ALLOWED_ATTRS["a"]
    assert "src" in ALLOWED_ATTRS["img"]
