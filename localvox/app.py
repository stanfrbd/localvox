import asyncio
from contextlib import asynccontextmanager
import fcntl
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import shutil
import tempfile
import time
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from .audio import AudioError, EXTENSIONS, decode
from .config import Settings
from .engine import MockEngine, ParakeetEngine
from .models import CATALOG

STATIC = Path(__file__).with_name("static")
COOKIE = "localvox_session"
PUBLIC = {"/health", "/login", "/manifest.webmanifest", "/sw.js", "/icon-192.png", "/icon-512.png"}


def session_value(settings):
    payload = f"{int(time.time()) + 43200}.{secrets.token_hex(16)}"
    sig = hmac.new(settings.token.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def has_session(request, settings):
    try:
        value = request.cookies.get(COOKIE, "")
        expiry, nonce, sig = value.split(".")
        expected = hmac.new(settings.token.encode(), f"{expiry}.{nonce}".encode(), hashlib.sha256).hexdigest()
        return int(expiry) > time.time() and hmac.compare_digest(sig, expected)
    except (ValueError, TypeError):
        return False


def authorized(request, settings):
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return hmac.compare_digest(auth[7:].encode(), settings.token.encode())
    return has_session(request, settings)


class Guard:
    """Authenticate before reading, bound active requests and streamed body bytes."""
    def __init__(self, app, settings):
        self.app, self.settings = app, settings
        self.lock = asyncio.Lock()
        self.pending = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = scope["path"]

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend([
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    # no-referrer makes browsers send Origin: null on form POSTs,
                    # which correctly fails the CSRF check even for our login form.
                    (b"referrer-policy", b"same-origin"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                ])
            await send(message)

        async def error(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secure_send)

        if path not in PUBLIC and not authorized(request, self.settings):
            if path == "/" and request.method == "GET":
                return await RedirectResponse("/login", 303)(scope, receive, secure_send)
            return await error(401, "Authentication required.")
        if request.method not in {"GET", "HEAD"} and "authorization" not in request.headers:
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return await error(403, "Cross-origin request refused.")
            if path != "/login" and not origin:
                return await error(403, "Cookie requests require a same-origin Origin header.")
        is_job = path in {"/api/transcribe", "/share"} and request.method == "POST"
        if is_job:
            if self.pending >= self.settings.max_pending:
                return await error(503, "Queue is full. Retry shortly.")
            self.pending += 1
            try:
                await asyncio.wait_for(self.lock.acquire(), timeout=self.settings.queue_timeout)
            except (TimeoutError, asyncio.CancelledError) as exc:
                self.pending -= 1
                if isinstance(exc, asyncio.CancelledError):
                    raise
                return await error(503, "Queue wait timed out. Retry shortly.")
        try:
            if request.method in {"POST", "PUT", "PATCH"}:
                limit = self.settings.max_body_bytes if is_job else 8192
                # Buffer to a bounded spool before multipart parsing, including chunked requests.
                # This prevents an unbounded multipart spool even when Content-Length is absent.
                with tempfile.TemporaryFile() as body:
                    total = 0
                    try:
                        async with asyncio.timeout(self.settings.upload_timeout):
                            while True:
                                message = await receive()
                                if message["type"] == "http.disconnect":
                                    return
                                data = message.get("body", b"")
                                total += len(data)
                                if total > limit:
                                    return await error(413, "Request body is too large.")
                                body.write(data)
                                if not message.get("more_body", False):
                                    break
                    except TimeoutError:
                        return await error(408, "Upload timed out.")
                    body.seek(0)

                    async def replay():
                        data = body.read(65536)
                        return {"type": "http.request", "body": data, "more_body": body.tell() < total}

                    await self.app(scope, replay, secure_send)
            else:
                await self.app(scope, receive, secure_send)
        finally:
            if is_job:
                self.lock.release()
                self.pending -= 1


def create_app(settings=None, engine=None):
    settings = settings or Settings.from_env()
    engine = engine or (MockEngine() if settings.backend == "mock" else ParakeetEngine(settings))

    @asynccontextmanager
    async def lifespan(app):
        settings.temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (settings.temp_dir / ".server.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Use exactly one LocalVox server process per temporary directory.") from None
            # With the exclusive lock held, these belong to a previous stopped server.
            for stale in settings.temp_dir.glob("localvox-*"):
                if stale.is_dir() and not stale.is_symlink():
                    shutil.rmtree(stale)
            with tempfile.TemporaryDirectory(prefix="localvox-", dir=settings.temp_dir) as run:
                old_temp = tempfile.tempdir
                tempfile.tempdir = str(Path(run).resolve())
                app.state.run_dir = Path(run)
                try:
                    yield
                finally:
                    engine.close()
                    tempfile.tempdir = old_temp

    app = FastAPI(title="LocalVox", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(Guard, settings=settings)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        # Do not echo untrusted parser input or request headers.
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse({"detail": detail.replace(settings.token, "[redacted]")}, status_code=exc.status_code)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/login")
    async def login_page():
        return FileResponse(STATIC / "login.html")

    @app.post("/login")
    async def login(request: Request):
        async with request.form(max_files=0, max_fields=1, max_part_size=4096) as form:
            supplied = form.get("token", "")
            if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), settings.token.encode()):
                raise HTTPException(401, "Invalid token.")
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, session_value(settings), max_age=43200, httponly=True,
                            secure=settings.secure_cookie, samesite="lax", path="/")
        return response

    @app.post("/logout")
    async def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE)
        return response

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/model")
    async def model_status():
        path = settings.model_dir / CATALOG["filename"]
        return {"name": CATALOG["name"], "backend": settings.backend,
                "downloaded": path.is_file() and path.stat().st_size == CATALOG["size"],
                "integrity": "SHA-256 verified before loading", "max_files": settings.max_files,
                "max_file_mb": settings.max_file_bytes / 1024 / 1024,
                "max_seconds": settings.max_seconds}

    # Explicit asset allowlist: no arbitrary path access.
    for name in ("app.js", "style.css", "manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png"):
        def asset_route(filename):
            async def asset():
                media = {"sw.js": "application/javascript", "manifest.webmanifest": "application/manifest+json"}.get(filename)
                return FileResponse(STATIC / filename, media_type=media)
            return asset
        app.add_api_route("/" + name, asset_route(name), methods=["GET"], include_in_schema=False)

    def process(files, directory):
        results = []
        for upload in files:
            name = (upload.filename or "audio").replace("\\", "/").split("/")[-1][:160]
            name = "".join(c for c in name if c.isprintable()).replace(settings.token, "[redacted]")
            row = {"filename": name, "status": "error", "text": None, "error": None, "duration_seconds": None}
            try:
                if Path(name).suffix.lower() not in EXTENSIONS:
                    raise AudioError("Unsupported file extension.")
                if upload.size is not None and upload.size > settings.max_file_bytes:
                    raise AudioError("File exceeds the configured size limit.")
                with tempfile.TemporaryDirectory(dir=directory, prefix="file-") as work:
                    source, pcm = Path(work) / "input", Path(work) / "audio.f32"
                    with source.open("wb") as out:
                        total = 0
                        while chunk := upload.file.read(65536):
                            total += len(chunk)
                            if total > settings.max_file_bytes:
                                raise AudioError("File exceeds the configured size limit.")
                            out.write(chunk)
                    row["duration_seconds"] = decode(source, pcm, settings.max_seconds, settings.task_timeout)
                    row["text"] = engine.transcribe(pcm).replace(settings.token, "[redacted]")
                    row["status"] = "done"
            except AudioError as exc:
                row["error"] = str(exc)
            except RuntimeError as exc:
                # Only our own engine messages are public; injected backends may expose secrets.
                allowed = ("Parakeet Ultra is missing", "Local engine", "Could not load Parakeet", "Transcription failed")
                row["error"] = str(exc) if str(exc).startswith(allowed) else "Local transcription failed. Check the server configuration."
            except Exception:
                row["error"] = "Local transcription failed. Check the server configuration."
            results.append(row)
        return {"results": results}

    @app.post("/api/transcribe")
    @app.post("/share")
    async def transcribe(request: Request):
        async with request.form(max_files=settings.max_files, max_fields=0, max_part_size=4096) as form:
            files = form.getlist("files")
            if not files or any(not isinstance(f, UploadFile) for f in files) or any(k != "files" for k in form):
                raise HTTPException(400, "Use multipart file parts named files.")
            # Default AnyIO cancellation shielding keeps temporary data alive until work stops.
            # A disconnected HTTP client may finish the active bounded batch; there is no history.
            return await anyio.to_thread.run_sync(process, files, app.state.run_dir)

    return app
