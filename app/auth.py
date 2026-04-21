import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    secret_key: str
    cookie_name: str
    cookie_domain: str
    cookie_secure: bool
    cookie_same_site: str
    session_max_age: int
    auth_host: str
    default_redirect_url: str
    allowed_email_domains: tuple[str, ...]
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_hosted_domain: str | None


def load_settings() -> Settings:
    cookie_domain = os.getenv("SSO_COOKIE_DOMAIN", ".wrtual.in").strip() or ".wrtual.in"
    auth_host = os.getenv("SSO_AUTH_HOST", f"auth.{cookie_domain.lstrip('.')}").strip()
    allowed_domains = _get_allowed_email_domains()
    hosted_domain = os.getenv("GOOGLE_HOSTED_DOMAIN", "").strip() or None
    if hosted_domain is None and len(allowed_domains) == 1:
        hosted_domain = allowed_domains[0]

    return Settings(
        secret_key=os.getenv("SSO_SECRET_KEY", secrets.token_urlsafe(32)),
        cookie_name=os.getenv("SSO_COOKIE_NAME", "wrtual_sso"),
        cookie_domain=cookie_domain,
        cookie_secure=_get_bool_env("SSO_COOKIE_SECURE", default=True),
        cookie_same_site=os.getenv("SSO_COOKIE_SAMESITE", "lax"),
        session_max_age=int(os.getenv("SSO_SESSION_MAX_AGE", str(8 * 60 * 60))),
        auth_host=auth_host,
        default_redirect_url=os.getenv("SSO_DEFAULT_REDIRECT_URL", f"https://{auth_host}/"),
        allowed_email_domains=allowed_domains,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        google_redirect_uri=os.getenv(
            "GOOGLE_REDIRECT_URI",
            f"https://{auth_host}/auth/google/callback",
        ).strip(),
        google_hosted_domain=hosted_domain,
    )


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_allowed_email_domains() -> tuple[str, ...]:
    raw_value = os.getenv("SSO_ALLOWED_EMAIL_DOMAINS", "datacultr.com")
    domains = [item.strip().lower() for item in raw_value.split(",") if item.strip()]
    return tuple(domains or ["datacultr.com"])


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_allowed_email(email: str, allowed_domains: tuple[str, ...]) -> bool:
    normalized = normalize_email(email)
    if "@" not in normalized:
        return False
    _, domain = normalized.rsplit("@", 1)
    return domain in allowed_domains


def sanitize_next_url(target: str | None, cookie_domain: str, default_redirect_url: str) -> str:
    if not target:
        return default_redirect_url

    parsed = urlparse(target)
    if not parsed.netloc:
        if target.startswith("/"):
            return target
        return default_redirect_url

    hostname = (parsed.hostname or "").lower()
    parent_domain = cookie_domain.lstrip(".").lower()
    if hostname == parent_domain or hostname.endswith(f".{parent_domain}"):
        return target

    return default_redirect_url


def get_session_email(session: dict[str, Any]) -> str | None:
    user = session.get("user")
    if not isinstance(user, dict):
        return None

    email = user.get("email")
    if not isinstance(email, str):
        return None

    return normalize_email(email)
