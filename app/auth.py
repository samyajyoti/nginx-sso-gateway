import json
import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from passlib.context import CryptContext


PASSWORD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    users: dict[str, str]


def load_settings() -> Settings:
    cookie_domain = os.getenv("SSO_COOKIE_DOMAIN", ".wrtual.in").strip() or ".wrtual.in"
    auth_host = os.getenv("SSO_AUTH_HOST", f"auth.{cookie_domain.lstrip('.')}")

    return Settings(
        secret_key=os.getenv("SSO_SECRET_KEY", secrets.token_urlsafe(32)),
        cookie_name=os.getenv("SSO_COOKIE_NAME", "wrtual_sso"),
        cookie_domain=cookie_domain,
        cookie_secure=_get_bool_env("SSO_COOKIE_SECURE", default=True),
        cookie_same_site=os.getenv("SSO_COOKIE_SAMESITE", "lax"),
        session_max_age=int(os.getenv("SSO_SESSION_MAX_AGE", str(8 * 60 * 60))),
        auth_host=auth_host,
        default_redirect_url=os.getenv("SSO_DEFAULT_REDIRECT_URL", f"https://{auth_host}/"),
        allowed_email_domains=_get_allowed_email_domains(),
        users=_load_users_from_env(),
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


def _load_users_from_env() -> dict[str, str]:
    raw_value = os.getenv("SSO_USERS_JSON", "")
    if not raw_value.strip():
        return {}

    try:
        decoded: Any = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("SSO_USERS_JSON must be valid JSON.") from exc

    if not isinstance(decoded, dict):
        raise ValueError("SSO_USERS_JSON must decode to a JSON object.")

    users: dict[str, str] = {}
    for email, password_hash in decoded.items():
        if not isinstance(email, str) or not isinstance(password_hash, str):
            raise ValueError("SSO_USERS_JSON entries must map string emails to string password hashes.")
        users[email.strip().lower()] = password_hash.strip()

    return users


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_allowed_email(email: str, allowed_domains: tuple[str, ...]) -> bool:
    normalized = normalize_email(email)
    if "@" not in normalized:
        return False
    _, domain = normalized.rsplit("@", 1)
    return domain in allowed_domains


def validate_credentials(email: str, password: str, settings: Settings) -> tuple[bool, str | None]:
    normalized_email = normalize_email(email)

    if not is_allowed_email(normalized_email, settings.allowed_email_domains):
        joined_domains = ", ".join(f"@{domain}" for domain in settings.allowed_email_domains)
        return False, f"Use an approved company email address ({joined_domains})."

    if not settings.users:
        return False, "No users are configured yet. Set SSO_USERS_JSON before signing in."

    password_hash = settings.users.get(normalized_email)
    if not password_hash or not PASSWORD_CONTEXT.verify(password, password_hash):
        return False, "Invalid email or password."

    return True, None


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
