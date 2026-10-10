"""Checks the built website (website/dist) in a phone-sized and a laptop-sized browser, including offline use.
Usage: python website/tests/web_smoke.py   (after website/build.py; needs: pip install playwright)"""
import functools
import json
import os
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

DIST = Path(__file__).resolve().parents[1] / 'dist'
WWW = DIST  # older scripts
OUT = Path(__file__).resolve().parents[1] / 'test-results'
OUT.mkdir(exist_ok=True)


class Quiet(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript', '.js': 'text/javascript',
                      '.wasm': 'application/wasm', '.webmanifest': 'application/manifest+json'}

    def log_message(self, *args):
        pass


FAKE_AI = """(mode) => {
    const ai = window.TorqueDocWeb.ai;
    ai.cached = async () => ({ fake: true });
    ai.state = 'ready';
    ai.instance = () => ({
        isSupportWebGPU: () => false, exit: async () => {}, loadModel: async () => {},
        createChatCompletion: async ({ messages }) => {
            const context = JSON.parse(messages[1].content);
            const answer = context.passages.find(p => p.text.includes('12 N m'));
            const reply = mode === 'invented' ? { status: 'supported', passage_ids: ['999999'] }
                : mode === 'none' ? { status: 'not_found', passage_ids: [] }
                : { status: 'supported', passage_ids: [answer.id] };
            return { choices: [{ message: { content: JSON.stringify(reply) } }] };
        },
    });
}"""


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(DIST)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}/'
    checks, errors, external = [], [], []
    with sync_playwright() as p:
        launch = {'executable_path': os.environ['CHROMIUM']} if os.environ.get('CHROMIUM') else {}
        context = p.chromium.launch_persistent_context(tempfile.mkdtemp(prefix='torquedoc-web-'), headless=True,
                                                       viewport={'width': 390, 'height': 844}, device_scale_factor=2,
                                                       is_mobile=True, has_touch=True, **launch)

        def route(request):
            if urlparse(request.request.url).hostname not in {'127.0.0.1', 'localhost'}:
                external.append(request.request.url)
                request.abort()
            else:
                request.continue_()
        context.route('**/*', route)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base, wait_until='networkidle')
        expect(page.locator('.offline-badge')).to_have_text('LOCAL SEARCH READY', timeout=20000)
        expect(page.locator('.engine-strip [data-action="settings"]')).to_contain_text('Set up AI')
        page.select_option('#machine-selector', 'training')
        expect(page.locator('#manual-selector option').first).to_have_text('All manuals for this machine (1)')
        for hidden in ['import-documents', 'add-web']:
            assert all(not el.is_visible() for el in page.locator(f'[data-action="{hidden}"]').all()), hidden
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        page.screenshot(path=str(OUT / 'web-phone-home.png'))
        checks.append('Opens with the built-in library on a phone screen; desktop-only buttons hidden')

        page.fill('#technical-query', 'What is the cover bolt torque?')
        page.locator('[data-action="keyword-search"]').click()
        expect(page.locator('.live-result-heading')).to_contain_text('KEYWORD SEARCH', timeout=15000)
        expect(page.locator('.manual-excerpt').filter(has_text='12 N m').first).to_be_visible()
        expect(page.locator('.manual-excerpt mark').first).to_be_visible()
        page.get_by_role('button', name='Open original page 2').first.click()
        expect(page.locator('#source-page')).to_have_value('2')
        expect(page.locator('.source-page-image')).to_have_js_property('naturalWidth', 1190, timeout=20000)
        expect(page.locator('.modal-body')).to_contain_text('page label TRAIN-8')
        assert not page.locator('.open-pdf').is_visible()
        page.locator('[data-action="live-source"]', has_text='Next').click()
        expect(page.locator('#source-page')).to_have_value('3')
        expect(page.locator('.source-page-image')).not_to_have_js_property('naturalWidth', 0, timeout=20000)
        page.locator('.modal-header [data-action="close-modal"]').click()
        checks.append('Keyword search with highlights; original PDF pages drawn in the browser; page navigation')

        page.select_option('#machine-selector', 'volvo')
        page.fill('#technical-query', 'swing torque')
        page.locator('[data-action="keyword-search"]').click()
        expect(page.locator('.evidence-card .source-chip--web').first).to_be_visible()
        assert '12 N m' not in page.locator('#live-answer').inner_text()
        checks.append("Built-in web source for another machine, labeled Web, without the training manual's results")

        page.select_option('#machine-selector', 'training')
        for mode, expected in [('right', 'LOCAL AI · SOURCE EXTRACT'), ('invented', 'KEYWORD SEARCH'), ('none', 'NO SUPPORTED ANSWER')]:
            page.evaluate(FAKE_AI, mode)
            page.fill('#technical-query', 'What is the cover bolt torque?')
            page.click('.query-submit')
            expect(page.locator('.live-result-heading')).to_contain_text(expected, timeout=20000)
            if mode == 'right':
                expect(page.locator('.evidence-selected .manual-excerpt')).to_contain_text('12 N m')
        checks.append('AI answers show only original passages; a passage that was not retrieved is refused')

        answer = page.evaluate("""() => fetch(new Request(new URL('/api/ask', location.href), {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({question: 'cover bolt torque', machine: 'training', search_only: true})
        })).then(r => r.json())""")
        assert answer['status'] == 'search_only' and answer['matches'][0]['page'] == 2
        checks.append('API adapter preserves a Request object method and JSON body')

        cancelled = page.evaluate("""async () => {
            const ai = window.TorqueDocWeb.ai;
            ai.state = 'ready'; ai.loadedId = null;
            let began; const started = new Promise(resolve => { began = resolve; });
            ai.instance = () => ({loadModel: async () => {},
                createChatCompletion: ({abortSignal}) => new Promise((resolve, reject) => {
                    began(); abortSignal.addEventListener('abort', () => reject(new Error('cancelled')), {once:true});
                })});
            const controller = new AbortController();
            const pending = fetch('/api/ask', {method: 'POST', signal: controller.signal,
                body: JSON.stringify({question:'cover bolt torque',machine:'training'})})
                .then(() => 'unexpected result', error => error.name);
            await started; controller.abort(); const outcome = await pending;
            await new Promise(resolve => setTimeout(resolve, 0));
            return {outcome, busy: ai.busy};
        }""")
        assert cancelled == {'outcome': 'AbortError', 'busy': False}, cancelled
        checks.append('Cancelling the actual API request reaches inference and releases the engine')

        page.reload(wait_until='networkidle')
        page.locator('.engine-strip [data-action="settings"]').click()
        expect(page.locator('#modal-title')).to_have_text('TorqueDoc on this device')
        expect(page.locator('.modal-body')).to_contain_text('Experimental')
        expect(page.locator('[data-action="ai-download"]')).to_contain_text('Download 491 MB')
        page.screenshot(path=str(OUT / 'web-phone-settings.png'))
        page.locator('.modal-footer [data-action="close-modal"]').click()
        checks.append('Settings: experimental on-device AI with model sizes')

        page.locator('.mobile-nav [data-screen="library"]').click()
        page.get_by_role('button', name='Add a log entry').click()
        page.fill('#log-title', 'Website acceptance check')
        page.get_by_role('button', name='Save log locally').click()
        page.reload(wait_until='networkidle')
        page.locator('.mobile-nav [data-screen="library"]').click()
        expect(page.locator('.library-log-item')).to_contain_text('Website acceptance check')
        checks.append('Maintenance notes persist in the browser')

        # Offline after the first visit: the service worker has saved the app and the library.
        page.wait_for_function('navigator.serviceWorker.controller !== null', timeout=30000)
        page.wait_for_function("caches.keys().then(k => k.some(n => n.startsWith('torquedoc-web-')))", timeout=60000)
        page.wait_for_function("""caches.keys().then(async keys => { const c = await caches.open(keys.find(n => n.startsWith('torquedoc-web-')));
            return (await c.keys()).length > 200; })""", timeout=60000)
        context.set_offline(True)
        server.shutdown()  # the website is gone too: everything must come from the device
        page.reload(wait_until='load')
        page.locator('.mobile-nav [data-screen="assistant"]').click(timeout=20000)
        page.select_option('#machine-selector', 'training')
        page.fill('#technical-query', 'cover bolt torque')
        page.locator('[data-action="keyword-search"]').click()
        expect(page.locator('.manual-excerpt').filter(has_text='12 N m').first).to_be_visible(timeout=20000)
        page.get_by_role('button', name='Open original page 2').first.click()
        expect(page.locator('.source-page-image')).to_have_js_property('naturalWidth', 1190, timeout=20000)
        page.locator('.modal-header [data-action="close-modal"]').click()
        assert page.evaluate('self.crossOriginIsolated'), 'offline cache should enable multi-core AI'
        page.screenshot(path=str(OUT / 'web-phone-offline.png'))
        checks.append('With the internet off and the website gone, the saved app still searches and shows pages')

        page.set_viewport_size({'width': 1366, 'height': 900})
        page.reload(wait_until='load')
        expect(page.locator('.sidebar')).to_be_visible(timeout=20000)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        page.screenshot(path=str(OUT / 'web-laptop.png'))
        checks.append('Laptop-size browser layout')

        assert not errors, errors
        assert not external, external
        checks.append('No JavaScript errors and no internet requests')
        context.close()
    print(json.dumps({'passed': len(checks), 'checks': checks}, indent=2))


if __name__ == '__main__':
    main()
