// TorqueDoc website bootstrap: answers the interface's /api/... requests in the browser itself,
// using the built-in library database, pdf.js page rendering and the on-device AI.
import sqlite3InitModule from '../vendor/sqlite/index.mjs';
import { Library, ask, NOTICE } from './engine.js';
import { OnDeviceAI, MODELS } from './ai.js';
import { pageImage } from './pages.js';

const APP = new URL('../', import.meta.url);
const nativeFetch = window.fetch.bind(window);
const ai = new OnDeviceAI(new URL('../vendor/wllama/wllama.wasm', import.meta.url).href);
let host = null;  // the TorqueDoc interface: refresh, render, settings, toast
let libraryError = null;

const libraryReady = (async () => {
  const sqlite3 = await sqlite3InitModule({ print: () => {}, printErr: console.warn });
  const response = await nativeFetch(new URL('library.db', APP));
  if (!response.ok) throw new Error('The built-in library is missing from this app.');
  return new Library(sqlite3, new Uint8Array(await response.arrayBuffer()));
})().catch(error => { libraryError = error; throw error; });
const buildInfo = nativeFetch(new URL('web/build-info.json', APP)).then(r => r.json()).catch(() => ({}));

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function engineHealth() {
  const s = ai.snapshot();
  const state = ['ready', 'loaded'].includes(s.state) ? 'ready' : s.state === 'downloading' ? 'downloading' : 'model_missing';
  const message = state === 'ready' ? 'On-device AI model installed. Works offline.'
    : state === 'downloading' ? `Downloading the AI model: ${Math.round(s.progress * 100)}%.`
      : s.error || 'Download the on-device AI model once in Settings. Keyword search already works.';
  return { state, model: `${s.model.label} (on this device)`, message };
}

async function route(method, url, body, signal) {
  const library = await libraryReady;
  const path = url.pathname.replace(/\/+$/, '');
  let match;
  if (method === 'GET' && path === '/api/ping') return { app: 'torquedoc', ready: true };
  if (method === 'GET' && path === '/api/health') {
    if (url.searchParams.get('fresh') === 'true' || ai.state === 'unknown') await ai.refresh();
    const docs = library.documents();
    return { backend: 'ready', engine: engineHealth(), search: 'sqlite_fts5', documents: docs.length,
      builtin_documents: docs.filter(d => d.source === 'builtin').length, manual_bytes: docs.reduce((n, d) => n + d.bytes, 0),
      library: { state: 'ready', total: docs.length, done: docs.length, current: '', errors: [] },
      web_sources: { listed: 0, saved: 0, state: 'idle', errors: [] }, ocr: false, network_mode: 'on_device' };
  }
  if (method === 'GET' && path === '/api/machines') return { machines: library.machines() };
  if (method === 'GET' && path === '/api/documents') return { documents: library.documents(url.searchParams.get('machine')) };
  if (method === 'GET' && (match = path.match(/^\/api\/documents\/([^/]+)\/pages\/(\d+)$/))) {
    return library.page(decodeURIComponent(match[1]), Number(match[2]));
  }
  if (method === 'POST' && path === '/api/ask') return ask(library, ai, body || {}, { signal });
  const error = new Error('Not available in the website. Manuals and updates are added in the TorqueDoc desktop app and appear here when the website is updated.');
  error.status = 405;
  throw error;
}

// Requests to /api/ are answered in the browser; everything else (app files, model downloads) goes through normally.
window.fetch = async (input, init = {}) => {
  const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return nativeFetch(input, init);
  const request = input instanceof Request ? input : null;
  const signal = init.signal || request?.signal;
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  const method = (init.method || request?.method || 'GET').toUpperCase();
  const raw = init.body ?? (request && !['GET', 'HEAD'].includes(method) ? await request.clone().text() : null);
  let body = null;
  if (typeof raw === 'string') { try { body = JSON.parse(raw); } catch { return json({ detail: 'Invalid request.' }, 400); } }
  let onAbort;
  try {
    const task = route(method, url, body, signal);
    const cancelled = new Promise((_, reject) => {
      onAbort = () => reject(new DOMException('Aborted', 'AbortError'));
      signal?.addEventListener('abort', onAbort, { once: true });
      if (signal?.aborted) onAbort();
    });
    return json(await (signal ? Promise.race([task, cancelled]) : task));
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    if (libraryError) return json({ detail: `The built-in library could not be opened: ${libraryError.message}` }, 500);
    return json({ detail: error.message || 'Request failed.' }, error.status || 500);
  } finally {
    if (onAbort) signal?.removeEventListener('abort', onAbort);
  }
};

function formatSize(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

async function saveFile(name, text) {
  if (window.TorqueDocAndroid) return window.TorqueDocAndroid.saveFile(name, text);
  const cap = window.Capacitor;
  if (cap?.isNativePlatform?.()) {
    const Filesystem = cap.registerPlugin('Filesystem'), Share = cap.registerPlugin('Share');
    await Filesystem.writeFile({ path: name, data: text, directory: 'CACHE', encoding: 'utf8' });
    const { uri } = await Filesystem.getUri({ path: name, directory: 'CACHE' });
    await Share.share({ title: name, dialogTitle: 'Save or send the maintenance log', files: [uri] });
    return true;
  }
  return false;
}

// Offline after the first visit: the service worker keeps the app, the library and its PDFs on the device.
if ('serviceWorker' in navigator && !window.Capacitor && !window.TorqueDocAndroid) {
  navigator.serviceWorker.register(new URL('../sw.js', import.meta.url), { scope: new URL('../', import.meta.url).pathname })
    .then(registration => {
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing;
        worker?.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) host?.toast('An updated library is ready. Reopen TorqueDoc to use it.');
          if (worker.state === 'activated' && !navigator.serviceWorker.controller) host?.toast('TorqueDoc is now saved on this device and works offline.');
        });
      });
    }).catch(error => console.warn('Offline mode unavailable:', error));
}

window.TorqueDocWeb = {
  ai, MODELS,

  attach(app) {
    host = app;
    let lastState = null;
    ai.onChange(snapshot => {
      const bar = document.querySelector('.ai-progress i'), label = document.querySelector('[data-ai-status]');
      if (snapshot.state === 'downloading' && lastState === 'downloading' && bar) {
        // Only move the progress bar during a download; redrawing the dialog ten times a second makes slower devices sluggish.
        bar.style.width = `${(snapshot.progress * 100).toFixed(1)}%`;
        bar.parentElement?.setAttribute('aria-valuenow', Math.round(snapshot.progress * 100));
        if (label) label.textContent = `Downloading ${Math.round(snapshot.progress * 100)}%`;
        return;
      }
      lastState = snapshot.state;
      if (document.querySelector('[data-settings-modal]')) host.settings();
      clearTimeout(this.timer);
      this.timer = setTimeout(() => host.refresh(!document.querySelector('#modal-root')?.firstChild && !document.activeElement?.matches('input,textarea,select')), 400);
    });
    ai.refresh();
  },

  pageImage(document, number) { return pageImage(document, number); },

  saveFile,

  settings({ icon, esc, live }) {
    const s = ai.snapshot(), info = this.info || {};
    buildInfo.then(value => { if (!this.info) { this.info = value; if (document.querySelector('[data-settings-modal]')) host.settings(); } });
    const busy = s.busy || ['downloading', 'loading'].includes(s.state);
    const status = { unknown: 'Checking…', missing: 'Not downloaded', downloading: `Downloading ${Math.round(s.progress * 100)}%`,
      ready: 'Downloaded · works offline', loading: 'Starting…', loaded: s.busy ? 'Reading passages…' : 'Ready · works offline', error: 'Problem' }[s.state];
    const installed = ['ready', 'loaded'].includes(s.state);
    const builtin = live.documents.filter(d => d.source === 'builtin').length;
    return {
      title: 'TorqueDoc on this device',
      subtitle: `${window.TorqueDocAndroid ? 'Android app · bundled offline library' : 'Built-in library'}${info.built_at ? ` · ${info.built_at.slice(0, 10)}` : ''}`,
      body: `<span data-settings-modal hidden></span>
        <div class="setting-row"><div><strong>Built-in manuals</strong><p>${builtin} document(s) with their original pages, searchable offline. New manuals and revisions are added in the TorqueDoc desktop app and appear here when the website is updated.</p></div><span class="badge badge-teal">offline</span></div>
        <div class="setting-row"><div><strong>On-device AI <span class="badge badge-amber">Experimental</span></strong><p>Picks the passages that answer a question, on this device, without internet once downloaded. It is slow on most phones (often a minute or more per question) and less precise than the laptop's AI; keyword search is instant. It only points at manual text; answers always show the original pages.</p>
          <div class="ai-models">${Object.values(MODELS).map(m => `<label class="ai-model"><input type="radio" name="ai-model" data-action="ai-choose" data-model="${m.id}" ${m.id === s.choice ? 'checked' : ''} ${busy ? 'disabled' : ''}><span><strong>${esc(m.label)} · ${formatSize(m.size)}</strong><small>${esc(m.note)}</small></span></label>`).join('')}</div>
          <p><strong data-ai-status>${esc(status)}</strong>${s.error ? ` · <span class="text-amber">${esc(s.error)}</span>` : ''}</p>
          ${s.state === 'downloading' ? `<div class="ai-progress" role="progressbar" aria-valuenow="${Math.round(s.progress * 100)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${(s.progress * 100).toFixed(1)}%"></i></div>` : ''}
          <div class="ai-actions">${s.state === 'downloading' ? '<button class="button button-secondary" data-action="ai-cancel-download">Cancel download</button>'
            : installed ? `<button class="button button-secondary button-danger" data-action="ai-remove" ${busy ? 'disabled' : ''}>Delete model</button>`
            : `<button class="button button-primary" data-action="ai-download" ${busy ? 'disabled' : ''}>${icon('download', 16)}Download ${formatSize(s.model.size)}</button>`}</div>
          ${s.gpu ? `<label class="ai-model"><input type="checkbox" data-action="ai-gpu" ${s.useGpu ? 'checked' : ''} ${busy ? 'disabled' : ''}><span><strong>Use the graphics chip</strong><small>Usually faster. Turn off if answers fail or the app closes while thinking.</small></span></label>` : ''}
          <p class="live-small">Downloading needs internet once; use Wi-Fi. Free storage needed: about ${formatSize(s.model.size * 1.1)}.</p></div></div>
        <div class="setting-row"><div><strong>Maintenance notes</strong><p>Saved in this browser on this device. Export them to keep a backup or send them to the shop.</p></div><span class="setting-actions"><button class="button button-secondary" data-action="import-logs">Import logs</button><button class="button button-secondary" data-action="export-logs">Export logs</button></span></div>
        <div class="live-note">${icon('info', 18)}<span>${esc(NOTICE)}</span></div>`,
      footer: `<button class="button button-primary" data-action="close-modal">Done</button>`,
    };
  },

  action(name, target) {
    if (name === 'ai-choose') { ai.choose(target.dataset.model); return true; }
    if (name === 'ai-download') {
      host?.toast(`Downloading the AI model (${formatSize(ai.model.size)}). Keep the app open; you can keep searching meanwhile.`);
      ai.download().then(() => host?.toast(ai.state === 'ready' ? 'AI model downloaded. It now works offline.' : ai.error));
      return true;
    }
    if (name === 'ai-cancel-download') { ai.cancelDownload(); return true; }
    if (name === 'ai-gpu') { ai.setGpu(target.checked).catch(error => host?.toast(error.message)); return true; }
    if (name === 'ai-remove') {
      if (confirm('Delete the AI model from this device? Your manuals and notes will remain.')) {
        ai.remove().then(() => host?.toast('AI model deleted from this device.')).catch(error => host?.toast(`Could not delete the model: ${error.message}`));
      }
      return true;
    }
    return false;
  },
};
