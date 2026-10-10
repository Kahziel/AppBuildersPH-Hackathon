"""Page-preserving PDF ingestion, the built-in manual library and SQLite full-text retrieval. No network calls."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

MAX_BYTES = 50 * 1024 * 1024          # Uploaded updates. Built-in manuals have no size limit.
MAX_PAGES = 1500
MAX_TEXT = 15_000_000
KINDS = {"manual", "schematic", "bulletin", "web"}
DEFAULT_MACHINES = {"cat": "CAT 320D · Unit-41", "deere": "John Deere 850K · Unit-08",
                    "volvo": "Volvo EC220D · Unit-16", "training": "Training rig · TD-01 (fictional)"}
UNSPECIFIED_VARIANT = "Not listed in catalog — check the manual cover"
MACHINE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
PDF_LOCK = threading.RLock()
SCHEMA_VERSION = 5
# Part numbers and fault codes such as 1R-0750, E-360 or 3E/4512. Must contain a digit.
CODE = re.compile(r"(?<![\w-])[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)+(?![\w-])")
# Typographic ligatures (ﬁ, ﬂ, ﬃ …) are single characters in many PDFs; spell them out so "filter" finds "ﬁlter".
LIGATURES = {0xFB00: "ff", 0xFB01: "fi", 0xFB02: "fl", 0xFB03: "ffi", 0xFB04: "ffl", 0xFB05: "st", 0xFB06: "st"}
COLUMNS = ("id", "title", "machine", "variant", "revision", "type", "sha256", "bytes", "pages", "text_pages",
           "status", "added_at", "source", "source_path", "source_size", "source_mtime", "superseded_by", "url")


class DocumentError(ValueError):
    pass


class NotFound(LookupError):
    pass


def code_forms(text):
    """Separator-free copies of codes, so 1R-0750 and 1R0750 find each other."""
    forms = []
    for match in CODE.finditer(text):
        token = match.group(0)
        if any(c.isdigit() for c in token):
            forms.append(re.sub(r"[-/]", "", token).lower())
    return " ".join(dict.fromkeys(forms))


class Store:
    def __init__(self, root: Path, library: Path | None = None):
        self.root = Path(root)
        self.library = Path(library) if library else None
        self.files = self.root / "manuals"
        self.files.mkdir(parents=True, exist_ok=True)
        self.cache = self.root / "cache"
        self.path = self.root / "torquedoc.sqlite3"
        self.status_lock = threading.Lock()
        self.library_status = {"state": "none" if not self.library else "waiting", "total": 0, "done": 0,
                               "current": "", "errors": []}
        for leftover in self.files.glob("*.tmp"):
            leftover.unlink(missing_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, machine TEXT NOT NULL,
                    variant TEXT NOT NULL, revision TEXT NOT NULL, type TEXT NOT NULL,
                    sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, pages INTEGER NOT NULL,
                    text_pages INTEGER NOT NULL, status TEXT NOT NULL, added_at TEXT NOT NULL,
                    UNIQUE(sha256, machine, variant, revision, type)
                );
                CREATE TABLE IF NOT EXISTS pages (
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    number INTEGER NOT NULL, label TEXT NOT NULL, text TEXT NOT NULL,
                    PRIMARY KEY(document_id, number)
                );
                CREATE TABLE IF NOT EXISTS passages (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id)
                    ON DELETE CASCADE, page INTEGER NOT NULL, text TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS machines (id TEXT PRIMARY KEY, name TEXT NOT NULL, position INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS passages_document ON passages(document_id, page);
            """)
            self.migrate(db)
            if not db.execute("SELECT 1 FROM machines").fetchone():
                db.executemany("INSERT INTO machines VALUES (?,?,?)",
                               [(key, name, i) for i, (key, name) in enumerate(DEFAULT_MACHINES.items())])

    def migrate(self, db):
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version < 2:
            # Stemmed search (bolt finds bolts) plus separator-free part numbers and codes.
            columns = {row["name"] for row in db.execute("PRAGMA table_info(passages)")}
            if "codes" not in columns:
                db.execute("ALTER TABLE passages ADD COLUMN codes TEXT NOT NULL DEFAULT ''")
            db.executescript("""
                DROP TRIGGER IF EXISTS passages_insert;
                DROP TRIGGER IF EXISTS passages_delete;
                DROP TABLE IF EXISTS passage_search;
                DROP TABLE IF EXISTS passage_fts;
                CREATE VIRTUAL TABLE passage_fts USING fts5(
                    text, codes, content='passages', content_rowid='id', tokenize='porter unicode61'
                );
                CREATE TRIGGER passages_insert AFTER INSERT ON passages BEGIN
                    INSERT INTO passage_fts(rowid,text,codes) VALUES(new.id,new.text,new.codes);
                END;
                CREATE TRIGGER passages_delete AFTER DELETE ON passages BEGIN
                    INSERT INTO passage_fts(passage_fts,rowid,text,codes) VALUES('delete',old.id,old.text,old.codes);
                END;
            """)
            for row in db.execute("SELECT id,text FROM passages").fetchall():
                db.execute("UPDATE passages SET codes=? WHERE id=?", (code_forms(row["text"]), row["id"]))
            db.execute("INSERT INTO passage_fts(passage_fts) VALUES('rebuild')")
        if version < 3:
            # Built-in library documents and update/supersede tracking.
            columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            for name, definition in (("source", "TEXT NOT NULL DEFAULT 'update'"), ("source_path", "TEXT"),
                                     ("source_size", "INTEGER"), ("source_mtime", "REAL"), ("superseded_by", "TEXT")):
                if name not in columns:
                    db.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")
        if version < 4:
            # Web page snapshots keep the address they came from.
            if "url" not in {row["name"] for row in db.execute("PRAGMA table_info(documents)")}:
                db.execute("ALTER TABLE documents ADD COLUMN url TEXT")
        if version < 5 and version > 0:
            # Repair text indexed before ligatures were spelled out.
            for table in ("pages", "passages"):
                expression = "text"
                for code, letters in LIGATURES.items():
                    expression = f"replace({expression}, char({code}), '{letters}')"
                db.execute(f"UPDATE {table} SET text={expression} WHERE text <> {expression}")
            db.execute("INSERT INTO passage_fts(passage_fts) VALUES('rebuild')")
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    # ---- machines -------------------------------------------------------------------------
    def machines(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,name FROM machines ORDER BY position,name").fetchall()
        return [dict(row) for row in rows]

    def machine_ids(self):
        return {m["id"] for m in self.machines()}

    def check_machine(self, machine):
        if machine not in self.machine_ids():
            raise DocumentError("Choose a valid machine workspace.")

    # ---- documents ------------------------------------------------------------------------
    def documents(self, machine=None):
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM documents" + (" WHERE machine=?" if machine else "")
                + " ORDER BY superseded_by IS NOT NULL, source='update', title COLLATE NOCASE, added_at DESC",
                (machine,) if machine else (),
            ).fetchall()
        return [dict(row) for row in rows]

    def document(self, document_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise NotFound("Manual not found in this local library.")
        return dict(row)

    def file(self, document_id):
        document = self.document(document_id)
        if document["source"] == "builtin" and self.library:
            return self.library / document["source_path"]
        return self.files / f"{document['id']}.pdf"

    def ingest(self, content: bytes, title: str, machine: str, variant: str, revision: str, kind: str,
               supersedes: str | None = None, builtin: dict | None = None, url: str | None = None):
        """Index a PDF. `builtin` = {path,size,mtime} for library files, which are read in place, not copied."""
        if not content or (not builtin and len(content) > MAX_BYTES):
            raise DocumentError("Choose a PDF smaller than 50 MB.")
        if not content[:1024].lstrip().startswith(b"%PDF-"):
            raise DocumentError("This file is not a readable PDF. Export it as a PDF and retry.")
        self.check_machine(machine)
        if kind not in KINDS:
            raise DocumentError("Choose a valid document type.")
        if supersedes:
            self.check_supersedes(supersedes, machine)
        digest = hashlib.sha256(content).hexdigest()
        with self.connect() as db:
            existing = db.execute(
                "SELECT * FROM documents WHERE sha256=? AND machine=? AND variant=? AND revision=? AND type=?",
                (digest, machine, variant, revision, kind),
            ).fetchone()
        if existing:
            if supersedes and supersedes != existing["id"]:
                self.set_supersedes(existing["id"], supersedes)
            return {**self.document(existing["id"]), "duplicate": True}

        extracted, text_pages, total_text = [], 0, 0
        try:
            with PDF_LOCK, pymupdf.open(stream=content, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise DocumentError("Password-protected PDFs are not supported. Import an unlocked copy.")
                if not 0 < len(pdf) <= MAX_PAGES and not builtin:
                    raise DocumentError(f"Import between 1 and {MAX_PAGES} PDF pages per file.")
                if not len(pdf):
                    raise DocumentError("This PDF has no pages.")
                for index, page in enumerate(pdf):
                    # Page boundaries never get merged; extraction is not diagram interpretation or OCR.
                    text = page.get_text("text", sort=True).replace("\x00", "").translate(LIGATURES).strip()
                    total_text += len(text)
                    if total_text > MAX_TEXT and not builtin:
                        raise DocumentError("Too much extracted text. Split this manual into smaller PDFs.")
                    if len(re.sub(r"\W", "", text)) >= 20:
                        text_pages += 1
                    extracted.append((index + 1, page.get_label() or str(index + 1), text))
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("PDF could not be read. It may be damaged or use an unsupported format.") from exc

        document_id = str(uuid.uuid4())
        status = "indexed" if text_pages == len(extracted) else "partial" if text_pages else "needs_ocr"
        item = dict(id=document_id, title=title, machine=machine, variant=variant, revision=revision,
                    type=kind, sha256=digest, bytes=len(content), pages=len(extracted),
                    text_pages=text_pages, status=status, added_at=datetime.now(timezone.utc).isoformat(),
                    source="builtin" if builtin else "update", source_path=builtin and builtin["path"],
                    source_size=builtin and builtin["size"], source_mtime=builtin and builtin["mtime"],
                    superseded_by=None, url=url)
        destination = self.files / f"{document_id}.pdf"
        temporary = self.files / f"{document_id}.tmp"
        if not builtin:
            temporary.write_bytes(content)
        try:
            with self.connect() as db:
                db.execute(f"INSERT INTO documents ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))})",
                           tuple(item[c] for c in COLUMNS))
                for number, label, text in extracted:
                    db.execute("INSERT INTO pages VALUES (?,?,?,?)", (document_id, number, label, text))
                    if len(re.sub(r"\W", "", text)) < 20:
                        continue
                    for chunk in chunk_text(text):
                        db.execute("INSERT INTO passages(document_id,page,text,codes) VALUES(?,?,?,?)",
                                   (document_id, number, chunk, code_forms(chunk)))
                if supersedes:
                    db.execute("UPDATE documents SET superseded_by=? WHERE id=?", (document_id, supersedes))
                # Only a complete database record gets a permanent file name.
                if not builtin:
                    temporary.replace(destination)
        except sqlite3.IntegrityError:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            # Two concurrent identical imports should converge on the same stored document.
            with self.connect() as db:
                row = db.execute("SELECT * FROM documents WHERE sha256=? AND machine=? AND variant=? AND revision=? AND type=?",
                                 (digest, machine, variant, revision, kind)).fetchone()
            if row:
                return {**dict(row), "duplicate": True}
            raise
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        return {**item, "duplicate": False}

    def check_supersedes(self, target_id, machine, own_id=None):
        target = self.document(target_id)
        if target["machine"] != machine:
            raise DocumentError("An update can only replace a manual for the same machine.")
        if target_id == own_id:
            raise DocumentError("A manual cannot replace itself.")
        return target

    def set_supersedes(self, document_id, target_id):
        """Mark target_id as replaced by document_id (or clear what document_id replaces when target is None)."""
        with self.connect() as db:
            db.execute("UPDATE documents SET superseded_by=NULL WHERE superseded_by=?", (document_id,))
            if target_id:
                db.execute("UPDATE documents SET superseded_by=? WHERE id=?", (document_id, target_id))

    def replaces(self, document_id):
        with self.connect() as db:
            row = db.execute("SELECT id FROM documents WHERE superseded_by=?", (document_id,)).fetchone()
        return row["id"] if row else None

    def update(self, document_id, machine, variant, revision, kind, supersedes=None):
        """Correct metadata of an uploaded update. The PDF and its index are unchanged."""
        document = self.document(document_id)
        if document["source"] == "builtin":
            raise DocumentError("Built-in manuals are described in library/catalog.json. Upload an update instead.")
        self.check_machine(machine)
        if kind not in KINDS or (kind == "web") != (document["type"] == "web"):
            raise DocumentError("Choose a valid document type.")
        if supersedes:
            self.check_supersedes(supersedes, machine, document_id)
        try:
            with self.connect() as db:
                db.execute("UPDATE documents SET machine=?, variant=?, revision=?, type=? WHERE id=?",
                           (machine, variant, revision, kind, document_id))
                db.execute("UPDATE documents SET superseded_by=NULL WHERE superseded_by=?", (document_id,))
                if supersedes:
                    db.execute("UPDATE documents SET superseded_by=? WHERE id=?", (document_id, supersedes))
        except sqlite3.IntegrityError as exc:
            raise DocumentError("This PDF is already stored with the same machine, variant, revision and type.") from exc
        return self.document(document_id)

    def delete(self, document_id, allow_builtin=False):
        """Remove a document, its pages, search passages and cached page images. Replaced manuals become current again."""
        document = self.document(document_id)
        if document["source"] == "builtin" and not allow_builtin:
            raise DocumentError("Built-in manuals are part of the application. Remove them from the library folder instead.")
        with self.connect() as db:
            db.execute("UPDATE documents SET superseded_by=NULL WHERE superseded_by=?", (document_id,))
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
        if document["source"] != "builtin":
            (self.files / f"{document_id}.pdf").unlink(missing_ok=True)
        shutil.rmtree(self.cache / document_id, ignore_errors=True)

    # ---- built-in library -----------------------------------------------------------------
    def set_status(self, **values):
        with self.status_lock:
            self.library_status.update(values)

    def status(self):
        with self.status_lock:
            return {**self.library_status, "errors": list(self.library_status["errors"])}

    def read_catalog(self):
        """library/catalog.json is optional. Any PDF in library/<machine-id>/ is included."""
        catalog, errors = {}, []
        path = self.library / "catalog.json"
        if path.is_file():
            try:
                catalog = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(catalog, dict):
                    raise ValueError("catalog must be a JSON object")
            except (OSError, ValueError) as exc:
                errors.append(f"catalog.json could not be read: {exc}")
                catalog = {}
        machines = {}
        for entry in catalog.get("machines") or []:
            if isinstance(entry, dict) and MACHINE_ID.match(str(entry.get("id", ""))):
                machines[entry["id"]] = str(entry.get("name") or entry["id"])[:80]
            else:
                errors.append(f"Skipped machine entry {entry!r}: id must be lowercase letters, digits, - or _.")
        described = {}
        for entry in catalog.get("documents") or []:
            if isinstance(entry, dict) and entry.get("file"):
                described[str(entry["file"]).replace("\\", "/").strip("/").lower()] = entry
        return machines, described, errors

    def sync_library(self, lock=None):
        """Make the database mirror the built-in library folder. Safe to run on every start."""
        if not self.library:
            return
        self.set_status(state="scanning", done=0, total=0, current="", errors=[])
        if not self.library.is_dir():
            self.set_status(state="missing")
            return
        machines, described, errors = self.read_catalog()
        found = []
        for folder in sorted(p for p in self.library.iterdir() if p.is_dir()):
            if not MACHINE_ID.match(folder.name):
                continue
            pdfs = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
            if pdfs and folder.name not in machines:
                machines[folder.name] = folder.name
            found += pdfs
        with self.connect() as db:
            if machines:
                in_use = {row["machine"] for row in db.execute("SELECT DISTINCT machine FROM documents WHERE source='update'")}
                names = {**{m: m for m in in_use}, **machines}
                db.execute("DELETE FROM machines")
                db.executemany("INSERT INTO machines VALUES (?,?,?)",
                               [(key, name, i) for i, (key, name) in enumerate(names.items())])
            existing = {row["source_path"]: dict(row) for row in db.execute("SELECT * FROM documents WHERE source='builtin'")}
        self.set_status(total=len(found), errors=errors)
        seen = set()
        for done, pdf in enumerate(found):
            relative = pdf.relative_to(self.library).as_posix()
            seen.add(relative)
            self.set_status(current=relative, done=done)
            entry = described.get(relative.lower(), {})
            metadata = dict(title=str(entry.get("title") or pdf.name)[:220], machine=relative.split("/", 1)[0],
                            variant=str(entry.get("variant") or UNSPECIFIED_VARIANT)[:120],
                            revision=str(entry.get("revision") or "Not supplied")[:120],
                            kind=entry.get("type") if entry.get("type") in KINDS else "manual",
                            url=str(entry["url"])[:2000] if entry.get("url") else None)
            stat = pdf.stat()
            row = existing.get(relative)
            try:
                with lock or nullcontext():
                    if row and row["source_size"] == stat.st_size and row["source_mtime"] == stat.st_mtime:
                        if any(row[k] != metadata[k] for k in ("title", "machine", "variant", "revision", "url")) or row["type"] != metadata["kind"]:
                            with self.connect() as db:
                                db.execute("UPDATE documents SET title=?, machine=?, variant=?, revision=?, type=?, url=? WHERE id=?",
                                           (metadata["title"], metadata["machine"], metadata["variant"],
                                            metadata["revision"], metadata["kind"], metadata["url"], row["id"]))
                        continue
                    replaced_by = row and row["superseded_by"]
                    if row:  # The file changed: index the new copy.
                        self.delete(row["id"], allow_builtin=True)
                    item = self.ingest(pdf.read_bytes(), metadata["title"], metadata["machine"], metadata["variant"],
                                       metadata["revision"], metadata["kind"], url=metadata["url"],
                                       builtin={"path": relative, "size": stat.st_size, "mtime": stat.st_mtime})
                    if replaced_by and not item.get("duplicate"):
                        with self.connect() as db:
                            db.execute("UPDATE documents SET superseded_by=? WHERE id=?", (replaced_by, item["id"]))
            except (DocumentError, OSError, sqlite3.Error) as exc:
                errors.append(f"{relative}: {exc}")
                self.set_status(errors=errors)
        for relative, row in existing.items():
            if relative not in seen:  # Removed from the library folder.
                with lock or nullcontext():
                    self.delete(row["id"], allow_builtin=True)
        self.set_status(state="ready", done=len(found), current="", errors=errors)

    # ---- reading and search ---------------------------------------------------------------
    def page(self, document_id, number):
        document = self.document(document_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM pages WHERE document_id=? AND number=?", (document_id, number)).fetchone()
        if row is None:
            raise NotFound("That PDF page does not exist.")
        return {**dict(row), "title": document["title"], "pages": document["pages"]}

    def page_png(self, document_id, number):
        self.page(document_id, number)
        # Indexed PDFs never change under the same document ID, so a rendered page can be reused.
        cached = self.cache / document_id / f"{int(number)}.png"
        if cached.is_file():
            return cached.read_bytes()
        with PDF_LOCK, pymupdf.open(self.file(document_id)) as pdf:
            page = pdf[number - 1]
            longest = max(page.rect.width, page.rect.height, 1)
            scale = min(2, 1800 / longest)
            image = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            partial = cached.with_suffix(f".{uuid.uuid4().hex}.tmp")
            partial.write_bytes(image)
            partial.replace(cached)
        except OSError:
            pass  # Caching is an optimization; rendering still succeeded.
        return image

    def search(self, question, machine, document_id=None, limit=8):
        """Search one chosen manual, or every current (not replaced) manual for the machine."""
        if document_id:
            document = self.document(document_id)
            if document["machine"] != machine:
                raise DocumentError("Selected manual belongs to another machine. Select its workspace first.")
            scope, params = "d.id=?", [document_id]
        else:
            self.check_machine(machine)
            scope, params = "d.machine=? AND d.superseded_by IS NULL", [machine]
        terms = query_terms(question)
        if not terms:
            return []
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        with self.connect() as db:
            rows = db.execute(f"""
                SELECT p.id,p.page,p.text,pg.label AS page_label,bm25(passage_fts, 1.0, 2.0) AS score,
                       d.id AS document_id,d.title,d.revision,d.variant,d.type,d.source,d.url
                FROM passage_fts JOIN passages p ON p.id=passage_fts.rowid
                JOIN documents d ON d.id=p.document_id
                JOIN pages pg ON pg.document_id=p.document_id AND pg.number=p.page
                WHERE passage_fts MATCH ? AND {scope}
                ORDER BY score,d.title,p.page,p.id LIMIT ?
            """, (expression, *params, limit)).fetchall()
        return [dict(id=str(row["id"]), page=row["page"], page_label=row["page_label"], text=row["text"],
                     document_id=row["document_id"], title=row["title"], revision=row["revision"],
                     variant=row["variant"], type=row["type"], source=row["source"], url=row["url"]) for row in rows]


def chunk_text(text, size=1800):
    """Keep complete lines where possible and overlap one line for reading continuity."""
    chunk = ""
    for line in text.splitlines():
        parts = [line[i:i + size] for i in range(0, max(1, len(line)), size)]
        for part in parts:
            if len(chunk) + len(part) + 1 > size and chunk:
                yield chunk.strip()
                last = chunk.splitlines()[-1]
                chunk = last + "\n" if len(last) < 180 and len(last) + len(part) < size else ""
            chunk += part + "\n"
    if chunk.strip():
        yield chunk.strip()


STOP = set("a an and are as at be by can could do does for from get give how i in is it me my of on or please tell that the their this to use was what when where which with would you your find manual machine spec specification specifications model engine".split())


def query_terms(question):
    terms = [t for t in re.findall(r"[\w]+", question.lower(), flags=re.UNICODE) if t not in STOP and len(t) > 1]
    # "1R-0750" in a question also searches 1r0750; "1R0750" already matches the indexed codes column.
    extras = code_forms(question).split()
    if any(t in terms for t in ("torque", "tighten", "tightening")):
        extras.extend(("torque", "tighten", "tightening"))
    if "capacity" in terms:
        extras.extend(("capacities", "fill"))
    return list(dict.fromkeys(terms + extras))[:30]
