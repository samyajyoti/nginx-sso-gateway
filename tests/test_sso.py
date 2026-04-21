from fastapi.testclient import TestClient

from app.auth import PASSWORD_CONTEXT, Settings
from app.main import create_app


def build_settings() -> Settings:
    return Settings(
        secret_key="test-secret",
        cookie_name="wrtual_sso",
        cookie_domain=".wrtual.in",
        cookie_secure=True,
        cookie_same_site="lax",
        session_max_age=3600,
        auth_host="auth.wrtual.in",
        default_redirect_url="https://auth.wrtual.in/",
        allowed_email_domains=("datacultr.com",),
        users={
            "user@datacultr.com": PASSWORD_CONTEXT.hash("correct horse battery staple"),
        },
    )


def test_rejects_email_outside_allowed_domain() -> None:
    client = TestClient(create_app(build_settings()), base_url="https://auth.wrtual.in")

    response = client.post(
        "/login",
        data={
            "email": "user@example.com",
            "password": "correct horse battery staple",
            "next": "https://app1.wrtual.in/dashboard",
        },
    )

    assert response.status_code == 401
    assert "approved company email address" in response.text


def test_single_sign_on_cookie_works_across_subdomains() -> None:
    client = TestClient(create_app(build_settings()), base_url="https://auth.wrtual.in")

    first_check = client.get("https://app1.wrtual.in/auth/check")
    assert first_check.status_code == 401

    login_response = client.post(
        "/login",
        data={
            "email": "user@datacultr.com",
            "password": "correct horse battery staple",
            "next": "https://app1.wrtual.in/dashboard",
        },
        follow_redirects=False,
    )

    assert login_response.status_code == 302
    assert login_response.headers["location"] == "https://app1.wrtual.in/dashboard"

    app1_response = client.get("https://app1.wrtual.in/auth/check")
    app2_response = client.get("https://app2.wrtual.in/auth/check")

    assert app1_response.status_code == 200
    assert app2_response.status_code == 200
    assert app1_response.headers["x-authenticated-email"] == "user@datacultr.com"
    assert app2_response.headers["x-authenticated-email"] == "user@datacultr.com"


def test_logout_clears_session() -> None:
    client = TestClient(create_app(build_settings()), base_url="https://auth.wrtual.in")

    client.post(
        "/login",
        data={
            "email": "user@datacultr.com",
            "password": "correct horse battery staple",
            "next": "https://app1.wrtual.in/dashboard",
        },
        follow_redirects=False,
    )

    logout_response = client.get("/logout", follow_redirects=False)
    assert logout_response.status_code == 302

    auth_response = client.get("https://app2.wrtual.in/auth/check")
    assert auth_response.status_code == 401
