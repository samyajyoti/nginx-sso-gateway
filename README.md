# Nginx SSO Gateway

`nginx-sso-gateway` is a small Python/FastAPI service that gives single sign-on across nginx-protected apps under `*.wrtual.in`.

Users sign in once at `auth.wrtual.in`, nginx validates the shared session with `auth_request`, and apps such as `app1.wrtual.in` and `app2.wrtual.in` stop asking for credentials again.

## Features

- Shared signed session cookie scoped to `.wrtual.in`
- Email-domain allowlist with `@datacultr.com` as the default
- Nginx `auth_request` integration for existing protected apps
- Safe redirect handling back to the original app after sign-in
- Upstream headers that expose the authenticated email/user name

## Project Layout

- `app/main.py`: FastAPI app and HTTP routes
- `app/auth.py`: settings, credential validation, and redirect safety helpers
- `app/templates/login.html`: sign-in page
- `deploy/nginx/auth-gateway.conf`: nginx vhost for the auth service
- `deploy/nginx/protected-app.conf`: nginx example showing `auth_request`
- `tests/test_sso.py`: automated checks for login, cross-subdomain SSO, and logout

## Requirements

- Python 3.11+
- HTTPS-enabled nginx in front of the auth service and protected apps

## Configuration

Set these environment variables before running the service:

- `SSO_SECRET_KEY`: random secret used to sign the session cookie
- `SSO_USERS_JSON`: JSON object mapping email addresses to bcrypt password hashes
- `SSO_ALLOWED_EMAIL_DOMAINS`: comma-separated email domains allowed to log in, defaults to `datacultr.com`
- `SSO_COOKIE_DOMAIN`: parent cookie domain, defaults to `.wrtual.in`
- `SSO_AUTH_HOST`: auth host, defaults to `auth.wrtual.in`
- `SSO_DEFAULT_REDIRECT_URL`: fallback redirect after login, defaults to `https://auth.wrtual.in/`
- `SSO_COOKIE_NAME`: cookie name, defaults to `wrtual_sso`
- `SSO_COOKIE_SECURE`: `true` by default
- `SSO_COOKIE_SAMESITE`: `lax` by default
- `SSO_SESSION_MAX_AGE`: max session age in seconds, defaults to `28800`

Example:

```bash
export SSO_SECRET_KEY='replace-with-a-random-secret'
export SSO_USERS_JSON='{"user@datacultr.com":"$2b$12$DkOT1Wu0n7y9x4kY9GQ6XuM4A3pUwOCa/MEzhjmEUzQAQ6VykBLLi"}'
export SSO_ALLOWED_EMAIL_DOMAINS='datacultr.com'
export SSO_COOKIE_DOMAIN='.wrtual.in'
```

Generate a bcrypt hash for a password:

```bash
python3 - <<'PY'
from passlib.context import CryptContext

print(CryptContext(schemes=["bcrypt"], deprecated="auto").hash("replace-me"))
PY
```

## Local Run

Create a virtual environment, install dependencies, then run the app:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## How Nginx Uses It

Each protected app should replace `auth_basic` with `auth_request`.

The request flow is:

1. A user opens `https://app1.wrtual.in/`.
2. Nginx calls `https://auth.wrtual.in/auth/check`.
3. If there is no valid SSO session, nginx redirects the browser to `https://auth.wrtual.in/login?next=...`.
4. The user signs in with a valid `@datacultr.com` account.
5. The auth service sets a secure cookie for `.wrtual.in` and redirects back.
6. Subsequent visits to `app2.wrtual.in` reuse that same cookie.

See:

- `deploy/nginx/auth-gateway.conf`
- `deploy/nginx/protected-app.conf`

## Notes

- This app uses signed cookie sessions, which is enough for a simple rollout.
- If you need central session revocation later, swap the session storage to Redis.
- If you later integrate with LDAP, OAuth, OIDC, or SAML, keep the nginx `auth_request` pattern and replace the credential backend behind `/login`.

## Tests

Run the test suite with:

```bash
pytest
```
