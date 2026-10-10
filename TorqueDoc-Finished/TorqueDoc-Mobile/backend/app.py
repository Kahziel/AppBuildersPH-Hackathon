"""Same-origin local API and the original TorqueDoc interface."""
from __future__ import annotations

import os
import threading
from datetime import date
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from fastapi.concurrency import run_in_threadpool

from . import web
from .inference import DEFAULT_MODEL, LocalEngine
from .store import DocumentError, KINDS, MAX_BYTES, NotFound, Store, query_terms

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = {"index.html", "app.js", "icons.js", "styles.css", "technical.js", "technical.css",
          "library.js", "library.css", "mvp.js", "mvp.css", "icon.svg", "manifest.webmanifest", "sw.js"}


class Metadata(BaseModel):
    machine: str = Field(min_length=1, max_length=40)
    variant: str = Field(min_length=1, max_length=120)
    revision: str = Field(default="Not supplied", max_length=120)
    kind: str = Field(default="manual", max_length=20)
    supersedes: str | None = Field(default=None, max_length=80)


class WebPage(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    machine: str = Field(min_length=1, max_length=40)
    variant: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=220)
    supersedes: str | None = Field(default=None, max_length=80)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=700)
    document_id: str | None = Field(default=None, max_length=80)  # None: every current manual for the machine
    machine: str = Field(min_length=1, max_length=40)
    search_only: bool = False


def create_app(data_dir=None, engine=None, library=None, sync=True, fetcher=None):
    """library: folder of built-in manuals. The launched app uses ./library (or TORQUEDOC_LIBRARY)."""
    if library is None and data_dir is None:
        library = os.environ.get("TORQUEDOC_LIBRARY", ROOT / "library")

    @asynccontextmanager
    async def lifespan(app):
        if sync and store.library:
            # Index the built-in library in the background; the interface is usable immediately.
            threading.Thread(target=startup_library, daemon=True, name="library-sync").start()
        yield

    if fetcher is None and os.environ.get("TORQUEDOC_TEST_ALLOW_LOCAL_WEB") == "1":
        # Automated tests only: lets the browser test save a page from a fixture server on this computer.
        fetcher = lambda url, allow_private=False: web.fetch(url, allow_private=True)  # noqa: E731
    app = FastAPI(title="TorqueDoc local API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    store = Store(Path(data_dir or os.environ.get("TORQUEDOC_DATA_DIR", ROOT / "data")), library)
    local = engine or LocalEngine(os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
                                  os.environ.get("TORQUEDOC_MODEL", DEFAULT_MODEL))
    ingest_lock = threading.Lock()
    app.state.store, app.state.engine = store, local
    web_status = {"state": "idle", "done": 0, "total": 0, "current": "", "errors": []}

    def startup_library():
        store.sync_library(ingest_lock)
        listed, saved = web.listed_sources(store.library)
        if listed > saved and os.environ.get("TORQUEDOC_OFFLINE") != "1":
            # Fetch listed web sources that are not saved yet. Offline, this fails quickly and is retried next start.
            web_status.update(state="downloading", done=0, total=0, errors=[])
            download_web_sources(only_missing=True)

    def download_web_sources(only_missing):
        def progress(done, total, url):
            web_status.update(done=done, total=total, current=url)
        try:
            web_status["errors"] = web.download_library_sources(store.library, fetcher, progress, only_missing)
        except Exception as exc:  # A broken catalog must not crash the server.
            web_status["errors"] = [f"Web sources could not be downloaded: {exc}"]
        web_status.update(state="indexing", current="")
        store.sync_library(ingest_lock)
        web_status["state"] = "done"

    @contextmanager
    def library_change(wait=False):
        if not ingest_lock.acquire(timeout=300) if wait else not ingest_lock.acquire(blocking=False):
            raise HTTPException(409, "A manual is being indexed. Please retry shortly.")
        try:
            yield
        finally:
            ingest_lock.release()

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Bind to loopback as well. Reject cross-site requests and DNS-rebinding hostnames.
        allowed = {"127.0.0.1", "localhost", "::1", "testserver"}
        host = urlparse("http://" + request.headers.get("host", "")).hostname
        origin = request.headers.get("origin")
        if host not in allowed or (origin and origin != f"{request.url.scheme}://{request.headers.get('host')}"):
            return JSONResponse({"detail": "Use TorqueDoc from its local application address."}, status_code=403)
        length = request.headers.get("content-length", "0")
        if request.url.path == "/api/documents" and request.method == "POST":
            try:
                if int(length) > MAX_BYTES + 1024 * 1024:
                    return JSONResponse({"detail": "Maximum PDF size is 50 MB."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid request length."}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/") and request.url.path.endswith("/image") and response.status_code == 200:
            # Page images of a stored PDF never change; document IDs are never reused.
            response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
        return response

    @app.exception_handler(DocumentError)
    async def bad_document(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(NotFound)
    async def missing_document(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.get("/api/ping")
    def ping():
        """Instant readiness check for the desktop launcher: no database, no Ollama."""
        return {"app": "torquedoc", "ready": True}

    @app.get("/api/health")
    def health(fresh: bool = False):
        docs = store.documents()
        return {"backend": "ready", "engine": local.health(fresh=fresh), "search": "sqlite_fts5",
                "documents": len(docs), "builtin_documents": sum(d["source"] == "builtin" for d in docs),
                "manual_bytes": sum(d["bytes"] for d in docs), "library": store.status(),
                "web_sources": {**dict(zip(("listed", "saved"), web.listed_sources(store.library) if store.library else (0, 0))), **web_status},
                "ocr": False, "network_mode": "loopback_only; internet only when saving web pages"}

    @app.get("/api/machines")
    def machines():
        return {"machines": store.machines()}

    @app.get("/api/documents")
    def documents(machine: str | None = None):
        return {"documents": store.documents(machine)}

    @app.post("/api/documents", status_code=201)
    async def upload(file: UploadFile = File(...), machine: str = Form(...),
                     variant: str = Form(...), revision: str = Form("Not supplied"),
                     kind: str = Form("manual"), supersedes: str = Form("")):
        if machine not in store.machine_ids() or kind not in KINDS:
            raise HTTPException(422, "Choose a valid machine and document type.")
        variant, revision = variant.strip(), revision.strip() or "Not supplied"
        title = (file.filename or "Manual.pdf").replace("\\", "/").rsplit("/", 1)[-1]
        if not 1 <= len(variant) <= 120 or len(revision) > 120 or len(title) > 220:
            raise HTTPException(422, "Provide an equipment variant and metadata under the displayed limits.")
        # Waits for the built-in library indexer between manuals rather than failing.
        if not await run_in_threadpool(ingest_lock.acquire, True, 300):
            raise HTTPException(409, "Another manual is being indexed. Please retry shortly.")
        try:
            content = await file.read(MAX_BYTES + 1)
            item = await run_in_threadpool(store.ingest, content, title, machine, variant, revision, kind,
                                           supersedes.strip() or None)
            return item
        finally:
            await file.close()
            ingest_lock.release()

    @app.post("/api/web", status_code=201)
    def save_web_page(payload: WebPage):
        """Download a public page once and keep it as an offline, citable update."""
        if payload.machine not in store.machine_ids():
            raise HTTPException(422, "Choose a valid machine workspace.")
        variant = payload.variant.strip()
        try:
            pdf, title, final = web.save_page(payload.url, fetcher=fetcher)
        except web.WebError as exc:
            raise HTTPException(422, str(exc)) from exc
        title = (payload.title.strip() or title)[:220]
        with library_change(wait=True):
            return store.ingest(pdf, title, payload.machine, variant, f"Web page saved {date.today().isoformat()}", "web",
                                payload.supersedes or None, url=final[:2000])

    @app.post("/api/library/web-sources", status_code=202)
    def refresh_web_sources(only_missing: bool = False):
        if not store.library or not store.library.is_dir():
            raise HTTPException(422, "The built-in library folder is missing.")
        if web_status["state"] in {"downloading", "indexing"}:
            raise HTTPException(409, "Web sources are already being downloaded.")
        web_status.update(state="downloading", done=0, total=0, errors=[])
        threading.Thread(target=download_web_sources, args=(only_missing,), daemon=True, name="web-sources").start()
        return {"started": True}

    @app.patch("/api/documents/{document_id}")
    def edit(document_id: str, payload: Metadata):
        variant, revision = payload.variant.strip(), payload.revision.strip() or "Not supplied"
        if not variant:
            raise HTTPException(422, "Provide an equipment variant.")
        with library_change():
            return store.update(document_id, payload.machine, variant, revision, payload.kind, payload.supersedes or None)

    @app.delete("/api/documents/{document_id}")
    def remove(document_id: str):
        with library_change():
            store.delete(document_id)
        return {"deleted": document_id}

    @app.get("/api/documents/{document_id}/file")
    def original(document_id: str):
        document = store.document(document_id)
        return FileResponse(store.file(document_id), media_type="application/pdf", filename=document["title"], content_disposition_type="inline")

    @app.get("/api/documents/{document_id}/pages/{number}")
    def page(document_id: str, number: int):
        return store.page(document_id, number)

    @app.get("/api/documents/{document_id}/pages/{number}/image")
    def page_image(document_id: str, number: int):
        return Response(store.page_png(document_id, number), media_type="image/png")

    @app.post("/api/ask")
    def ask(payload: Question):
        question = payload.question.strip()
        if len(question) < 2:
            raise HTTPException(422, "Type a question or a technical search term.")
        document = store.document(payload.document_id) if payload.document_id else None
        sources = store.search(question, payload.machine, payload.document_id)
        machine_name = next((m["name"] for m in store.machines() if m["id"] == payload.machine), payload.machine)
        common = {"question": question, "document": document, "terms": query_terms(question),
                  "scope": "manual" if document else "machine",
                  "notice": "Confirm the exact equipment variant, revision, conditions and adjoining pages before service. Text extraction can lose table layout. Revision currency is not checked automatically."}
        if not sources:
            if document and document["status"] == "needs_ocr":
                message = "No searchable text is available. This PDF needs OCR; open the original pages."
            elif document:
                message = "No matching passage was found in this manual. Try the component name, part number or fault code."
            elif not store.documents(payload.machine):
                message = "There are no manuals for this machine yet. Add its PDFs to the built-in library or upload one."
            else:
                message = "No matching passage was found in this machine's manuals. Try the component name, part number or fault code."
            return {**common, "status": "not_found", "message": message, "evidence": [], "matches": []}
        if payload.search_only:
            where = "the selected manual" if document else "this machine's manuals"
            return {**common, "status": "search_only", "message": f"Keyword matches from {where}. These have not been selected as an answer by the local model.", "evidence": [], "matches": sources}
        evidence, message = local.select(question, document or {"machine": machine_name}, sources)
        status = "search_only" if evidence is None else "supported" if evidence else "not_found"
        return {**common, "status": status, "message": message, "evidence": evidence or [], "matches": sources}

    @app.get("/")
    def home():
        return FileResponse(ROOT / "index.html")

    @app.get("/{asset}")
    def asset(asset: str):
        if asset not in PUBLIC or not (ROOT / asset).is_file():
            raise HTTPException(404, "File not found.")
        return FileResponse(ROOT / asset)

    return app


app = create_app()
