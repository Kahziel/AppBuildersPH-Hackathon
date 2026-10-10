"""Real on-device AI check, step by step with timings: download the Fast model inside the app,
block the internet, then ask questions through the app's own /api/ask (the same path the screen uses).
Usage: python tests/phone_ai_bench.py  [cpu]   (internet needed for the one-time download)"""
import functools
import json
import os
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(__file__))
import web_smoke as phone_smoke  # noqa: E402


def log(*parts):
    print(time.strftime('%H:%M:%S'), *parts, flush=True)


def main():
    cpu_only = 'cpu' in sys.argv[1:]
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(phone_smoke.Quiet, directory=str(phone_smoke.DIST)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}/'
    report = {'cpu_only': cpu_only}
    with sync_playwright() as p:
        launch = {'executable_path': os.environ['CHROMIUM']} if os.environ.get('CHROMIUM') else {}
        context = p.chromium.launch_persistent_context(tempfile.mkdtemp(prefix='torquedoc-phone-'), headless=True,
                                                       viewport={'width': 390, 'height': 844}, is_mobile=True, **launch)
        page = context.new_page()
        page.set_default_timeout(0)
        page.on('pageerror', lambda e: log('PAGE ERROR', e))
        page.on('crash', lambda *_: log('PAGE CRASHED'))
        page.goto(base, wait_until='networkidle')
        if cpu_only:
            page.evaluate("localStorage.setItem('torquedoc-ai-gpu', 'off')")
            page.reload(wait_until='networkidle')
        started = time.monotonic()
        page.evaluate('window.TorqueDocWeb.ai.download()')
        report['download'] = {'state': page.evaluate('window.TorqueDocWeb.ai.state'), 'seconds': round(time.monotonic() - started, 1)}
        log('download', report['download'])

        def offline(route):  # from here on, nothing may leave the device
            (route.continue_ if urlparse(route.request.url).hostname in {'127.0.0.1', 'localhost'} else route.abort)()
        context.route('**/*', offline)
        page.reload(wait_until='networkidle')
        log('engine', page.evaluate("fetch('/api/health').then(r => r.json()).then(h => h.engine)"))
        started = time.monotonic()
        page.evaluate('window.TorqueDocWeb.ai.load()')
        report['model_start_seconds'] = round(time.monotonic() - started, 1)
        log('model loaded', report['model_start_seconds'], 's')
        for question, machine in [('What is the cover bolt torque?', 'training'), ('What is the coolant capacity?', 'training'),
                                  ('What is the swing torque?', 'volvo')]:
            started = time.monotonic()
            answer = page.evaluate("""([question, machine]) => fetch('/api/ask', {method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({question, machine})}).then(r => r.json())""", [question, machine])
            report[question] = {'seconds': round(time.monotonic() - started, 1), 'status': answer['status'], 'message': answer['message'],
                                'cited': [e['text'][:160] for e in answer['evidence']]}
            log(question, json.dumps(report[question])[:400])
        context.close()
    server.shutdown()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
