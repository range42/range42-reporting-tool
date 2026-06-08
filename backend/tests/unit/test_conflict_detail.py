from app.schemas.common import ConflictDetail


def test_conflict_detail_serializes_full() -> None:
    cd = ConflictDetail(
        current_version=3,
        current_content="latest body",
        current_choice_values=["a", "b"],
    )
    dumped = cd.model_dump()
    assert dumped["current_version"] == 3
    assert dumped["current_content"] == "latest body"
    assert dumped["current_choice_values"] == ["a", "b"]


def test_conflict_detail_optional_fields_default_none() -> None:
    cd = ConflictDetail(current_version=1)
    dumped = cd.model_dump()
    assert dumped["current_content"] is None
    assert dumped["current_choice_values"] is None
