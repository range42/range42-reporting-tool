from app.schemas.common import ErrorBody, ErrorEnvelope


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
