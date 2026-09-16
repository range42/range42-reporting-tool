"""Log every demo persona in once, headlessly, so their user rows exist.

DEV ONLY: depends on Dex static passwords, which the prod overlay never runs.

Run INSIDE the backend container, BEFORE ``app.seed_grants``, which can only
grant roles to user rows that an SSO login has already created::

    docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml \
        exec -T backend uv run --no-sync python -m app.seed_logins

Drives the ordinary authorization-code flow over HTTP instead of a browser; the
backend still mints state + PKCE and exchanges the code itself.

Idempotent: an existing persona is logged in again, refreshing ``last_login_at``.
"""

import asyncio
import html
import re
from urllib.parse import parse_qs, urlsplit

import httpx

from app.seed_grants import GRANTS

# The backend talks to itself: this runs in its own container.
BACKEND_BASE_URL = "http://127.0.0.1:8000"
API_PREFIX = "/api/v1"

# Every Dex staticPasswords entry in deploy/dex/config.yaml shares this password.
DEV_PERSONA_PASSWORD = "changeme"

# Where Dex sends the browser once login succeeds; must match OIDC_REDIRECT_URI.
CALLBACK_URL_PREFIX = "http://localhost:5173/auth/callback"

REQUEST_TIMEOUT_SECONDS = 15.0
MAX_REDIRECT_HOPS = 10

_FORM_ACTION_PATTERN = re.compile(r"<form[^>]*\saction=\"([^\"]*)\"", re.IGNORECASE)


def parse_form_action(page_html: str) -> str:
    """The action URL of Dex's login form, as written in the page (may be relative)."""
    match = _FORM_ACTION_PATTERN.search(page_html)
    if match is None:
        raise RuntimeError("no <form action=...> in the Dex login page -- its markup may have changed in a Dex upgrade")
    return html.unescape(match.group(1))


def parse_code_and_state(callback_url: str) -> tuple[str, str]:
    """The ``code`` and ``state`` Dex put on the redirect back to the app."""
    query = parse_qs(urlsplit(callback_url).query)
    error = query.get("error", [None])[0]
    if error is not None:
        raise RuntimeError(f"Dex refused the login: {error}")
    code = query.get("code", [None])[0]
    state = query.get("state", [None])[0]
    if not code or not state:
        raise RuntimeError(f"no code/state on the callback redirect: {callback_url}")
    return code, state


async def _start_login(client: httpx.AsyncClient) -> str:
    """Ask the backend to begin a login; returns the IdP URL it redirects to."""
    response = await client.get(f"{BACKEND_BASE_URL}{API_PREFIX}/auth/login")
    if response.status_code != 302:
        raise RuntimeError(
            f"expected a redirect to the IdP, got HTTP {response.status_code} -- "
            "is the dev overlay up, with OIDC_ISSUER_URL set?"
        )
    location = str(response.headers.get("location", ""))
    if not location:
        raise RuntimeError("the backend's login redirect carried no Location header")
    return location


async def _submit_credentials(client: httpx.AsyncClient, authorize_url: str, email: str) -> str:
    """Fill in Dex's login form; returns the URL it finally redirects the app back to."""
    login_page = await client.get(authorize_url, follow_redirects=True)
    if login_page.status_code != 200:
        raise RuntimeError(f"Dex did not serve a login page: HTTP {login_page.status_code}")

    action_url = httpx.URL(str(login_page.url)).join(parse_form_action(login_page.text))
    response = await client.post(
        action_url,
        data={"login": email, "password": DEV_PERSONA_PASSWORD},
        follow_redirects=False,
    )

    # Walk the post-login hops until Dex hands control back to the app's redirect URI.
    for _ in range(MAX_REDIRECT_HOPS):
        if response.status_code == 200:
            raise RuntimeError(f"Dex rejected the credentials for {email} -- it re-served the login form")
        location = response.headers.get("location")
        if not location:
            raise RuntimeError(f"Dex stopped redirecting at HTTP {response.status_code} without a Location")
        next_url = str(httpx.URL(str(response.url)).join(location))
        if next_url.startswith(CALLBACK_URL_PREFIX):
            return next_url
        response = await client.get(next_url, follow_redirects=False)

    raise RuntimeError(f"Dex kept redirecting for more than {MAX_REDIRECT_HOPS} hops")


async def login_persona(email: str) -> None:
    """Drive one persona through the full authorization-code flow."""
    # A cookie jar per persona: the backend keys state + PKCE to the session cookie.
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False) as client:
        authorize_url = await _start_login(client)
        callback_url = await _submit_credentials(client, authorize_url, email)
        code, state = parse_code_and_state(callback_url)
        response = await client.get(
            f"{BACKEND_BASE_URL}{API_PREFIX}/auth/callback",
            params={"code": code, "state": state},
        )
        if response.status_code != 200:
            raise RuntimeError(f"the backend rejected {email}'s callback: HTTP {response.status_code} {response.text}")


async def _main() -> None:
    emails = tuple(grant.email for grant in GRANTS)
    failures: list[str] = []
    for email in emails:
        try:
            await login_persona(email)
        except (httpx.HTTPError, RuntimeError) as exc:
            failures.append(f"{email}: {exc}")
            print(f"login FAILED {email}: {exc}")
        else:
            print(f"logged in {email}")

    print(f"logins: {len(emails) - len(failures)}/{len(emails)} succeeded")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(_main())
