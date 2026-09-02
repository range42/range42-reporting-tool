import json
from decimal import Decimal

from app.core.errors import _sanitize_errors
from app.schemas.common import ErrorBody, ErrorEnvelope


def test_sanitize_handles_exception_nested_in_list() -> None:
    """An Exception nested inside a list must be stringified, not returned raw."""
    raw = [
        {
            "type": "x",
            "loc": ["body", "f"],
            "msg": "bad",
            "ctx": {"error": ValueError("boom")},
            "extras": [ValueError("nested-in-list")],
        }
    ]
    cleaned = _sanitize_errors(raw)
    # Must not raise — result must be fully JSON-serialisable
    json.dumps(cleaned)
    # Dict-nested exception becomes str (existing path)
    assert cleaned[0]["ctx"]["error"] == "boom"  # type: ignore[index]
    # List-nested exception becomes str (new path under test)
    assert cleaned[0]["extras"] == ["nested-in-list"]  # type: ignore[index]


def test_error_envelope_shape() -> None:
    env = ErrorEnvelope(
        error=ErrorBody(code="VALIDATION_ERROR", message="bad", details=[]),
        trace_id="abc123",
    )
    dumped = env.model_dump()
    assert dumped["error"]["code"] == "VALIDATION_ERROR"
    assert dumped["error"]["message"] == "bad"
    assert dumped["trace_id"] == "abc123"


def test_trace_id_optional() -> None:
    env = ErrorEnvelope(error=ErrorBody(code="X", message="y"))
    assert env.model_dump()["trace_id"] is None


def test_sanitize_stringifies_decimal_constraint_bounds() -> None:
    """Pydantic echoes a Decimal field's ``ge``/``le`` bound into ``ctx`` as a Decimal, which
    ``json`` cannot encode. The 422 handler must survive a rejected Decimal body."""
    raw = [{"type": "greater_than_equal", "loc": ["body", "overall_grade"], "msg": "bad", "ctx": {"ge": Decimal("0")}}]
    cleaned = _sanitize_errors(raw)
    json.dumps(cleaned)
    assert cleaned[0]["ctx"]["ge"] == "0"  # type: ignore[index]
