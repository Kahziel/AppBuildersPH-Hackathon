"""Built-in library, updates that replace manuals, and search across all of a machine's manuals. Fictional data only."""
import json
import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import ROOT, create_app
from backend.inference import LocalEngine
from backend.store import UNSPECIFIED_VARIANT
from tests.test_core import OfflineEngine, pdf_bytes


def write_library(folder, catalog=None, files=None):
    folder.mkdir(parents=True, exist_ok=True)
    if catalog is not None:
        (folder / 'catalog.json').write_text(json.dumps(catalog), encoding='utf-8')
    for name, pages in (files or {}).items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf_bytes(pages))


CATALOG = {
    'machines': [{'id': 'rig', 'name': 'Fictional rig'}, {'id': 'other', 'name': 'Other fictional rig'}],
    'documents': [
        {'file': 'rig/engine.pdf', 'title': 'Engine manual', 'variant': 'RIG-1 engine', 'revision': 'R1', 'type': 'manual'},
        {'file': 'rig/hydraulics/pump.pdf', 'title': 'Pump manual', 'variant': 'RIG-1 pump', 'revision': 'R4', 'type': 'manual'},
    ],
}
FILES = {
    'rig/engine.pdf': ['FICTIONAL ONLY. Cylinder head bolt torque: 40 N m then 90 degrees.'],
    'rig/hydraulics/pump.pdf': ['FICTIONAL ONLY. Pump mounting bolt torque: 95 N m.'],
    'other/misc.pdf': ['FICTIONAL ONLY. Other machine cover bolt torque: 7 N m.'],
}


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / 'library'
    write_library(folder, CATALOG, FILES)
    return folder


@pytest.fixture
def client(tmp_path, library):
    app = create_app(tmp_path / 'data', OfflineEngine(), library=library, sync=False)
    app.state.store.sync_library()
    with TestClient(app) as client:
        yield client


def docs(client, machine=None):
    return client.get('/api/documents' + (f'?machine={machine}' if machine else '')).json()['documents']


def ask_machine(client, question, machine='rig', **extra):
    return client.post('/api/ask', json={'question': question, 'machine': machine, 'search_only': True, **extra}).json()


def test_library_is_indexed_with_catalog_details_and_not_copied(client, tmp_path):
    rig = {d['title']: d for d in docs(client, 'rig')}
    assert set(rig) == {'Engine manual', 'Pump manual'}
    assert rig['Pump manual']['variant'] == 'RIG-1 pump' and rig['Pump manual']['revision'] == 'R4'
    assert all(d['source'] == 'builtin' for d in rig.values())
    assert not list((tmp_path / 'data' / 'manuals').glob('*.pdf'))  # read in place, no duplicate copy
    original = (tmp_path / 'library' / 'rig' / 'engine.pdf').read_bytes()
    assert client.get(f"/api/documents/{rig['Engine manual']['id']}/file").content == original
    assert client.get(f"/api/documents/{rig['Engine manual']['id']}/pages/1/image").status_code == 200
    status = client.get('/api/health').json()
    assert status['library']['state'] == 'ready' and status['builtin_documents'] == 3


def test_uncatalogued_pdf_and_machine_folder_are_included(client):
    machines = {m['id']: m['name'] for m in client.get('/api/machines').json()['machines']}
    assert machines == {'rig': 'Fictional rig', 'other': 'Other fictional rig'}
    misc = docs(client, 'other')[0]
    assert misc['title'] == 'misc.pdf' and misc['variant'] == UNSPECIFIED_VARIANT


def test_search_covers_every_current_manual_for_the_machine_only(client):
    result = ask_machine(client, 'bolt torque')
    titles = {m['title'] for m in result['matches']}
    assert titles == {'Engine manual', 'Pump manual'} and result['scope'] == 'machine'
    assert all('7 N m' not in m['text'] for m in result['matches'])
    pump = next(d for d in docs(client, 'rig') if d['title'] == 'Pump manual')
    narrowed = ask_machine(client, 'bolt torque', document_id=pump['id'])
    assert {m['title'] for m in narrowed['matches']} == {'Pump manual'} and narrowed['scope'] == 'manual'
    assert client.post('/api/ask', json={'question': 'bolt', 'machine': 'mars'}).status_code == 422


def test_update_replaces_builtin_manual_and_deleting_it_restores_the_original(client):
    pump = next(d for d in docs(client, 'rig') if d['title'] == 'Pump manual')
    update = client.post('/api/documents', data={'machine': 'rig', 'variant': 'RIG-1 pump', 'revision': 'R5', 'kind': 'manual', 'supersedes': pump['id']},
                         files={'file': ('pump-r5.pdf', pdf_bytes(['FICTIONAL ONLY. Pump mounting bolt torque: 100 N m (revised).']), 'application/pdf')})
    assert update.status_code == 201, update.text
    update = update.json()
    assert update['source'] == 'update'
    old = client.get('/api/documents').json()['documents']
    assert next(d for d in old if d['id'] == pump['id'])['superseded_by'] == update['id']
    texts = ' '.join(m['text'] for m in ask_machine(client, 'pump bolt torque')['matches'])
    assert '100 N m' in texts and '95 N m' not in texts
    # The replaced manual can still be opened and searched on purpose.
    assert '95 N m' in ask_machine(client, 'pump bolt torque', document_id=pump['id'])['matches'][0]['text']
    assert client.delete(f"/api/documents/{update['id']}").status_code == 200
    assert next(d for d in docs(client, 'rig') if d['id'] == pump['id'])['superseded_by'] is None
    assert '95 N m' in ' '.join(m['text'] for m in ask_machine(client, 'pump bolt torque')['matches'])


def test_update_rules(client):
    pump = next(d for d in docs(client, 'rig') if d['title'] == 'Pump manual')
    misc = docs(client, 'other')[0]
    assert client.delete(f"/api/documents/{pump['id']}").status_code == 422
    assert client.patch(f"/api/documents/{pump['id']}", json={'machine': 'rig', 'variant': 'x'}).status_code == 422
    wrong_machine = client.post('/api/documents', data={'machine': 'rig', 'variant': 'v', 'supersedes': misc['id']},
                                files={'file': ('x.pdf', pdf_bytes(['FICTIONAL ONLY. Text for a wrong-machine update.']), 'application/pdf')})
    assert wrong_machine.status_code == 422
    unknown = client.post('/api/documents', data={'machine': 'mars', 'variant': 'v'},
                          files={'file': ('x.pdf', pdf_bytes(['FICTIONAL ONLY. Text for an unknown machine.']), 'application/pdf')})
    assert unknown.status_code == 422
    # Editing an update can change which manual it replaces.
    update = client.post('/api/documents', data={'machine': 'rig', 'variant': 'RIG-1 pump', 'revision': 'R6'},
                         files={'file': ('r6.pdf', pdf_bytes(['FICTIONAL ONLY. Revised pump text R6.']), 'application/pdf')}).json()
    edited = client.patch(f"/api/documents/{update['id']}", json={'machine': 'rig', 'variant': 'RIG-1 pump', 'revision': 'R6', 'kind': 'manual', 'supersedes': pump['id']})
    assert edited.status_code == 200
    assert next(d for d in docs(client, 'rig') if d['id'] == pump['id'])['superseded_by'] == update['id']
    client.patch(f"/api/documents/{update['id']}", json={'machine': 'rig', 'variant': 'RIG-1 pump', 'revision': 'R6', 'kind': 'manual', 'supersedes': None})
    assert next(d for d in docs(client, 'rig') if d['id'] == pump['id'])['superseded_by'] is None


def test_resync_skips_unchanged_reindexes_changed_and_removes_deleted(tmp_path, library):
    app = create_app(tmp_path / 'data', OfflineEngine(), library=library, sync=False)
    store = app.state.store
    store.sync_library()
    before = {d['source_path']: d['id'] for d in store.documents()}
    store.sync_library()
    assert {d['source_path']: d['id'] for d in store.documents()} == before
    catalog = json.loads((library / 'catalog.json').read_text())
    catalog['documents'][0]['revision'] = 'R2'
    (library / 'catalog.json').write_text(json.dumps(catalog))
    engine = library / 'rig' / 'engine.pdf'
    engine.write_bytes(pdf_bytes(['FICTIONAL ONLY. Cylinder head bolt torque: 45 N m (changed file).']))
    os.utime(engine, (time.time() + 5, time.time() + 5))
    (library / 'other' / 'misc.pdf').unlink()
    store.sync_library()
    after = {d['source_path']: d for d in store.documents()}
    assert after['rig/engine.pdf']['id'] != before['rig/engine.pdf'] and after['rig/engine.pdf']['revision'] == 'R2'
    assert '45 N m' in store.search('cylinder head', 'rig')[0]['text']
    assert after['rig/hydraulics/pump.pdf']['id'] == before['rig/hydraulics/pump.pdf']
    assert 'other/misc.pdf' not in after


def test_broken_catalog_and_bad_pdf_are_reported_not_fatal(tmp_path):
    folder = tmp_path / 'library'
    write_library(folder, files={'rig/good.pdf': ['FICTIONAL ONLY. Good manual text about the alternator belt.']})
    (folder / 'catalog.json').write_text('{ not json', encoding='utf-8')
    (folder / 'rig' / 'broken.pdf').write_bytes(b'not a pdf')
    app = create_app(tmp_path / 'data', OfflineEngine(), library=folder, sync=False)
    app.state.store.sync_library()
    status = app.state.store.status()
    assert status['state'] == 'ready' and len(status['errors']) == 2
    assert [d['title'] for d in app.state.store.documents()] == ['good.pdf']


def test_missing_library_folder_still_starts(tmp_path):
    app = create_app(tmp_path / 'data', OfflineEngine(), library=tmp_path / 'nowhere', sync=False)
    app.state.store.sync_library()
    assert app.state.store.status()['state'] == 'missing'
    assert {m['id'] for m in app.state.store.machines()} == {'cat', 'deere', 'volvo', 'training'}


def test_background_sync_runs_on_startup(tmp_path, library):
    with TestClient(create_app(tmp_path / 'data', OfflineEngine(), library=library)) as client:
        for _ in range(100):
            if client.get('/api/health').json()['library']['state'] == 'ready':
                break
            time.sleep(.05)
        assert client.get('/api/health').json()['builtin_documents'] == 3


def test_shipped_library_catalog_is_valid(tmp_path):
    app = create_app(tmp_path / 'data', OfflineEngine(), library=ROOT / 'library', sync=False)
    app.state.store.sync_library()
    assert app.state.store.status()['errors'] == []
    training = app.state.store.documents('training')
    assert training and training[0]['variant'] == 'TD-01 (fictional)'


def test_ai_receives_manual_details_for_each_passage(client):
    engine = LocalEngine()
    passages = ask_machine(client, 'bolt torque')['matches']
    captured = []

    def reply(path, payload=None, timeout=3):
        if path == '/api/tags':
            return {'models': [{'name': 'qwen3:4b'}]}
        captured.append(json.loads(payload['messages'][1]['content']))
        pump = next(p for p in passages if '95 N m' in p['text'])
        return {'message': {'content': json.dumps({'status': 'supported', 'evidence': [{'id': pump['id'], 'quote': 'Pump mounting bolt torque: 95 N m.'}]})}}

    with patch.object(engine, 'request', side_effect=reply):
        selected, _ = engine.select('pump bolt torque', {'machine': 'Fictional rig'}, passages)
    assert selected[0]['title'] == 'Pump manual'
    sent = captured[0]
    assert sent['search_scope'] == {'machine': 'Fictional rig'}
    assert {p['manual']['title'] for p in sent['passages']} == {'Engine manual', 'Pump manual'}
