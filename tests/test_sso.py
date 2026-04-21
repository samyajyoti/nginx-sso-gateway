from fastapi.testclient import TestClient

from app.auth import Settings
from app.main import create_app


def build_settings() -> Settings:
    return Settings(
        secret_key="test-secret",
        cookie_name="wrtual_sso",
        cookie_domain=".wrtual.in",
        cookie_secure=True,
        cookie_same_site="lax",
        session_max_age=3600,
        auth_host="test-sso.wrtual.in",
        default_redirect_url="https://test-sso.wrtual.in/",
        allowed_email_domains=("datacultr.com",),
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
        google_redirect_uri="https://test-sso.wrtual.in/auth/google/callback",
        google_hosted_domain="datacultr.com",
    )


def _seed_session(client: TestClient, email: str) -> None:
    response = client.get("/_seed_session", params={"email": email})
    assert response.status_code == 200


def make_client_with_session(email: str | None) -> TestClient:
    app = create_app(build_settings())

    @app.get("/_seed_session")
    async def seed_session(request, email: str = "") -> dict[str, str]:
        if email:
            request.session["user"] = {"email": email}
        else:
            request.session.clear()
        return {"status": "ok"}

    client = TestClient(app, base_url="https://test-sso.wrtual.in")
    if email:
        _seed_session(client, email)
    return client


def test_unauthenticated_request_is_rejected_by_auth_check() -> None:
    client = make_client_with_session(None)

    response = client.get("https://app1.wrtual.in/auth/check")

    assert response.status_code == 401


def test_authenticated_session_is_shared_across_subdomains() -> None:
    client = make_client_with_session("user@datacultr.com")

    app1 = client.get("https://app1.wrtual.in/auth/check")
    app2 = client.get("https://app2.wrtual.in/auth/check")

    assert app1.status_code == 200
    assert app2.status_code == 200
    assert app1.headers["x-authenticated-email"] == "user@datacultr.com"
    assert app2.headers["x-authenticated-email"] == "user@datacultr.com"


def test_session_with_disallowed_domain_is_rejected() -> None:
    client = make_client_with_session("intruder@example.com")

    response = client.get("https://app1.wrtual.in/auth/check")

    assert response.status_code == 401


def test_logout_clears_session_for_other_apps() -> None:
    client = make_client_with_session("user@datacultr.com")

    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code == 302

    auth_response = client.get("https://app2.wrtual.in/auth/check")
    assert auth_response.status_code == 401


def test_login_page_renders_google_button() -> None:
    client = make_client_with_session(None)

    response = client.get("/login")

    assert response.status_code == 200
    assert "Sign in with Google" in response.text
