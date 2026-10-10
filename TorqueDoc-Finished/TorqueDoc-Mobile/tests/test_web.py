"""Web page snapshots: cleaning, safety checks, offline storage and citation. Uses a local fixture server, never the internet."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend import web
from backend.app import create_app
from tests.test_core import OfflineEngine, pdf_bytes

PAGE = """<!doctype html><html><head><title>Fictional Rig Spec Sheet</title><style>.x{color:red}</style>
<script>alert('never')</script></head><body><nav>Home | Products | Login</nav>
<main><h1>Fictional rig RIG-1 specifications</h1><p>FICTIONAL ONLY. Track tension bolt torque: 33 N m &amp; check daily.</p>
<table><tr><th>Item</th><th>Value</th></tr><tr><td>Hydraulic tank</td><td>120 L (fictional)</td></tr></table>
<ul><li>Engine oil: 18 L (fictional)</li></ul><p>""" + "Filler text about the fictional rig for testing. " * 12 + """</p>
<img src="x.png" alt="Rig photo"><form><input name="q"></form></main><footer>Copyright footer text</footer></body></html>"""


class Site(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        routes = {
            '/spec': (200, 'text/html; charset=utf-8', PAGE.encode()),
            '/brochure.pdf': (200, 'application/pdf', pdf_bytes(['FICTIONAL ONLY. Brochure: bucket pin torque 210 N m.'])),
            '/empty': (200, 'text/html', b'<html><body><div id="app"></div><script>render()</script></body></html>'),
            '/image': (200, 'image/png', b'\x89PNG....'),
        }
        if self.path == '/moved':
            self.send_response(302); self.send_header('Location', '/spec'); self.end_headers(); return
        status, kind, body = routes.get(self.path, (404, 'text/plain', b'missing'))
        self.send_response(status); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope='module')
def site():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()


def local_fetch(url, allow_private=False):
    return web.fetch(url, allow_private=True)


@pytest.fixture
def client(tmp_path):
    library = tmp_path / 'library'
    (library / 'rig').mkdir(parents=True)
    (library / 'catalog.json').write_text(json.dumps({'machines': [{'id': 'rig', 'name': 'Fictional rig'}]}))
    app = create_app(tmp_path / 'data', OfflineEngine(), library=library, sync=False, fetcher=local_fetch)
    app.state.store.sync_library()
    with TestClient(app) as client:
        yield client


def test_snapshot_keeps_content_drops_page_clutter_and_labels_the_source(site):
    pdf, title, final = web.save_page(site + '/spec', fetcher=local_fetch)
    assert title == 'Fictional Rig Spec Sheet' and final == site + '/spec'
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        text = ' '.join(page.get_text() for page in doc)
    assert 'WEB SOURCE' in text and 'not an OEM service manual' in text and site + '/spec' in text
    assert '33 N m & check daily' in text and 'Hydraulic tank' in text and '120 L' in text and 'Engine oil' in text
    assert '[image: Rig photo]' in text
    for clutter in ('alert', 'never', 'Home | Products', 'Copyright footer', 'color:red'):
        assert clutter not in text


def test_pdf_redirect_empty_and_unsupported_pages(site):
    pdf, _, _ = web.save_page(site + '/brochure.pdf', fetcher=local_fetch)
    assert pdf.startswith(b'%PDF-')
    assert web.save_page(site + '/moved', fetcher=local_fetch)[2] == site + '/spec'
    with pytest.raises(web.WebError, match='almost no readable text'):
        web.save_page(site + '/empty', fetcher=local_fetch)
    with pytest.raises(web.WebError, match='image/png'):
        web.save_page(site + '/image', fetcher=local_fetch)
    with pytest.raises(web.WebError, match='error 404'):
        web.save_page(site + '/nothing', fetcher=local_fetch)


@pytest.mark.parametrize('url', ['ftp://example.com/x', 'file:///etc/passwd', 'https://user:pw@example.com/', 'example.com'])
def test_only_plain_public_web_addresses(url):
    with pytest.raises(web.WebError):
        web.check_url(url)


def test_local_and_private_addresses_are_refused(site):
    for url in (site + '/spec', 'http://localhost/', 'http://10.0.0.5/', 'http://169.254.169.254/latest/'):
        with pytest.raises(web.WebError, match='Only public websites'):
            web.check_url(url)


def test_saved_web_page_is_searched_and_cited_offline(client, site):
    saved = client.post('/api/web', json={'url': site + '/spec', 'machine': 'rig', 'variant': 'RIG-1 (fictional)'})
    assert saved.status_code == 201, saved.text
    doc = saved.json()
    assert doc['type'] == 'web' and doc['source'] == 'update' and doc['url'] == site + '/spec'
    assert doc['title'] == 'Fictional Rig Spec Sheet' and doc['revision'].startswith('Web page saved')
    result = client.post('/api/ask', json={'question': 'track tension bolt torque', 'machine': 'rig', 'search_only': True}).json()
    match = result['matches'][0]
    assert '33 N m' in match['text'] and match['type'] == 'web' and match['url'] == site + '/spec'
    assert client.get(f"/api/documents/{doc['id']}/pages/1/image").status_code == 200
    # Web pages can be deleted like any update.
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200


def test_web_page_errors_are_reported(client, site):
    response = client.post('/api/web', json={'url': site + '/empty', 'machine': 'rig', 'variant': 'v'})
    assert response.status_code == 422 and 'readable text' in response.json()['detail']
    assert client.post('/api/web', json={'url': site + '/spec', 'machine': 'mars', 'variant': 'v'}).status_code == 422
    assert client.post('/api/web', json={'url': 'ftp://x.example/a', 'machine': 'rig', 'variant': 'v'}).status_code == 422


def test_catalog_web_sources_become_builtin_offline_documents(tmp_path, site):
    library = tmp_path / 'library'
    (library / 'rig').mkdir(parents=True)
    (library / 'catalog.json').write_text(json.dumps({
        'machines': [{'id': 'rig', 'name': 'Fictional rig'}],
        'web_sources': [{'url': site + '/spec', 'machine': 'rig', 'title': 'Rig spec sheet', 'variant': 'RIG-1 (fictional)'},
                        {'url': site + '/empty', 'machine': 'rig', 'title': 'Broken page'}]}))
    app = create_app(tmp_path / 'data', OfflineEngine(), library=library, sync=False, fetcher=local_fetch)
    with TestClient(app) as client:
        assert client.post('/api/library/web-sources').status_code == 202
        for _ in range(200):
            status = client.get('/api/health').json()['web_sources']
            if status['state'] == 'done':
                break
            threading.Event().wait(.05)
        assert status['state'] == 'done' and status['listed'] == 2 and status['saved'] == 1
        assert len(status['errors']) == 1 and 'Broken page' not in status['errors'][0] and '/empty' in status['errors'][0]
        doc = client.get('/api/documents?machine=rig').json()['documents'][0]
        assert doc['source'] == 'builtin' and doc['type'] == 'web' and doc['url'] == site + '/spec' and doc['title'] == 'Rig spec sheet'
        assert (library / doc['source_path']).is_file() and doc['source_path'].startswith('rig/web/')
    catalog = json.loads((library / 'catalog.json').read_text())
    assert catalog['documents'][0]['url'] == site + '/spec' and len(catalog['web_sources']) == 2
    # Offline afterwards: a fresh start indexes the saved snapshot without any download.
    restarted = create_app(tmp_path / 'data2', OfflineEngine(), library=library, sync=False)
    restarted.state.store.sync_library()
    assert restarted.state.store.search('track tension', 'rig')[0]['url'] == site + '/spec'


def test_shipped_catalog_lists_web_sources_for_each_machine():
    from backend.app import ROOT
    catalog = json.loads((ROOT / 'library' / 'catalog.json').read_text(encoding='utf-8'))
    machines = {m['id'] for m in catalog['machines']}
    assert {s['machine'] for s in catalog['web_sources']} == {'cat', 'deere', 'volvo'} <= machines
    assert all(s['url'].startswith('https://') and 'verify' in s['variant'] for s in catalog['web_sources'])


def test_ligatures_are_spelled_out_so_words_match(client):
    html = '<html><head><title>Ligature page</title></head><body><p>' + 'Replace the hydraulic filter and grease fitting at the office. ' * 6 + '</p></body></html>'
    store = client.app.state.store
    pdf, _ = web.snapshot(html.encode(), 'text/html', 'utf-8', 'https://example.com/lig')
    doc = store.ingest(pdf, 'Ligature page', 'rig', 'RIG-1', 'R1', 'web', url='https://example.com/lig')
    for word in ('filter', 'fitting', 'office'):
        assert store.search(word, 'rig', doc['id']), word
    assert not any(0xFB00 <= ord(c) <= 0xFB06 for c in store.page(doc['id'], 1)['text'])


def test_existing_ligature_text_is_repaired_on_upgrade(tmp_path):
    import sqlite3
    from backend.store import Store
    store = Store(tmp_path)
    doc = store.ingest(pdf_bytes(['FICTIONAL ONLY. Change the oil filter every 250 hours of fictional operation.']), 'Old', 'cat', 'V', 'R', 'manual')
    with sqlite3.connect(tmp_path / 'torquedoc.sqlite3') as db:
        for table in ('pages', 'passages'):
            db.execute(f"UPDATE {table} SET text=replace(text, 'filter', 'ﬁlter')")
        db.execute("INSERT INTO passage_fts(passage_fts) VALUES('rebuild')")
        db.execute('PRAGMA user_version=4')
    upgraded = Store(tmp_path)
    assert upgraded.search('filter', 'cat', doc['id'])
    assert 'filter' in upgraded.page(doc['id'], 1)['text']
