// Draws original PDF pages in the browser with pdf.js (same size rule as the laptop: longest side up to 1800 px).
import * as pdfjs from '../vendor/pdf/pdf.min.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = new URL('../vendor/pdf/pdf.worker.min.mjs', import.meta.url).href;
const VENDOR = new URL('../vendor/pdf/', import.meta.url).href;
const documents = new Map();
const images = new Map();
const KEEP_IMAGES = 16;

function libraryUrl(path) {
  return new URL('../library/' + path.split('/').map(encodeURIComponent).join('/'), import.meta.url).href;
}

function openDocument(document) {
  if (!documents.has(document.id)) {
    const task = pdfjs.getDocument({ url: libraryUrl(document.source_path), cMapUrl: VENDOR + 'cmaps/', cMapPacked: true,
      standardFontDataUrl: VENDOR + 'standard_fonts/', wasmUrl: VENDOR + 'wasm/', isEvalSupported: false });
    documents.set(document.id, task.promise.catch(error => { documents.delete(document.id); throw error; }));
  }
  return documents.get(document.id);
}

export async function pageImage(document, number) {
  const key = `${document.id}:${number}`;
  if (images.has(key)) return images.get(key);
  const promise = (async () => {
    const pdf = await openDocument(document);
    const page = await pdf.getPage(number);
    const base = page.getViewport({ scale: 1 });
    const scale = Math.min(2, 1800 / Math.max(base.width, base.height, 1));
    const viewport = page.getViewport({ scale });
    const canvas = window.document.createElement('canvas');
    canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
    const context = canvas.getContext('2d', { alpha: false });
    context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({ canvasContext: context, canvas, viewport }).promise;
    page.cleanup();
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    return URL.createObjectURL(blob);
  })();
  images.set(key, promise);
  promise.catch(() => images.delete(key));
  while (images.size > KEEP_IMAGES) {
    const [oldest, url] = images.entries().next().value;
    images.delete(oldest);
    url.then(u => URL.revokeObjectURL(u)).catch(() => {});
  }
  return promise;
}
