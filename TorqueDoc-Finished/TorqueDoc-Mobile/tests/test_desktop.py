"""Desktop launcher: engine lifecycle, start-up checks and window behavior, with a stand-in for the WebView2 window."""
import json
import socket
import sys
import threading
import time
import types
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import desktop


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def fetch(url):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5) as response:
        return json.loads(response.read())


def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class SlowOllama(BaseHTTPRequestHandler):
    """Behaves like a missing Ollama on Windows: every check takes over 2 seconds."""
    def log_message(self, *args):
        pass

    def do_GET(self):
        time.sleep(2.5)
        self.send_response(503); self.end_headers()


class OldTorqueDoc(BaseHTTPRequestHandler):
    """An older TorqueDoc version: answers /api/health, has no /api/ping."""
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps({'backend': 'ready'}).encode() if self.path == '/api/health' else b'{}'
        self.send_response(200 if self.path == '/api/health' else 404)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('TORQUEDOC_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('TORQUEDOC_OFFLINE', '1')
    monkeypatch.setattr(desktop, 'PREFERRED_PORT', free_port())
    sys.modules.pop('backend.app', None)  # pick up the temporary data folder
    return tmp_path


def fake_webview(monkeypatch, seen):
    module = types.ModuleType('webview')
    module.settings = {}

    class Window:
        def load_url(self, url):
            seen['url'] = url
            seen['health'] = fetch(url + 'api/health')

        def load_html(self, content):
            seen.setdefault('html', []).append(content)

    def create_window(title, url=None, html=None, **options):
        seen.update(title=title, first_html=html, options=options)
        return Window()

    def start(func=None, **options):
        seen['start'] = options
        if func:
            func()  # the real window calls this once it is visible; returning = window closed

    module.create_window, module.start = create_window, start
    monkeypatch.setitem(sys.modules, 'webview', module)
    return module


def test_window_shows_at_once_then_loads_the_app_and_stops_engine_on_close(isolated, monkeypatch):
    seen = {}
    module = fake_webview(monkeypatch, seen)
    engines = []
    real = desktop.start_engine
    monkeypatch.setattr(desktop, 'start_engine', lambda port, progress=None: engines.append(real(port, progress)) or engines[-1])
    desktop.main()
    assert seen['title'] == 'TorqueDoc' and 'Starting TorqueDoc' in seen['first_html']
    assert seen['url'].startswith('http://127.0.0.1:') and seen['health']['backend'] == 'ready'
    assert seen['start']['private_mode'] is False and seen['start']['storage_path'].endswith('app-window')
    assert module.settings['ALLOW_DOWNLOADS'] is True
    server, thread = engines[0]
    assert server.should_exit is True
    thread.join(timeout=10)
    assert not thread.is_alive()


def test_slow_ollama_check_does_not_block_start(isolated, monkeypatch):
    ollama = serve(SlowOllama)
    monkeypatch.setenv('OLLAMA_HOST', f'http://127.0.0.1:{ollama.server_port}')
    seen = {}
    fake_webview(monkeypatch, seen)
    started = time.monotonic()
    desktop.main()
    assert seen.get('url'), seen.get('html')
    assert time.monotonic() - started < 20
    ollama.shutdown()


def test_older_torquedoc_on_the_port_is_reported(isolated, monkeypatch):
    old = serve(OldTorqueDoc)
    monkeypatch.setattr(desktop, 'PREFERRED_PORT', old.server_port)
    with pytest.raises(desktop.OlderTorqueDocRunning, match='older TorqueDoc'):
        desktop.choose_port()
    seen = {}
    fake_webview(monkeypatch, seen)
    desktop.main()  # shows the explanation in the window instead of hanging
    assert 'url' not in seen and 'older TorqueDoc' in seen['html'][-1]
    old.shutdown()


def test_running_current_torquedoc_is_reused(isolated, monkeypatch):
    seen = {}
    fake_webview(monkeypatch, seen)
    port = desktop.PREFERRED_PORT
    server, thread = desktop.start_engine(port)
    try:
        assert desktop.choose_port() == (port, True)
        monkeypatch.setattr(desktop, 'start_engine', lambda *a, **k: pytest.fail('should reuse the running engine'))
        desktop.main()
        assert seen['url'] == f'http://127.0.0.1:{port}/'
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_missing_window_component_falls_back_to_browser(isolated, monkeypatch):
    monkeypatch.setitem(sys.modules, 'webview', None)  # import fails
    opened = []
    monkeypatch.setattr(desktop.webbrowser, 'open', opened.append)
    engine = desktop.Engine()
    assert desktop.run_window(engine, isolated / 'w') is False
    monkeypatch.setattr(desktop, 'choose_port', lambda: (4173, True))
    desktop.main()
    assert opened == ['http://127.0.0.1:4173/']


def test_busy_port_used_by_another_program_picks_another(monkeypatch):
    with socket.socket() as busy:
        busy.bind(('127.0.0.1', 0)); busy.listen()
        monkeypatch.setattr(desktop, 'PREFERRED_PORT', busy.getsockname()[1])
        monkeypatch.setattr(desktop, 'get_json', lambda *a: None)
        port, running = desktop.choose_port()
        assert port != busy.getsockname()[1] and running is False
