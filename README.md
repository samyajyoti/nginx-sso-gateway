# Nginx SSO Gateway

`nginx-sso-gateway` is a small Python/FastAPI service that gives single sign-on across nginx-protected apps under `*.wrtual.in` using Google OAuth.

Users sign in once with their `@datacultr.com` Google account at the SSO host (for example `test-sso.wrtual.in`), nginx validates the shared session with `auth_request`, and apps such as `app1.wrtual.in` and `app2.wrtual.in` stop asking for credentials again.

## Features

- Google OAuth login restricted to a Google Workspace email domain
- Shared signed session cookie scoped to `.wrtual.in`
- Email-domain allowlist with `@datacultr.com` as the default
- Nginx `auth_request` integration for existing protected apps
- Safe redirect handling back to the original app after sign-in
- Upstream headers that expose the authenticated email/user name

## Project Layout

- `app/main.py`: FastAPI app and HTTP routes
- `app/auth.py`: settings, email-domain checks, and redirect safety helpers
- `app/templates/login.html`: sign-in page
- `deploy/nginx/auth-gateway.conf`: nginx vhost for the auth service
- `deploy/nginx/protected-app.conf`: nginx example showing `auth_request`
- `tests/test_sso.py`: automated checks for cross-subdomain SSO and logout

## Requirements

- Python 3.11+
- HTTPS-enabled nginx in front of the auth service and protected apps
- A Google OAuth client (created in Google Cloud Console)

## Google OAuth Setup

1. Open [Google Cloud Console](https://console.cloud.google.com/), pick or create a project.
2. Configure the OAuth consent screen with **User Type = Internal** so only your Google Workspace users can sign in.
3. Create credentials → OAuth client ID → Web application:
   - Authorized JavaScript origins: `https://test-sso.wrtual.in`
   - Authorized redirect URI: `https://test-sso.wrtual.in/auth/google/callback`
4. Copy the generated Client ID and Client Secret into `.env`.

## Configuration

Set these environment variables before running the service:

- `SSO_SECRET_KEY`: random secret used to sign the session cookie
- `SSO_ALLOWED_EMAIL_DOMAINS`: comma-separated email domains allowed to sign in, defaults to `datacultr.com`
- `SSO_COOKIE_DOMAIN`: parent cookie domain, defaults to `.wrtual.in`
- `SSO_AUTH_HOST`: auth host, defaults to `auth.wrtual.in`
- `SSO_DEFAULT_REDIRECT_URL`: fallback redirect after login, defaults to `https://<auth-host>/`
- `SSO_COOKIE_NAME`: cookie name, defaults to `wrtual_sso`
- `SSO_COOKIE_SECURE`: `true` by default
- `SSO_COOKIE_SAMESITE`: `lax` by default
- `SSO_SESSION_MAX_AGE`: max session age in seconds, defaults to `28800`
- `GOOGLE_CLIENT_ID`: OAuth client ID from Google Cloud Console
- `GOOGLE_CLIENT_SECRET`: OAuth client secret from Google Cloud Console
- `GOOGLE_REDIRECT_URI`: must match a Google "Authorized redirect URI", typically `https://<auth-host>/auth/google/callback`
- `GOOGLE_HOSTED_DOMAIN`: optional, restricts the Google account picker to this domain (defaults to the only allowed email domain when there is just one)

A starter `.env.example` is provided.

## Local Run

Create a virtual environment, install dependencies, then run the app:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker Run

This repo includes a `Dockerfile` and `docker-compose.yml` for running the SSO service in a container.

1. Create a runtime env file:

```bash
cp .env.example .env
```

2. Update `.env`, especially `SSO_SECRET_KEY`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET`.

3. Build and start the container:

```bash
docker compose up --build
```

The app will be available on `http://localhost:8000`.

## How Nginx Uses It

Each protected app should replace `auth_basic` with `auth_request`.

The request flow is:

1. A user opens `https://app1.wrtual.in/`.
2. Nginx calls `https://test-sso.wrtual.in/auth/check`.
3. If there is no valid SSO session, nginx redirects the browser to `https://test-sso.wrtual.in/login?next=...`.
4. The user clicks "Sign in with Google" and authenticates with their `@datacultr.com` account.
5. The auth service sets a secure cookie for `.wrtual.in` and redirects back to the original URL.
6. Subsequent visits to `app2.wrtual.in` reuse that same cookie.

See:

- `deploy/nginx/auth-gateway.conf`
- `deploy/nginx/protected-app.conf`

## Notes

- This app uses signed cookie sessions, which is enough for a simple rollout.
- If you need central session revocation later, swap the session storage to Redis.
- The Google OAuth consent screen should be set to **Internal** in your Google Workspace so only your domain users can use this client.

## Tests

Run the test suite with:

```bash
pytest
```
