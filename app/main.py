from pathlib import Path

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import (
    Settings,
    get_session_email,
    is_allowed_email,
    load_settings,
    normalize_email,
    sanitize_next_url,
)


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _build_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        client_kwargs={
            "scope": "openid email profile",
            "prompt": "select_account",
        },
    )
    return oauth


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    app = FastAPI(title="Nginx SSO Gateway", version="0.2.0")
    app.state.settings = settings
    app.state.oauth = _build_oauth(settings)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.cookie_name,
        max_age=settings.session_max_age,
        same_site=settings.cookie_same_site,
        https_only=settings.cookie_secure,
        domain=settings.cookie_domain,
    )

    def render_login(request: Request, error: str | None = None, status_code: int = 200) -> Response:
        next_url = request.query_params.get("next", "")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "email": get_session_email(request.session),
                "error": error,
                "next_url": next_url,
                "allowed_domains": settings.allowed_email_domains,
            },
            status_code=status_code,
        )

    @app.get("/healthz", response_class=JSONResponse)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> Response:
        if get_session_email(request.session):
            return render_login(request)
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> Response:
        if get_session_email(request.session):
            target = sanitize_next_url(
                request.query_params.get("next"),
                settings.cookie_domain,
                settings.default_redirect_url,
            )
            return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
        return render_login(request)

    @app.get("/auth/google/start")
    async def google_start(request: Request) -> Response:
        if not settings.google_client_id or not settings.google_client_secret:
            return render_login(
                request,
                error="Google login is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
                status_code=500,
            )

        next_url = sanitize_next_url(
            request.query_params.get("next"),
            settings.cookie_domain,
            settings.default_redirect_url,
        )
        request.session["post_login_next"] = next_url

        oauth: OAuth = request.app.state.oauth
        kwargs: dict[str, str] = {}
        if settings.google_hosted_domain:
            kwargs["hd"] = settings.google_hosted_domain
        return await oauth.google.authorize_redirect(
            request,
            settings.google_redirect_uri,
            **kwargs,
        )

    @app.get("/auth/google/callback")
    async def google_callback(request: Request) -> Response:
        oauth: OAuth = request.app.state.oauth
        try:
            token = await oauth.google.authorize_access_token(request)
        except OAuthError as exc:
            return render_login(
                request,
                error=f"Google sign-in failed: {exc.error or 'unknown error'}.",
                status_code=400,
            )

        userinfo = token.get("userinfo") or await oauth.google.userinfo(token=token)
        email = normalize_email(userinfo.get("email", ""))
        email_verified = bool(userinfo.get("email_verified", False))

        if not email or not email_verified:
            return render_login(
                request,
                error="Google did not return a verified email address.",
                status_code=401,
            )

        if not is_allowed_email(email, settings.allowed_email_domains):
            joined_domains = ", ".join(f"@{domain}" for domain in settings.allowed_email_domains)
            return render_login(
                request,
                error=f"Only {joined_domains} accounts can sign in here.",
                status_code=403,
            )

        next_url = request.session.pop("post_login_next", settings.default_redirect_url)
        request.session.clear()
        request.session["user"] = {
            "email": email,
            "name": userinfo.get("name"),
            "picture": userinfo.get("picture"),
        }

        target = sanitize_next_url(next_url, settings.cookie_domain, settings.default_redirect_url)
        return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)

    @app.get("/auth/check", response_class=PlainTextResponse)
    async def auth_check(request: Request) -> Response:
        email = get_session_email(request.session)
        if not email or not is_allowed_email(email, settings.allowed_email_domains):
            request.session.clear()
            return PlainTextResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

        response = PlainTextResponse("OK", status_code=status.HTTP_200_OK)
        response.headers["X-Authenticated-Email"] = email
        response.headers["X-Authenticated-User"] = email.split("@", 1)[0]
        return response

    @app.api_route("/logout", methods=["GET", "POST"])
    async def logout(request: Request) -> Response:
        request.session.clear()
        next_url = request.query_params.get("next")
        target = sanitize_next_url(next_url, settings.cookie_domain, "/login")
        return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)

    return app


app = create_app()
