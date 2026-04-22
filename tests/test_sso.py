from fastapi.testclient import TestClient

from app.auth import Settings
from app.main import create_app


def build_settings(app_access: dict[str, tuple[str, ...]] | None = None) -> Settings:
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
        app_access=app_access or {},
    )


def _seed_session(client: TestClient, email: str) -> None:
    response = client.get("/_seed_session", params={"email": email})
    assert response.status_code == 200


def make_client_with_session(
    email: str | None,
    app_access: dict[str, tuple[str, ...]] | None = None,
) -> TestClient:
    app = create_app(build_settings(app_access=app_access))

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


def test_per_app_access_policy_allows_listed_user() -> None:
    policy = {
        "app1.wrtual.in": ("user1@datacultr.com",),
        "app2.wrtual.in": ("user1@datacultr.com", "user2@datacultr.com"),
    }
    client = make_client_with_session("user1@datacultr.com", app_access=policy)

    app1 = client.get(
        "https://test-sso.wrtual.in/auth/check",
        headers={"X-Forwarded-Host": "app1.wrtual.in"},
    )
    app2 = client.get(
        "https://test-sso.wrtual.in/auth/check",
        headers={"X-Forwarded-Host": "app2.wrtual.in"},
    )

    assert app1.status_code == 200
    assert app2.status_code == 200


def test_per_app_access_policy_blocks_unlisted_user() -> None:
    policy = {
        "app1.wrtual.in": ("user1@datacultr.com",),
        "app2.wrtual.in": ("user1@datacultr.com", "user2@datacultr.com"),
    }
    client = make_client_with_session("user2@datacultr.com", app_access=policy)

    blocked = client.get(
        "https://test-sso.wrtual.in/auth/check",
        headers={"X-Forwarded-Host": "app1.wrtual.in"},
    )
    allowed = client.get(
        "https://test-sso.wrtual.in/auth/check",
        headers={"X-Forwarded-Host": "app2.wrtual.in"},
    )

    assert blocked.status_code == 403
    assert allowed.status_code == 200


def test_per_app_access_policy_leaves_unlisted_hosts_open() -> None:
    policy = {"app1.wrtual.in": ("user1@datacultr.com",)}
    client = make_client_with_session("user2@datacultr.com", app_access=policy)

    response = client.get(
        "https://test-sso.wrtual.in/auth/check",
        headers={"X-Forwarded-Host": "app3.wrtual.in"},
    )

    assert response.status_code == 200
