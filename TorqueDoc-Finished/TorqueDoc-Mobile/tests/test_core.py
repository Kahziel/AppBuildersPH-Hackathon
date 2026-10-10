"""Core acceptance checks use fictional PDFs and a controlled Ollama response, never OEM values."""
import json
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.inference import LocalEngine


class OfflineEngine:
    def health(self, fresh=False):
        return {"state": "unavailable", "model": "qwen3:4b", "message": "Test engine is offline."}

    def select(self, *args):
        return None, "Test engine is offline. Showing keyword matches only."


def pdf_bytes(pages, labels=False):
    with pymupdf.open() as pdf:
        for text in pages:
            page = pdf.new_page()
            if text:
                page.insert_textbox(pymupdf.Rect(40, 40, 540, 780), text, fontsize=12)
        if labels:
            pdf.set_page_labels([{"startpage": 0, "prefix": "TD-", "style": "D", "firstpagenum": 7}])
        return pdf.tobytes()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, OfflineEngine())) as client:
        yield client


def upload(client, content=None, **metadata):
    data = {"machine": "training", "variant": "Training rig TD-01 (FICTIONAL)", "revision": "TRAINING R1", "kind": "manual", **metadata}
    return client.post('/api/documents', files={"file": ("fictional.pdf", content or pdf_bytes([
        "FICTIONAL TRAINING RIG TD-01. Not a service manual. Introduction.",
        "FICTIONAL TRAINING ONLY. Cover bolt torque: 12 N m. Use a dry thread.\nTighten the four cover bolts in the numbered order shown on the drawing.\nSensor code TR-204 identifies the training connector."
    ], labels=True), "application/pdf")}, data=data)


def ask(client, doc, question='Cover bolt torque', **extra):
    return client.post('/api/ask', json={"question": question, "document_id": doc['id'], "machine": doc['machine'], **extra})


def test_upload_search_citation_original_and_page_render(client):
    data = pdf_bytes(["Introduction to a fictional training rig only.", "Cover bolt torque: 12 N m. FICTIONAL ONLY. Use dry threads."], labels=True)
    response = upload(client, data)
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc['status'] == 'indexed' and doc['pages'] == 2
    result = ask(client, doc).json()
    assert result['status'] == 'search_only' and result['evidence'] == []
    assert result['matches'][0]['page'] == 2
    assert result['matches'][0]['page_label'] == 'TD-8'
    assert result['matches'][0]['revision'] == 'TRAINING R1'
    assert '12 N m' in result['matches'][0]['text']
    assert client.get(f"/api/documents/{doc['id']}/file").content == data
    image = client.get(f"/api/documents/{doc['id']}/pages/2/image")
    assert image.status_code == 200 and image.content.startswith(b'\x89PNG')
    assert 'immutable' in image.headers['cache-control']
    assert client.get(f"/api/documents/{doc['id']}/pages/2").headers['cache-control'] == 'no-store'
    assert client.get(f"/api/documents/{doc['id']}/pages/99").status_code == 404


def test_no_matches_no_answer_and_machine_boundary(client):
    doc = upload(client).json()
    result = ask(client, doc, 'extraterrestrial fluxcapacitance').json()
    assert result['status'] == 'not_found' and not result['evidence'] and not result['matches']
    assert ask(client, doc, machine='cat').status_code == 422
    other = upload(client, pdf_bytes(['Different manual: cover bolt torque 999 N m. FICTIONAL ONLY.']), machine='cat').json()
    result = ask(client, doc, search_only=True).json()
    assert all(p['document_id'] == doc['id'] and '999' not in p['text'] for p in result['matches'])
    assert len(client.get('/api/documents?machine=cat').json()['documents']) == 1
    assert other['id'] != doc['id']


def test_duplicate_and_revision_are_separate(client):
    content = pdf_bytes(['Fictional training manual. Cover bolt torque is a test value only.'])
    one, two = upload(client, content).json(), upload(client, content).json()
    assert one['id'] == two['id'] and two['duplicate']
    updated = upload(client, content, revision='TRAINING R2').json()
    assert updated['id'] != one['id']
    assert len(client.get('/api/documents').json()['documents']) == 2


def test_scanned_partial_corrupt_and_encrypted_pdf(client):
    scanned = upload(client, pdf_bytes([''])).json()
    assert scanned['status'] == 'needs_ocr'
    assert ask(client, scanned).json()['status'] == 'not_found'
    partial = upload(client, pdf_bytes(['A fictional page with enough searchable text.', ''])).json()
    assert partial['status'] == 'partial' and partial['text_pages'] == 1
    assert upload(client, b'not a pdf').status_code == 422
    with pymupdf.open() as pdf:
        pdf.new_page()
        encrypted = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='reader')
    assert upload(client, encrypted).status_code == 422


def test_persistence_across_app_restart(tmp_path):
    with TestClient(create_app(tmp_path, OfflineEngine())) as first:
        doc = upload(first).json()
    with TestClient(create_app(tmp_path, OfflineEngine())) as restarted:
        assert restarted.get('/api/documents').json()['documents'][0]['id'] == doc['id']
        assert ask(restarted, doc, 'TR-204', search_only=True).json()['matches']


def test_local_only_and_private_files(client):
    assert client.get('/api/health', headers={'host':'evil.example'}).status_code == 403
    assert client.post('/api/ask', headers={'origin':'https://evil.example'}, json={}).status_code == 403
    for path in ['/backend/app.py', '/data/torquedoc.sqlite3', '/requirements.txt', '/.venv/pyvenv.cfg']:
        assert client.get(path).status_code == 404
    with pytest.raises(ValueError):
        LocalEngine('https://api.example.com')
    with pytest.raises(ValueError):
        LocalEngine(model='some-cloud-model')


def test_structured_evidence_selection_and_invented_quote_rejection():
    engine = LocalEngine()
    passage = {'id':'7', 'page':2, 'text':'FICTIONAL ONLY. Cover bolt torque: 12 N m. Use dry threads.'}
    document = {'title':'Training manual', 'variant':'TD-01', 'revision':'TRAINING R1'}
    captured = []
    def reply(path, payload=None, timeout=3):
        if path == '/api/tags':
            return {'models':[{'name':'qwen3:4b'}]}
        captured.append(payload)
        return {'message':{'content':json.dumps({'status':'supported', 'evidence':[{'id':'7','quote':'Cover bolt torque: 12 N m.'}]})}}
    with patch.object(engine, 'request', side_effect=reply):
        selected, _ = engine.select('Cover bolt torque', document, [passage])
    assert selected == [passage]  # display original text, not generated paraphrases
    assert captured[0]['stream'] is False and captured[0]['think'] is False
    assert captured[0]['format']['type'] == 'object'
    def forged(path, payload=None, timeout=3):
        if path == '/api/tags':
            return {'models':[{'name':'qwen3:4b'}]}
        return {'message':{'content':json.dumps({'status':'supported', 'evidence':[{'id':'7','quote':'Cover bolt torque: 900 N m.'}]})}}
    with patch.object(engine, 'request', side_effect=forged):
        selected, message = engine.select('Cover bolt torque', document, [passage])
    assert selected is None and 'could not be checked' in message


@pytest.mark.parametrize('response', [
    {'status':'supported','evidence':[{'id':'unknown','quote':'Cover bolt torque: 12 N m.'}]},
    {'status':'supported','evidence':[]},
    {'status':'not_found','evidence':[]},
    {'unstructured':'anything'},
])
def test_model_refusal_and_malformed_output(response):
    engine = LocalEngine()
    def reply(path, payload=None, timeout=3):
        return {'models':[{'name':'qwen3:4b'}]} if path == '/api/tags' else {'message':{'content':json.dumps(response)}}
    with patch.object(engine, 'request', side_effect=reply):
        selected, _ = engine.select('Cover bolt torque', {'title':'Test','variant':'TD-01','revision':'R1'}, [{'id':'1','page':1,'text':'Cover bolt torque: 12 N m. FICTIONAL ONLY.'}])
    assert selected == ([] if response.get('status') == 'not_found' else None)


def test_ollama_http_contract_and_supported_api_answer(tmp_path):
    """Exercise real loopback HTTP with a controlled protocol fixture, not a language model."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    requests = []

    class OllamaFixture(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            assert self.path == '/api/tags'
            self.send_json({'models':[{'name':'qwen3:4b'}]})

        def do_POST(self):
            assert self.path == '/api/chat'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload)
            context = json.loads(payload['messages'][1]['content'])
            passage = next(p for p in context['passages'] if '12 N m' in p['text'])
            self.send_json({'message':{'content':json.dumps({'status':'supported','evidence':[
                {'id':passage['id'],'quote':'Cover bolt torque: 12 N m.'}
            ]})}})

    server = ThreadingHTTPServer(('127.0.0.1', 0), OllamaFixture)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with TestClient(create_app(tmp_path, LocalEngine(f'http://127.0.0.1:{server.server_port}'))) as client:
            doc = upload(client).json()
            result = ask(client, doc).json()
            assert result['status'] == 'supported'
            assert result['evidence'][0]['page'] == 2
            assert 'Use a dry thread.' in result['evidence'][0]['text']
            assert result['evidence'][0]['document_id'] == doc['id']
            assert requests[0]['model'] == 'qwen3:4b'
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
