"""FastAPI application factory."""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import settings
from .db.session import SessionLocal, init_db
from .logging_setup import configure_logging

log = logging.getLogger("rdi")

OPEN_PATHS = {"/api/health", "/api/settings/public"}


def _startup(start_background: bool) -> None:
    configure_logging()
    settings.ensure_dirs()
    info = init_db()
    log.info("Database ready (%s)", "new" if info["new_database"] else f"schema v{info['to_version']}")
    from .services import job_handlers  # noqa: F401  (registers job handlers)
    from .services.acquisition import seed_sources
    from .services.jobs import recover_interrupted
    with SessionLocal() as db:
        seed_sources(db)
    n = recover_interrupted()
    if n:
        log.warning("%s job(s) from a previous run were marked INTERRUPTED", n)
    if start_background:
        from .services import scheduler
        scheduler.start()


def _shutdown() -> None:
    from .services import jobs, scheduler
    scheduler.stop()
    jobs.shutdown()
    log.info("Shutdown complete")


def create_app(start_background: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        _startup(start_background)
        yield
        _shutdown()

    app = FastAPI(title="Road Disruption Intelligence API", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "Authorization", "X-Operator"])

    @app.middleware("http")
    async def security(request: Request, call_next):
        path = request.url.path
        if settings.access_token and path.startswith("/api/") and path not in OPEN_PATHS and request.method != "OPTIONS":
            supplied = request.headers.get("authorization", "")
            token = supplied[7:] if supplied.lower().startswith("bearer ") else ""
            if not token or not hmac.compare_digest(token, settings.access_token):
                return JSONResponse({"error": {"code": 401, "message": "Access token required"},
                                     "detail": "Access token required"}, status_code=401)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if not path.startswith("/api/docs"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob: https:; connect-src 'self' https:; font-src 'self' data: https:; "
                "worker-src 'self' blob:; child-src blob:; frame-ancestors 'none'; base-uri 'self'")
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        msg = detail if isinstance(detail, str) else (detail.get("message") if isinstance(detail, dict) else str(detail))
        return JSONResponse({"error": {"code": exc.status_code, "message": msg}, "detail": detail},
                            status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        errs = [{"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg")} for e in exc.errors()]
        msg = "; ".join(f"{'.'.join(e['loc'][1:]) or 'body'}: {e['msg']}" for e in errs[:5])
        return JSONResponse({"error": {"code": 422, "message": msg}, "detail": errs}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception):
        log.exception("Unhandled error")
        return JSONResponse({"error": {"code": 500, "message": "Internal server error – see runtime/logs"}},
                            status_code=500)

    from .api import config_api, dashboard, incidents, operations, records
    for r in (config_api.router, dashboard.router, incidents.router, operations.router, records.router):
        app.include_router(r)

    dist = settings.frontend_dist
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (dist / full_path).resolve()
        if full_path and dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return HTMLResponse("<h1>Road Disruption Intelligence</h1><p>The web interface has not been built yet. "
                            "Run <code>setup_and_start.bat</code> (or <code>npm run build</code> in "
                            "<code>frontend/</code>). The API is available at <a href='/api/docs'>/api/docs</a>.</p>",
                            status_code=503)

    return app
