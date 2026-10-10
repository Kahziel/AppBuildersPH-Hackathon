"""Index the built-in library with the desktop engine and save a phone-ready copy of the search database.

The phone runs the same SQLite full-text index (FTS5, porter stemming, part-number codes),
so phone searches return the same passages as the laptop.
"""
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.store import Store  # noqa: E402


def main(out_db, out_info):
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp), ROOT / "library")
        store.sync_library()
        status = store.status()
        for error in status["errors"]:
            print("WARNING:", error)
        documents = store.documents()
        machines = store.machines()
        # A clean single-file copy: the phone loads it directly, so no WAL side files.
        source, target = sqlite3.connect(store.path), sqlite3.connect(out_db)
        source.backup(target)
        source.close()
        target.execute("PRAGMA journal_mode=DELETE")
        target.execute("VACUUM")
        target.close()
    info = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "documents": len(documents), "pages": sum(d["pages"] for d in documents),
            "machines": [m["id"] for m in machines], "errors": status["errors"]}
    Path(out_info).write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"Library database: {len(documents)} documents, {info['pages']} pages -> {out_db}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
