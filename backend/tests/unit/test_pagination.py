from app.core.pagination import PageParams


def test_offset_limit() -> None:
    p = PageParams(page=3, per_page=20)
    assert p.offset == 40
    assert p.limit == 20
