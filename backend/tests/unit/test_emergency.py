import bcrypt

from app.auth.emergency import emergency_claims, verify_emergency_password


def test_emergency_claims_shape() -> None:
    c = emergency_claims()
    assert c.provider == "emergency"
    assert c.subject == "admin"
    assert c.email and c.display_name


def test_verify_correct_password() -> None:
    h = bcrypt.hashpw(b"correct horse battery staple", bcrypt.gensalt()).decode()
    assert verify_emergency_password("correct horse battery staple", h) is True


def test_verify_wrong_password() -> None:
    h = bcrypt.hashpw(b"correct horse battery staple", bcrypt.gensalt()).decode()
    assert verify_emergency_password("guess", h) is False


def test_verify_empty_hash_is_false() -> None:
    assert verify_emergency_password("anything", "") is False
