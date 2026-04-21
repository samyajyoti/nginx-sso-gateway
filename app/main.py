from pathlib import Path

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import (
    Settings,
    get_session_email,
    is_allowed_email,
    load_settings,
    normalize_email,
    sanitize_next_url,
    validate_credentials,
)


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    app = FastAPI(title="Nginx SSO Gateway", version="0.1.0")
    app.state.settings = settings
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.cookie_name,
        max_age=settings.session_max_age,
        same_site=settings.cookie_same_site,
        https_only=settings.cookie_secure,
        domain=settings.cookie_domain,
    )

    @app.get("/healthz", response_class=JSONResponse)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        email = get_session_email(request.session)
        next_url = request.query_params.get("next")
        if email:
            target = sanitize_next_url(next_url, settings.cookie_domain, settings.default_redirect_url)
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "email": email,
                    "error": None,
                    "next_url": target,
                    "allowed_domains": settings.allowed_email_domains,
                },
            )

        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, next: str | None = None) -> HTMLResponse | RedirectResponse:
        email = get_session_email(request.session)
        target = sanitize_next_url(next, settings.cookie_domain, settings.default_redirect_url)
        if email:
            return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)

        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "email": None,
                "error": None,
                "next_url": next or "",
                "allowed_domains": settings.allowed_email_domains,
            },
        )

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        next: str = Form(""),
    ) -> HTMLResponse | RedirectResponse:
        normalized_email = normalize_email(email)
        is_valid, error_message = validate_credentials(normalized_email, password, settings)
        if not is_valid:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "email": normalized_email,
                    "error": error_message,
                    "next_url": next,
                    "allowed_domains": settings.allowed_email_domains,
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        request.session.clear()
        request.session["user"] = {"email": normalized_email}

        target = sanitize_next_url(next, settings.cookie_domain, settings.default_redirect_url)
        return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)

    @app.get("/auth/check", response_class=PlainTextResponse)
    async def auth_check(request: Request) -> PlainTextResponse:
        email = get_session_email(request.session)
        if not email or not is_allowed_email(email, settings.allowed_email_domains):
            request.session.clear()
            return PlainTextResponse("Unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)

        response = PlainTextResponse("OK", status_code=status.HTTP_200_OK)
        response.headers["X-Authenticated-Email"] = email
        response.headers["X-Authenticated-User"] = email.split("@", 1)[0]
        return response

    @app.api_route("/logout", methods=["GET", "POST"])
    async def logout(request: Request, next: str | None = None) -> RedirectResponse:
        request.session.clear()
        target = sanitize_next_url(next, settings.cookie_domain, "/login")
        return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)

    return app


app = create_app()
