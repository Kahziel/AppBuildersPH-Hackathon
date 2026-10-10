"""Run the laptop's search on a library database (used to check the phone gives identical results)."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.store import Store, query_terms  # noqa: E402

database, cases = sys.argv[1], json.loads(sys.argv[2])
with tempfile.TemporaryDirectory() as tmp:
    shutil.copyfile(database, Path(tmp) / "torquedoc.sqlite3")
    store = Store(Path(tmp))
    out = [{"terms": query_terms(q), "ids": [p["id"] for p in store.search(q, m, d)]} for q, m, d in cases]
print(json.dumps(out))
