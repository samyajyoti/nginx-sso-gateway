import json
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
    app_access: dict[str, tuple[str, ...]]


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
        app_access=_load_app_access_from_env(),
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


def _load_app_access_from_env() -> dict[str, tuple[str, ...]]:
    """Load the per-app access policy from env vars.

    Two formats are supported. Use whichever is easier:

    1. Simple form (recommended) using `SSO_APP_ACCESS`:

       SSO_APP_ACCESS=app1.wrtual.in=user1@datacultr.com; app2.wrtual.in=user1@datacultr.com, user2@datacultr.com

       Each entry is `host=user1,user2,...` separated by `;` or newlines.
       Use `*` as the user list to allow every signed-in allowed-domain user.

    2. JSON form using `SSO_APP_ACCESS_JSON` for programmatic configuration.
    """

    simple_value = os.getenv("SSO_APP_ACCESS", "").strip()
    if simple_value:
        return _parse_app_access_simple(simple_value)

    raw_value = os.getenv("SSO_APP_ACCESS_JSON", "").strip()
    if not raw_value:
        return {}

    try:
        decoded: Any = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError("SSO_APP_ACCESS_JSON must be valid JSON.") from exc

    if not isinstance(decoded, dict):
        raise ValueError("SSO_APP_ACCESS_JSON must decode to a JSON object.")

    result: dict[str, tuple[str, ...]] = {}
    for host, users in decoded.items():
        if not isinstance(host, str):
            raise ValueError("SSO_APP_ACCESS_JSON keys must be hostnames.")
        if not isinstance(users, list):
            raise ValueError(f"SSO_APP_ACCESS_JSON value for {host!r} must be a list.")

        normalized_users: list[str] = []
        for user in users:
            if not isinstance(user, str):
                raise ValueError(f"SSO_APP_ACCESS_JSON entries for {host!r} must be strings.")
            cleaned = user.strip().lower()
            if cleaned:
                normalized_users.append(cleaned)

        result[host.strip().lower()] = tuple(normalized_users)

    return result


def _parse_app_access_simple(value: str) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}

    raw_entries: list[str] = []
    for line in value.splitlines():
        for chunk in line.split(";"):
            chunk = chunk.strip()
            if not chunk or chunk.startswith("#"):
                continue
            raw_entries.append(chunk)

    for entry in raw_entries:
        if "=" not in entry:
            raise ValueError(
                f"SSO_APP_ACCESS entry {entry!r} must use the form 'host=user1,user2'."
            )

        host, _, users_part = entry.partition("=")
        host = _normalize_host(host)
        if not host:
            raise ValueError(f"SSO_APP_ACCESS entry {entry!r} is missing a host.")

        users = tuple(
            user.strip().lower()
            for user in users_part.split(",")
            if user.strip()
        )
        result[host] = users

    return result


def _normalize_host(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        return ""

    if "://" in cleaned:
        cleaned = urlparse(cleaned).hostname or ""
    else:
        cleaned = cleaned.split("/", 1)[0]

    return cleaned.strip().strip(".")


def is_user_allowed_for_host(
    email: str,
    host: str | None,
    app_access: dict[str, tuple[str, ...]],
) -> bool:
    if not app_access:
        return True

    normalized_host = _normalize_host(host or "")
    if not normalized_host:
        return False

    allowed = app_access.get(normalized_host)
    if allowed is None:
        return True

    if "*" in allowed:
        return True

    return normalize_email(email) in allowed


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
