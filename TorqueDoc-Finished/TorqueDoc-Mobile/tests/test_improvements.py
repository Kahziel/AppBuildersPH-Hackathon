"""Search recall, metadata correction, deletion and quote matching. Fictional data only."""
import json
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.inference import LocalEngine, normalize
from backend.store import SCHEMA_VERSION, Store, code_forms
from tests.test_core import OfflineEngine, ask, pdf_bytes, upload

MANUAL = [
    "FICTIONAL ONLY. Hydraulic pump mounting bolts: tighten to 95 N m. Filter element part number 1R-0750.",
    "FICTIONAL ONLY. Fault code E-360 indicates low coolant level. Sensor P/N 3E4512.",
    "FICTIONAL ONLY. Replace the fuel filters every 500 hours of operation.",
]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, OfflineEngine())) as client:
        yield client


def pages(client, doc, question):
    return [m['page'] for m in ask(client, doc, question, search_only=True).json()['matches']]


@pytest.mark.parametrize('question,page', [
    ('bolt', 1), ('mounting bolt', 1), ('replacing filter', 3), ('fuel filter interval', 3),
    ('1R0750', 1), ('1R-0750', 1), ('1r0750', 1), ('E360', 2), ('E-360', 2), ('3E-4512', 2),
])
def test_stemming_and_code_variants(client, question, page):
    doc = upload(client, pdf_bytes(MANUAL)).json()
    assert pages(client, doc, question)[0] == page


def test_code_forms_ignore_plain_words_and_require_digits():
    assert code_forms('Use 1R-0750 and E-360, not well-known or N-m.') == '1r0750 e360'


def test_edit_metadata_and_conflict(client):
    content = pdf_bytes(MANUAL)
    doc = upload(client, content).json()
    edited = client.patch(f"/api/documents/{doc['id']}", json={'machine':'training', 'variant':'TD-02 (fictional)', 'revision':'R9', 'kind':'bulletin'})
    assert edited.status_code == 200, edited.text
    assert edited.json()['variant'] == 'TD-02 (fictional)' and edited.json()['type'] == 'bulletin'
    assert ask(client, edited.json(), 'hydraulic pump', search_only=True).json()['matches'][0]['variant'] == 'TD-02 (fictional)'
    moved = client.patch(f"/api/documents/{doc['id']}", json={'machine':'cat', 'variant':'TD-02 (fictional)', 'revision':'R9', 'kind':'bulletin'}).json()
    assert len(client.get('/api/documents?machine=cat').json()['documents']) == 1 and moved['machine'] == 'cat'
    assert client.patch(f"/api/documents/{doc['id']}", json={'machine':'mars', 'variant':'x'}).status_code == 422
    # Same PDF already stored with identical metadata is refused rather than silently merged.
    other = upload(client, content).json()
    assert other['id'] != doc['id']
    clash = client.patch(f"/api/documents/{other['id']}", json={'machine':'cat', 'variant':'TD-02 (fictional)', 'revision':'R9', 'kind':'bulletin'})
    assert clash.status_code == 422


def test_delete_removes_file_index_and_cached_pages(client, tmp_path):
    content = pdf_bytes(['Intro page for a fictional rig.', 'FICTIONAL ONLY. Cover bolt torque: 12 N m.'])
    doc = upload(client, content).json()
    assert client.get(f"/api/documents/{doc['id']}/pages/2/image").status_code == 200
    assert (tmp_path / 'cache' / doc['id'] / '2.png').is_file()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert not (tmp_path / 'manuals' / f"{doc['id']}.pdf").exists()
    assert not (tmp_path / 'cache' / doc['id']).exists()
    assert client.get('/api/documents').json()['documents'] == []
    assert ask(client, doc).status_code == 404
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404
    with sqlite3.connect(tmp_path / 'torquedoc.sqlite3') as db:
        assert db.execute("SELECT count(*) FROM passage_fts WHERE passage_fts MATCH 'cover'").fetchone()[0] == 0
    # The identical PDF can be imported again afterwards.
    assert upload(client, content).json()['duplicate'] is False


def test_ask_returns_highlight_terms(client):
    doc = upload(client).json()
    assert 'torque' in ask(client, doc, 'Cover bolt torque', search_only=True).json()['terms']


def test_existing_version_1_library_is_upgraded(tmp_path):
    with sqlite3.connect(tmp_path / 'torquedoc.sqlite3') as db:
        db.executescript("""
            CREATE TABLE documents (id TEXT PRIMARY KEY, title TEXT NOT NULL, machine TEXT NOT NULL,
                variant TEXT NOT NULL, revision TEXT NOT NULL, type TEXT NOT NULL, sha256 TEXT NOT NULL,
                bytes INTEGER NOT NULL, pages INTEGER NOT NULL, text_pages INTEGER NOT NULL,
                status TEXT NOT NULL, added_at TEXT NOT NULL, UNIQUE(sha256, machine, variant, revision, type));
            CREATE TABLE pages (document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                number INTEGER NOT NULL, label TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY(document_id, number));
            CREATE TABLE passages (id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id)
                ON DELETE CASCADE, page INTEGER NOT NULL, text TEXT NOT NULL);
            CREATE VIRTUAL TABLE passage_search USING fts5(text, content='passages', content_rowid='id', tokenize='unicode61');
            CREATE TRIGGER passages_insert AFTER INSERT ON passages BEGIN
                INSERT INTO passage_search(rowid,text) VALUES(new.id,new.text); END;
            INSERT INTO documents VALUES ('old','Old.pdf','training','TD-01','R1','manual','x',1,1,1,'indexed','2026-01-01');
            INSERT INTO pages VALUES ('old',1,'1','FICTIONAL. Cover bolts 12 N m. Part 1R-0750.');
            INSERT INTO passages(document_id,page,text) VALUES ('old',1,'FICTIONAL. Cover bolts 12 N m. Part 1R-0750.');
        """)
    store = Store(tmp_path)
    assert store.search('bolt', 'training', 'old')[0]['page'] == 1
    assert store.search('1R0750', 'training', 'old')
    Store(tmp_path)  # Second start does not rebuild or fail.
    with sqlite3.connect(tmp_path / 'torquedoc.sqlite3') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION


def test_interrupted_import_leftovers_are_removed(tmp_path):
    (tmp_path / 'manuals').mkdir(parents=True)
    (tmp_path / 'manuals' / 'abc.tmp').write_bytes(b'%PDF-partial')
    Store(tmp_path)
    assert not (tmp_path / 'manuals' / 'abc.tmp').exists()


def test_quote_normalization_tolerates_typography_not_values():
    assert normalize('Tighten to 95-100 N m') in normalize('tighten to 95–100 N m.')
    assert normalize('“dry” threads') == normalize('"Dry" threads')
    assert normalize('Tighten to 95-110 N m') not in normalize('tighten to 95–100 N m.')


def test_typographic_quote_is_accepted_by_engine():
    engine = LocalEngine()
    passage = {'id':'4', 'page':1, 'text':'FICTIONAL ONLY. Tighten to 95–100 N m with dry threads.'}
    def reply(path, payload=None, timeout=3):
        if path == '/api/tags':
            return {'models':[{'name':'qwen3:4b'}]}
        return {'message':{'content':json.dumps({'status':'supported','evidence':[{'id':'4','quote':'tighten to 95-100 N m with dry threads'}]})}}
    with patch.object(engine, 'request', side_effect=reply):
        selected, _ = engine.select('torque', {'title':'T','variant':'V','revision':'R'}, [passage])
    assert selected == [passage]


def test_model_choice_is_allowlisted(tmp_path, monkeypatch):
    assert LocalEngine(model='qwen3:8b').model == 'qwen3:8b'
    with pytest.raises(ValueError):
        LocalEngine(model='qwen3:4b-cloud')
    monkeypatch.setenv('TORQUEDOC_MODEL', 'qwen3:1.7b')
    app = create_app(tmp_path)
    assert app.state.engine.model == 'qwen3:1.7b'


def test_ping_is_instant_and_engine_status_is_cached(tmp_path):
    import time
    from tests.test_core import OfflineEngine
    calls = []

    class CountingEngine(OfflineEngine):
        def health(self, fresh=False):
            calls.append(fresh)
            return super().health()

    with TestClient(create_app(tmp_path, CountingEngine())) as client:
        assert client.get('/api/ping').json() == {'app': 'torquedoc', 'ready': True}
        assert calls == []
        client.get('/api/health'); client.get('/api/health?fresh=true')
        assert calls == [False, True]
    engine = LocalEngine('http://127.0.0.1:1')
    checks = []
    engine.check = lambda: checks.append(1) or {'state': 'unavailable'}
    engine.health(); engine.health()
    assert len(checks) == 1
    engine.health(fresh=True)
    assert len(checks) == 2
