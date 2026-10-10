"""Optional UI acceptance check. pip install playwright==1.51.0; python -m playwright install chromium.
Runs its own isolated backend and uses only a fictional example document.
"""
import json
import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

try:
    import httpx2 as httpx
except ModuleNotFoundError:
    import httpx
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'test-results'
OUT.mkdir(exist_ok=True)


def main():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    checks, errors, external = [], [], []
    with tempfile.TemporaryDirectory(prefix='torquedoc-browser-') as data:
        page_html = ('<html><head><title>Training rig web notes</title></head><body><nav>Menu</nav><h1>Training rig TD-01 web notes</h1>'
                     '<p>FICTIONAL ONLY. Track tension adjuster grease fitting: inspect weekly. ' + 'Fictional filler sentence for the web snapshot test. ' * 8 + '</p></body></html>').encode()

        class Site(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(page_html))); self.end_headers()
                self.wfile.write(page_html)

        site = ThreadingHTTPServer(('127.0.0.1', 0), Site)
        threading.Thread(target=site.serve_forever, daemon=True).start()
        site_url = f'http://127.0.0.1:{site.server_port}/notes'
        env = {**os.environ, 'PORT':str(port), 'TORQUEDOC_DATA_DIR':data, 'TORQUEDOC_NO_BROWSER':'1', 'OLLAMA_HOST':'http://127.0.0.1:1', 'TORQUEDOC_TEST_ALLOW_LOCAL_WEB':'1'}
        process = subprocess.Popen([sys.executable, 'run.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            with httpx.Client(trust_env=False) as api:
                for _ in range(80):
                    try:
                        if api.get(base + '/api/documents', timeout=1).is_success:
                            break
                    except httpx.TransportError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError(process.stderr.read().decode())
                    time.sleep(.1)
                else:
                    raise RuntimeError('Test backend did not start.')
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={'width':1440, 'height':1000})
                # Internet requests are blocked; loopback is still usable with Wi-Fi disconnected.
                def route(request):
                    if urlparse(request.request.url).hostname not in {'127.0.0.1','localhost'}:
                        external.append(request.request.url)
                        request.abort()
                    else:
                        request.continue_()
                context.route('**/*', route)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base, wait_until='networkidle')
                expect(page.locator('.offline-badge')).to_have_text('LOCAL SEARCH READY')
                expect(page.locator('.live-welcome')).to_be_visible()
                page.screenshot(path=str(OUT / 'assistant-desktop.png'), full_page=True)
                checks.append('Initial UI and unavailable-model status')

                page.select_option('#machine-selector','training')
                expect(page.locator('#manual-selector option').first).to_have_text('All manuals for this machine (1)', timeout=30000)
                expect(page.locator('.library-progress')).to_have_count(0, timeout=30000)
                checks.append('Built-in library is indexed on first start and searched by default')

                page.fill('#technical-query','What is the cover bolt torque?')
                page.click('.query-submit')
                expect(page.locator('.live-result-heading')).to_contain_text('KEYWORD SEARCH',timeout=15000)
                expect(page.locator('.manual-excerpt').filter(has_text='12 N m').first).to_be_visible()
                expect(page.locator('.manual-excerpt mark').first).to_be_visible()
                expect(page.locator('.evidence-card .source-chip--builtin').first).to_be_visible()
                page.screenshot(path=str(OUT / 'search-desktop.png'), full_page=True)
                page.get_by_role('button',name='Open original page 2').first.click()
                expect(page.locator('#source-page')).to_have_value('2')
                expect(page.locator('.source-page-image')).to_have_js_property('naturalWidth',1190)
                expect(page.locator('.modal-body')).to_contain_text('page label TRAIN-8')
                page.screenshot(path=str(OUT / 'source-page.png'), full_page=True)
                page.fill('#source-page','3')
                page.locator('#page-form button').click()
                expect(page.locator('#source-page')).to_have_value('3')
                expect(page.locator('[data-action="delete-manual"]')).to_have_count(0)
                page.locator('.modal-header [data-action="close-modal"]').click()
                checks.append('Ollama-off fallback, page citations, original rendering and page navigation')

                page.fill('#technical-query','extraterrestrial fluxcapacitance')
                page.locator('[data-action="keyword-search"]').click()
                expect(page.locator('.live-result-heading')).to_contain_text('NO SUPPORTED ANSWER')
                expect(page.locator('.evidence-card')).to_have_count(0)
                checks.append('No-match question produces no specification')

                page.locator('.primary-nav [data-screen="library"]').click()
                expect(page.locator('.library-document')).to_have_count(1)
                expect(page.locator('.library-document')).to_contain_text('Built-in')
                expect(page.locator('.library-document')).to_contain_text('Text indexed')
                page.get_by_role('button',name='Add a log entry').click()
                page.fill('#log-title','Browser acceptance check')
                page.fill('#log-note','Fictional training reference inspected. No equipment work performed.')
                page.get_by_role('button',name='Save log locally').click()
                page.reload(wait_until='networkidle')
                expect(page.locator('.library-log-item')).to_contain_text('Browser acceptance check')
                checks.append('Library and maintenance note persist after reload')

                page.select_option('#machine-selector','cat')
                page.wait_for_timeout(300)
                assert all('Training' not in t for t in page.locator('.library-document').all_inner_texts())
                page.locator('.primary-nav [data-screen="assistant"]').click()
                page.fill('#technical-query','cover bolt torque')
                page.locator('[data-action="keyword-search"]').click()
                expect(page.locator('.live-result-heading')).to_be_visible()
                assert '12 N m' not in page.locator('#live-answer').inner_text() and 'TD-01' not in page.locator('#live-answer').inner_text()
                page.select_option('#machine-selector','deere')
                expect(page.locator('.live-result-heading')).to_have_count(0)
                checks.append('Machine switching does not leak prior manual or answer')

                page.locator('.primary-nav [data-screen="diagnostics"]').click()
                expect(page.locator('.design-preview-note')).to_contain_text('DESIGN PREVIEW')
                assert '74%' not in page.locator('main').inner_text()
                checks.append('Diagnostic screen clearly marked as preview, no invented probabilities')

                page.select_option('#machine-selector','training')
                page.evaluate("""async ({encoded}) => {
                    const request=indexedDB.open('torquedoc-local',1);
                    const db=await new Promise((resolve,reject)=>{request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
                    const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
                    await new Promise((resolve,reject)=>{const tx=db.transaction('documents','readwrite');tx.objectStore('documents').put({id:'legacy-ui-check',title:'legacy-training.pdf',mime:'application/pdf',type:'import',status:'imported',size:'5 KB',blob:new Blob([bytes],{type:'application/pdf'})});tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
                    db.close();
                }""", {'encoded':base64.b64encode((ROOT/'examples/Training-Rig-TD01.pdf').read_bytes()).decode()})
                page.reload(wait_until='networkidle')
                page.locator('.primary-nav [data-screen="library"]').click()
                page.locator('[data-action="open-document"][data-id="legacy-ui-check"]').click()
                page.locator('[data-action="index-legacy"]').click()
                page.fill('#import-variant','TD-01 (fictional)')
                page.fill('#import-revision','TRAINING R1')
                page.click('#import-confirm')
                expect(page.locator('#modal-root')).to_be_empty(timeout=30000)
                page.locator('.primary-nav [data-screen="library"]').click()
                expect(page.locator('.library-document')).to_have_count(1)
                page.evaluate("localStorage.setItem('torquedoc-migrated-legacy-ui-check','missing-backend-copy')")
                page.reload(wait_until='networkidle')
                expect(page.locator('[data-action="open-document"][data-id="legacy-ui-check"]')).to_contain_text('Not indexed')
                checks.append('Legacy PDF migration preserves original and re-exposes it if the backend copy is missing')

                builtin = page.locator('.library-document', has_text='Built-in')
                builtin.click()
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-action="update-manual"]').click()
                chooser.value.set_files(str(ROOT / 'examples/Training-Rig-TD01.pdf'))
                expect(page.locator('#modal-title')).to_have_text('Add an update')
                expect(page.locator('#import-variant')).to_have_value('TD-01 (fictional)')
                assert page.locator('#import-supersedes').input_value()
                page.fill('#import-revision','TRAINING R2')
                page.click('#import-confirm')
                expect(page.locator('#modal-root')).to_be_empty(timeout=30000)
                expect(page.locator('#manual-selector option').first).to_have_text('All manuals for this machine (1)')
                expect(page.locator('#manual-selector optgroup[label="Replaced by an update"] option')).to_have_count(1)
                page.fill('#technical-query','cover bolt torque')
                page.locator('[data-action="keyword-search"]').click()
                expect(page.locator('.evidence-meta').first).to_contain_text('TRAINING R2')
                expect(page.locator('.evidence-meta').filter(has_text='TRAINING R1')).to_have_count(0)
                page.locator('.primary-nav [data-screen="library"]').click()
                expect(builtin).to_contain_text('Replaced')
                checks.append('An update replaces a built-in manual in searches; the original stays viewable')

                update = page.locator('.library-document', has_text='TRAINING R2')
                update.click()
                page.locator('[data-action="edit-manual"]').click()
                page.fill('#edit-revision','TRAINING R2b')
                page.click('#edit-confirm')
                expect(page.locator('#toast')).to_contain_text('Manual details updated')
                page.locator('.library-document', has_text='TRAINING R2b').click()
                page.locator('[data-action="delete-manual"]').click()
                expect(page.locator('#modal-title')).to_have_text('Delete this update?')
                page.locator('[data-action="confirm-delete"]').click()
                expect(page.locator('#toast')).to_contain_text('Update deleted')
                expect(builtin).not_to_contain_text('Replaced')
                checks.append('Updates can be corrected or deleted; deleting restores the built-in manual')

                example = str(ROOT / 'examples/Training-Rig-TD01.pdf')
                page.set_input_files('#file-input', [example, example])
                page.uncheck('#import-same')
                expect(page.locator('#import-variant-1')).to_be_visible()
                page.fill('#import-variant','TD-01 (fictional)')
                page.fill('#import-revision','TRAINING R5')
                page.fill('#import-variant-1','TD-01 (fictional)')
                page.fill('#import-revision-1','TRAINING R3')
                page.select_option('#import-kind-1','bulletin')
                page.click('#import-confirm')
                expect(page.locator('#modal-root')).to_be_empty(timeout=30000)
                page.locator('.primary-nav [data-screen="library"]').click()
                expect(page.locator('.library-document')).to_have_count(4)
                expect(page.locator('.library-document').filter(has_text='Service bulletin')).to_contain_text('TRAINING R3')
                checks.append('Multi-file update stores separate details per file')

                page.locator('[data-action="open-document"][data-id="legacy-ui-check"]').click()
                page.locator('[data-action="delete-legacy"]').click()
                page.locator('[data-action="confirm-delete-legacy"]').click()
                expect(page.locator('#toast')).to_contain_text('Browser copy removed')
                expect(page.locator('[data-action="open-document"][data-id="legacy-ui-check"]')).to_have_count(0)
                expect(page.locator('.library-document')).to_have_count(3)
                checks.append('Earlier browser imports can be removed after confirmation')

                page.locator('.primary-nav [data-screen="library"]').click()
                page.locator('.library-heading [data-action="add-web"]').click()
                page.fill('#web-url', site_url)
                page.fill('#web-variant', 'TD-01 (fictional)')
                page.click('#web-confirm')
                expect(page.locator('#modal-root')).to_be_empty(timeout=30000)
                expect(page.locator('#toast')).to_contain_text('Training rig web notes')
                page.fill('#technical-query', 'track tension grease fitting')
                page.locator('[data-action="keyword-search"]').click()
                expect(page.locator('.evidence-card .source-chip--web').first).to_be_visible()
                expect(page.locator('.web-note')).to_be_visible()
                expect(page.locator('.evidence-card .web-link').first).to_have_attribute('href', site_url)
                page.screenshot(path=str(OUT / 'web-result.png'), full_page=True)
                page.locator('.primary-nav [data-screen="library"]').click()
                page.locator('.library-filter[data-filter="web"]').click()
                expect(page.locator('.library-document')).to_have_count(1)
                page.locator('.library-filter[data-filter="all"]').click()
                page.locator('.sidebar-settings').click()
                expect(page.locator('.modal-body')).to_contain_text('Web sources')
                expect(page.locator('.modal-body')).to_contain_text('3 listed in the library catalog')
                exported = page.evaluate("localStorage.getItem('torquedoc-workspace-v1')")
                logs = json.loads(exported)['logs']
                page.evaluate("""() => { const data = JSON.parse(localStorage.getItem('torquedoc-workspace-v1')); data.logs = []; localStorage.setItem('torquedoc-workspace-v1', JSON.stringify(data)); }""")
                export_file = OUT / 'logs-export.json'
                export_file.write_text(json.dumps({'application': 'TorqueDoc', 'logs': logs + [{'id': 'imported-1', 'title': 'Imported from browser version', 'note': 'Fictional.', 'machine': 'training', 'time': '2026-01-01T00:00:00Z', 'kind': 'note'}]}))
                with page.expect_file_chooser() as chooser:
                    page.locator('[data-action="import-logs"]').click()
                chooser.value.set_files(str(export_file))
                expect(page.locator('#toast')).to_contain_text('Imported')
                page.locator('.primary-nav [data-screen="library"]').click()
                expect(page.locator('.library-log-item').filter(has_text='Imported from browser version')).to_have_count(1)
                page.locator('.sidebar-settings').click()
                page.locator('.modal-header [data-action="close-modal"]').click()
                checks.append('A web page is saved offline, searched, labeled as a web source and linked to its address; logs can be imported')

                page.locator('.primary-nav [data-screen="assistant"]').click()
                page.set_viewport_size({'width':390,'height':844})
                expect(page.locator('.sidebar')).not_to_be_in_viewport()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
                page.screenshot(path=str(OUT / 'assistant-mobile.png'), full_page=True)
                checks.append('390px mobile layout has no horizontal overflow')
                cache_urls = page.evaluate("async () => {const urls=[];for(const name of await caches.keys()){const c=await caches.open(name);urls.push(...(await c.keys()).map(r=>r.url));}return urls;}")
                assert not any('/api/' in url for url in cache_urls)
                assert not errors, errors
                assert not external, external
                checks.append('No API cached, no JavaScript exceptions, no external browser requests')
                browser.close()
        finally:
            site.shutdown()
            process.terminate()
            process.wait(timeout=10)
            process.stderr.close()
    report = {'passed':len(checks),'checks':checks,'javascript_errors':errors,'external_requests':external,
              'actual_llm_inference_tested':False,'windows_launcher_executed':False}
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
