// On-device AI: a small Qwen model run by llama.cpp compiled to WebAssembly (wllama), using the device's GPU when available.
// The model is downloaded once (internet needed), stored in the browser, and then works offline.
// Like the laptop, it only *selects* passages; the app shows the original manual text.
import { Wllama } from '../vendor/wllama/index.js';
import { PHONE_PROMPT, choiceSchema, parseReply, validateChoice, specificationCandidates } from './engine.js';

export const MODELS = {
  fast: { id: 'fast', label: 'Fast · Qwen2.5 0.5B', size: 491400032, note: 'Works on most devices. Quicker, less precise.',
    url: 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf' },
  better: { id: 'better', label: 'Better · Qwen2.5 1.5B', size: 1117320736, note: 'Needs a recent device with 6 GB memory or more. Slower, more precise.',
    url: 'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf' },
};
const PASSAGES_FOR_MODEL = 3;      // fewer, shorter passages keep answers fast on phones
const PASSAGE_CHARS = 700;

function storageGet(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } }
function storageSet(key, value) { try { localStorage.setItem(key, value); } catch { /* per-session only */ } }

export class OnDeviceAI {
  constructor(wasmUrl, options = {}) {
    this.wasmUrl = wasmUrl;
    this.choice = MODELS[storageGet('torquedoc-ai-model', 'fast')] ? storageGet('torquedoc-ai-model', 'fast') : 'fast';
    // Graphics chip use can be switched off if a device's GPU support is unreliable.
    this.useGpu = storageGet('torquedoc-ai-gpu', 'on') !== 'off';
    this.state = 'unknown';            // unknown | missing | downloading | ready | loading | loaded | error
    this.progress = 0;
    this.error = '';
    this.busy = false;
    this.loadedId = null;
    this.listeners = new Set();
    this.create = options.create || (() => {
      const runtime = new Wllama({ default: this.wasmUrl }, { allowOffline: true, logger: { debug() {}, log() {}, warn: console.warn, error: console.error } });
      // Older Android WebViews lack JSPI/memory64. Never fetch their runtime from a CDN.
      runtime.setCompat({
        worker: new URL('../vendor/wllama-compat/wllama.js', import.meta.url).href,
        wasm: new URL('../vendor/wllama-compat/wllama.wasm', import.meta.url).href,
      });
      return runtime;
    });
    this.refreshRequest = 0;
    this.wllama = null;
    this.passages = PASSAGES_FOR_MODEL;
    this.chars = PASSAGE_CHARS;
    // Small models spend a long time evaluating JSON grammars. Validate their short reply
    // instead; malformed or invented IDs always fall back to explicitly labeled search.
    this.grammar = false;
    this.downloadController = null;
    this.lastRun = null;  // for troubleshooting: raw model output, error and timing of the last question
  }

  get model() { return MODELS[this.choice]; }

  onChange(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }

  emit() { for (const listener of this.listeners) listener(this.snapshot()); }

  snapshot() {
    return { choice: this.choice, model: this.model, state: this.state, progress: this.progress, error: this.error,
      gpu: Boolean(this.wllama?.isSupportWebGPU?.()), useGpu: this.useGpu, busy: this.busy, models: MODELS };
  }

  instance() {
    if (!this.wllama) this.wllama = this.create();
    return this.wllama;
  }

  async cached(id = this.choice) {
    const models = await this.instance().modelManager.getModels();
    return models.find(m => m.url === MODELS[id].url && m.validate() === 'valid') || null;
  }

  async refresh() {
    if (['downloading', 'loading'].includes(this.state) || this.busy) return this.snapshot();
    const request = ++this.refreshRequest, choice = this.choice;
    try {
      const cached = await this.cached(choice);
      if (request !== this.refreshRequest || choice !== this.choice || ['downloading', 'loading'].includes(this.state) || this.busy) return this.snapshot();
      this.state = this.loadedId === choice ? 'loaded' : cached ? 'ready' : 'missing';
      this.error = '';
    } catch (error) {
      if (request !== this.refreshRequest || ['downloading', 'loading'].includes(this.state) || this.busy) return this.snapshot();
      this.state = 'missing';
      this.error = `Model storage is unavailable: ${error.message}`;
    }
    this.emit();
    return this.snapshot();
  }

  async choose(id) {
    if (!MODELS[id] || this.busy || ['downloading', 'loading'].includes(this.state)) return;
    this.choice = id;
    storageSet('torquedoc-ai-model', id);
    await this.refresh();
  }

  async setGpu(on) {
    if (this.busy || ['downloading', 'loading'].includes(this.state)) return;
    this.useGpu = Boolean(on);
    storageSet('torquedoc-ai-gpu', this.useGpu ? 'on' : 'off');
    if (this.loadedId && !this.busy) { await this.wllama.exit(); this.wllama = null; this.loadedId = null; this.state = 'ready'; }
    this.emit();
  }

  async download() {
    if (['downloading', 'loading'].includes(this.state) || this.busy) return;
    ++this.refreshRequest;
    const model = this.model;
    this.downloadController = new AbortController();
    this.state = 'downloading'; this.progress = 0; this.error = ''; this.emit();
    try {
      const storage = await navigator.storage?.estimate?.().catch(() => null);
      if (storage?.quota && storage.quota - (storage.usage || 0) < model.size * 1.05) {
        throw new Error(`Not enough storage. Free at least ${Math.ceil(model.size * 1.1 / 1e6)} MB and retry.`);
      }
      await navigator.storage?.persist?.().catch(() => false);
      const downloaded = await this.instance().modelManager.downloadModel(model.url, {
        signal: this.downloadController.signal,
        progressCallback: ({ loaded, total }) => { this.progress = total ? loaded / total : 0; this.emit(); },
      });
      if (downloaded.validate() !== 'valid') throw new Error('The model download is incomplete. Please retry.');
      this.state = 'ready';
      this.progress = 1;
    } catch (error) {
      const cancelled = this.downloadController.signal.aborted;
      this.state = cancelled ? 'missing' : 'error';
      this.error = cancelled ? 'Download cancelled. You can retry when ready.'
        : navigator.onLine === false ? 'No internet connection. Connect to Wi-Fi and try again.' : `Download failed: ${error.message}`;
    } finally {
      this.downloadController = null;
    }
    this.emit();
  }

  cancelDownload() { this.downloadController?.abort(); }

  async remove() {
    if (['downloading', 'loading'].includes(this.state) || this.busy) return;
    this.busy = true; ++this.refreshRequest; this.emit();
    try {
      if (this.loadedId) { await this.wllama.exit(); this.wllama = null; this.loadedId = null; }
      const model = await this.cached();
      if (model) await model.remove();
    } finally { this.busy = false; this.emit(); }
    await this.refresh();
  }

  async load() {
    const wllama = this.instance();
    if (this.loadedId === this.choice) return wllama;
    if (this.loadedId) { await wllama.exit(); this.wllama = null; this.loadedId = null; return this.load(); }
    const model = await this.cached();
    if (!model) { this.state = 'missing'; this.emit(); throw new Error('missing'); }
    this.state = 'loading'; this.error = ''; this.emit();
    try {
      await wllama.loadModel(model, { n_ctx: 3072, n_batch: 512, ...(this.useGpu ? {} : { n_gpu_layers: 0 }) });
      this.loadedId = this.choice;
      this.state = 'loaded';
    } catch (error) {
      // A failed worker must not be reused by the next attempt.
      await wllama.exit().catch(() => {});
      this.wllama = null; this.loadedId = null;
      this.state = 'error'; this.error = `The AI model could not start on this device (${error.message}). Try the Fast model or free some memory.`;
      this.emit();
      throw error;
    }
    this.emit();
    return wllama;
  }

  /** Same contract as the laptop's LocalEngine.select: [passages | [] | null, message]. */
  async select(question, scope, passages, { signal } = {}) {
    const checkAbort = () => { if (signal?.aborted) throw new DOMException('Aborted', 'AbortError'); };
    checkAbort();
    if (this.state === 'unknown') await this.refresh();
    if (!['ready', 'loaded'].includes(this.state)) {
      return [null, this.state === 'downloading' ? 'The on-device AI model is still downloading. These are keyword matches.'
        : 'Download the on-device AI model in Settings to get AI-selected answers. Keyword search already works.'];
    }
    if (this.busy) return [null, 'On-device AI is handling another question. These are keyword matches; try AI again shortly.'];
    const eligible = new Set(specificationCandidates(question,
      passages.map(p => ({ ...p, text: p.text.slice(0, this.chars) }))).map(p => p.id));
    const used = passages.filter(p => eligible.has(p.id)).slice(0, this.passages);
    if (!used.length) {
      this.lastRun = { preflight: 'No direct specification with matching component and units in the retrieved text.' };
      return [[], 'No direct specification for this component was found in the retrieved text. Inspect the original pages or try a more exact component name.'];
    }
    this.busy = true;
    this.lastRun = null;
    this.emit();
    try {
      const wllama = await this.load();
      checkAbort();
      const context = {
        question,
        passages: used.map(p => ({ id: p.id, source: `${p.title ?? scope.title} · ${p.variant ?? scope.variant}`,
          revision: p.revision ?? scope.revision,
          kind: (p.type ?? scope.type) === 'web' ? 'web_page' : 'manual', text: p.text.slice(0, this.chars) })),
      };
      const started = performance.now();
      this.lastRun = { promptChars: JSON.stringify(context).length + PHONE_PROMPT.length, grammar: this.grammar };
      const response = await wllama.createChatCompletion({
        messages: [{ role: 'system', content: PHONE_PROMPT }, { role: 'user', content: JSON.stringify(context) }],
        temperature: 0, max_tokens: 60, abortSignal: signal,
        ...(this.grammar ? { response_format: { type: 'json_schema', json_schema: { name: 'choice', schema: choiceSchema(used.map(p => p.id)), strict: true } } } : {}),
      });
      checkAbort();
      const raw = response.choices[0].message.content;
      Object.assign(this.lastRun, { raw, seconds: (performance.now() - started) / 1000, usage: response.usage || null, timings: response.timings || null });
      const generated = parseReply(raw);
      return validateChoice(generated, used);
    } catch (error) {
      if (signal?.aborted || error?.name === 'AbortError') throw new DOMException('Aborted', 'AbortError');
      if (this.lastRun) this.lastRun.error = String(error?.message || error);
      if (error?.message === 'missing') return [null, 'Download the on-device AI model in Settings to get AI-selected answers. Keyword search already works.'];
      return [null, this.state === 'error' ? `${this.error} Showing keyword matches only.`
        : 'On-device AI returned evidence that could not be checked. Showing keyword matches only.'];
    } finally {
      this.busy = false;
      this.emit();
    }
  }
}
