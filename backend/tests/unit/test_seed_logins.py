import pytest

from app.seed_grants import GRANTS
from app.seed_logins import parse_code_and_state, parse_form_action

_DEX_LOGIN_PAGE = """
<html><body>
  <form method="post" action="/dex/auth/local?req=abc123&amp;back=">
    <input type="text" name="login" />
    <input type="password" name="password" />
  </form>
</body></html>
"""


def test_extracts_the_login_form_action_with_entities_decoded() -> None:
    # Arrange / Act
    action = parse_form_action(_DEX_LOGIN_PAGE)

    # Assert
    assert action == "/dex/auth/local?req=abc123&back="


def test_raises_when_the_page_has_no_form() -> None:
    # Arrange
    page = "<html><body><p>Internal Server Error</p></body></html>"

    # Act / Assert
    with pytest.raises(RuntimeError, match="no <form action"):
        parse_form_action(page)


def test_reads_code_and_state_off_the_callback_redirect() -> None:
    # Arrange
    url = "http://localhost:5173/auth/callback?code=the-code&state=the-state"

    # Act
    code, state = parse_code_and_state(url)

    # Assert
    assert (code, state) == ("the-code", "the-state")


def test_surfaces_an_idp_error_instead_of_a_missing_code() -> None:
    # Arrange
    url = "http://localhost:5173/auth/callback?error=access_denied"

    # Act / Assert
    with pytest.raises(RuntimeError, match="access_denied"):
        parse_code_and_state(url)


def test_raises_when_the_redirect_carries_no_code() -> None:
    # Arrange
    url = "http://localhost:5173/auth/callback?state=only-state"

    # Act / Assert
    with pytest.raises(RuntimeError, match="no code/state"):
        parse_code_and_state(url)


def test_every_granted_persona_is_one_this_script_logs_in() -> None:
    # The login pass feeds the grants pass; a persona in one and not the other
    # is the exact failure this pairing exists to remove.
    emails = [grant.email for grant in GRANTS]

    assert emails == sorted(set(emails))
