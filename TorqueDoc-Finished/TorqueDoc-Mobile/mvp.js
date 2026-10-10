// Live manual workflow. No hosted AI, CDN assets, or remote requests.
export function createMvp({icon, esc, getMachine, machineNames, applyMachines, getQuery, setQuery, render, toast, openModal, closeModal, navigate, db, readImports}) {
  let selections = {};
  try { selections = JSON.parse(localStorage.getItem('torquedoc-manual-selections') || '{}'); } catch {}
  const live = {documents: [], health: null, backend: 'checking', error: '', result: null, asking: false, importing: false, request: 0, selection: selections || {}};
  let askController, pageRequest = 0, pendingSupersedes = null;
  const machineDocs = () => live.documents.filter(d => d.machine === getMachine());
  const currentDocs = () => machineDocs().filter(d => !d.superseded_by);
  // No selection means every current manual for the machine is searched.
  const selected = () => machineDocs().find(d => d.id === live.selection[getMachine()]);
  const titleOf = id => live.documents.find(d => d.id === id)?.title || 'a newer document';
  const sourceLabel = d => d.source === 'builtin' ? 'Built-in' : 'Update';
  const webLink = d => d.url && /^https?:\/\//i.test(d.url) ? `<a class="web-link" href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">${icon('arrow-up-right',13)}${esc(new URL(d.url).hostname)}</a>` : '';
  const webChip = '<span class="source-chip source-chip--web">Web</span>';
  const bytes = n => n === 0 ? '0 KB' : n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
  const kindLabels = {manual:'Shop / maintenance manual', schematic:'Wiring schematic', bulletin:'Service bulletin', web:'Web page'};
  const modelName = () => live.health?.engine?.model || 'qwen3:4b';
  const regex = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // Mark the searched words so a technician can find them inside a long passage.
  function highlight(text, terms = []) {
    const patterns = [...new Set(terms)].filter(t => t.length > 1).map(term => /\d/.test(term)
      ? `${[...term].map(regex).join('[-/]?')}(?!\\w)`
      : `${regex(term.length > 4 ? term.replace(/(ing|ed|es|s)$/, '') : term)}(?:e|s|es|d|ed|ing|er|ers|ment|ments)?(?!\\w)`);
    if (!patterns.length) return esc(text);
    let html = '', last = 0;
    for (const match of text.matchAll(new RegExp(`(?<!\\w)(?:${patterns.join('|')})`, 'gi'))) {
      if (!match[0]) continue;
      html += `${esc(text.slice(last, match.index))}<mark>${esc(match[0])}</mark>`;
      last = match.index + match[0].length;
    }
    return html + esc(text.slice(last));
  }
  const prettyStatus = d => d.status === 'needs_ocr' ? 'Needs OCR · view only' : d.status === 'partial' ? `${d.text_pages}/${d.pages} pages searchable` : 'Text indexed';

  async function api(url, options = {}, timeout = 150000) {
    const controller = new AbortController();
    const external = options.signal;
    const cancel = () => controller.abort();
    external?.addEventListener('abort', cancel, {once: true});
    if (external?.aborted) controller.abort();
    const timer = setTimeout(cancel, timeout);
    try {
      const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Local request failed (${response.status}).`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Request stopped or timed out. The local process may still be finishing; you can use keyword search.');
      if (error instanceof TypeError) { live.backend = 'unavailable'; throw new Error('Local backend is unavailable. Keep start-windows.bat running, then retry.'); }
      throw error;
    } finally { clearTimeout(timer); external?.removeEventListener('abort', cancel); }
  }

  async function refresh(update = true, fresh = false) {
    const results = await Promise.allSettled([api(`/api/health${fresh ? '?fresh=true' : ''}`, {}, 10000), api('/api/documents', {}, 10000), api('/api/machines', {}, 10000)]);
    if (results[0].status === 'fulfilled') { live.health = results[0].value; live.backend = 'ready'; }
    else { live.health = null; live.backend = 'unavailable'; }
    if (results[1].status === 'fulfilled') live.documents = results[1].value.documents;
    if (results[2].status === 'fulfilled') applyMachines(results[2].value.machines);
    // Keep refreshing while the built-in library is still being indexed.
    clearTimeout(refresh.timer);
    if (['waiting', 'scanning'].includes(live.health?.library?.state) || ['downloading', 'indexing'].includes(live.health?.web_sources?.state)) refresh.timer = setTimeout(() => refresh(!document.querySelector('#modal-root')?.firstChild && !document.activeElement?.matches('input,textarea,select')), 2000);
    if (update) render();
  }

  function reset() {
    live.request++; askController?.abort(); live.asking = false; live.result = null; live.error = ''; setQuery('');
  }

  function select(id) {
    reset(); live.selection[getMachine()] = id;
    try { localStorage.setItem('torquedoc-manual-selections', JSON.stringify(live.selection)); } catch {}
    render();
  }

  function evidenceCard(p, index, answer = false) {
    return `<article class="panel evidence-card ${answer ? 'evidence-selected' : ''}">
      <div class="panel-header"><h2>${icon('book', 17)}${answer ? 'Source passage' : 'Search match'} ${index + 1}</h2><span class="badge badge-amber mono">PDF PAGE ${p.page}</span></div>
      <div class="evidence-content"><div class="source-title">${esc(p.title)} ${p.source ? `<span class="source-chip source-chip--${p.source === 'builtin' ? 'builtin' : 'update'}">${sourceLabel(p)}</span>` : ''}${p.type === 'web' ? webChip : ''}</div><div class="evidence-meta">${esc(p.variant)} · ${esc(p.revision)}${p.page_label !== String(p.page) ? ` · Page label ${esc(p.page_label)}` : ''}${p.type === 'web' ? ` · ${webLink(p)}` : ''}</div>
      <blockquote class="manual-excerpt">${highlight(p.text, live.result?.terms)}</blockquote>
      <button class="button button-secondary" data-action="live-source" data-id="${esc(p.document_id)}" data-page="${p.page}">${icon('arrow-up-right', 16)}Open original page ${p.page}</button></div></article>`;
  }

  function assistant() {
    const docs = machineDocs(), current = currentDocs(), replaced = docs.filter(d => d.superseded_by), document = selected();
    const library = live.health?.library || {};
    const indexing = ['waiting', 'scanning'].includes(library.state);
    const ready = live.health?.engine?.state === 'ready';
    let body;
    if (live.asking) body = `<section class="panel live-empty" role="status"><span class="btn-spinner"></span><h2>Searching ${document ? 'the selected manual' : `all ${current.length} manuals for this machine`}…</h2><p>${window.TorqueDocWeb ? "Local AI may take a few minutes on this device. You can cancel and use keyword search anytime." : "Local AI may take up to two minutes to load and check the passages. Your files stay on this computer."}</p><button class="button button-secondary" data-action="cancel-query">${window.TorqueDocWeb ? "Cancel question" : "Stop waiting"}</button></section>`;
    else if (live.error) body = `<section class="panel live-empty" role="alert">${icon('alert', 30)}<h2>Could not complete this request.</h2><p>${esc(live.error)}</p><button class="button button-secondary" data-action="refresh-engine">Check local connection</button></section>`;
    else if (live.result) {
      const r = live.result, supported = r.status === 'supported';
      body = `<div class="live-result-heading"><div class="eyebrow">${supported ? 'LOCAL AI · SOURCE EXTRACT' : r.status === 'search_only' ? 'KEYWORD SEARCH · NO AI ANSWER' : 'NO SUPPORTED ANSWER'}</div><h2>${esc(r.question)}</h2><p>${esc(r.message)}</p></div>
        ${supported ? r.evidence.map((p, i) => evidenceCard(p, i, true)).join('') : ''}
        ${supported ? `<div class="live-result-actions"><button class="button button-secondary" data-action="copy-answer">${icon('copy',16)}Copy passages & citations</button><button class="button button-secondary" data-action="add-log">${icon('plus',16)}Add repair note</button></div>` : ''}
        <div class="live-note">${icon('info', 18)}<span>${esc(r.notice)}</span></div>
        ${[...r.evidence, ...r.matches].some(p => p.type === 'web') ? `<div class="live-note web-note">${icon('alert', 18)}<span>Some results come from saved web pages, not OEM manuals. Web information can be incomplete, outdated or wrong; confirm it in the manufacturer's documentation.</span></div>` : ''}
        ${r.matches.length ? `<details class="search-matches" ${supported ? '' : 'open'}><summary>${supported ? 'Other retrieved passages' : 'Inspect keyword matches'} (${r.matches.length})</summary>${r.matches.map((p, i) => evidenceCard(p, i)).join('')}</details>` : `<section class="panel live-empty"><h3>No passage to cite.</h3><p>Try a precise component name or part number${document ? ', or search all manuals for this machine' : ''}. No specification has been generated.</p></section>`}`;
    } else body = `<section class="panel live-welcome"><div class="eyebrow">THE MANUALS ARE BUILT IN</div><h2>Every manual for this machine,<br>available offline.</h2><p>${current.length ? `Ask about a component, specification, or fault code. TorqueDoc searches ${current.length === 1 ? 'the' : `all ${current.length}`} current manual${current.length === 1 ? '' : 's'} for ${esc(machineNames[getMachine()])} and shows the original pages it found.` : indexing ? 'The built-in library is still being prepared. Questions work as soon as this machine\'s manuals are indexed.' : `No manuals are included for ${esc(machineNames[getMachine()])} yet. Add its PDFs to the library folder, or add an update below.`}</p><div class="live-workflow"><div><span>01</span><strong>Ask or search</strong><p>All current manuals for the selected machine.</p></div><div><span>02</span><strong>Check the source</strong><p>Read the full page, conditions and sequence.</p></div><div><span>03</span><strong>Add updates</strong><p>New revisions or bulletins replace older pages.</p></div></div><div class="live-welcome-actions"><button class="button button-secondary" data-action="import-documents">${icon('upload',16)}Add an update</button><button class="button button-secondary" data-action="add-web">${icon('arrow-up-right',16)}Add web page</button></div><p class="live-small">The Training rig workspace includes a fictional test manual. Never use it for real maintenance.</p></section>`;
    return `<div class="page-title-row"><div><h1>Technical assistant<span class="text-amber">.</span></h1><p>Your manuals. Your machine. Evidence you can inspect.</p></div><button class="button button-secondary" data-action="history">${icon('history',16)}Service history</button></div>
      <section class="manual-scope panel"><div class="manual-scope-label">${icon('book',20)}<label for="manual-selector">Search in<small>Citations always name the manual</small></label></div><select id="manual-selector" aria-label="Select manuals to search"><option value="">${current.length ? `All manuals for this machine (${current.length})` : indexing ? 'Preparing built-in manuals…' : 'No manuals for this machine yet'}</option>${current.length ? `<optgroup label="One manual">${current.map(d => `<option value="${esc(d.id)}" ${document?.id === d.id ? 'selected' : ''}>${esc(d.title)} · ${esc(d.revision)}</option>`).join('')}</optgroup>` : ''}${replaced.length ? `<optgroup label="Replaced by an update">${replaced.map(d => `<option value="${esc(d.id)}" ${document?.id === d.id ? 'selected' : ''}>${esc(d.title)} · ${esc(d.revision)} (replaced)</option>`).join('')}</optgroup>` : ''}</select><button class="icon-button" data-action="import-documents" aria-label="Add an update">${icon('upload',20)}</button>
      ${document ? `<div class="manual-scope-meta"><span>${esc(document.variant)}</span><span class="mono">${sourceLabel(document)} · ${esc(prettyStatus(document))}</span><button class="button button-ghost" data-action="live-source" data-id="${esc(document.id)}" data-page="1">View manual ${icon('arrow-up-right',14)}</button></div>${document.superseded_by ? `<div class="live-note">${icon('alert',18)}<span>This manual was replaced by ${esc(titleOf(document.superseded_by))}. You are searching the older revision on purpose.</span></div>` : ''}` : current.length ? `<div class="manual-scope-meta"><span>${current.filter(d => d.source === 'builtin').length} built-in · ${current.filter(d => d.source !== 'builtin').length} update${current.filter(d => d.source !== 'builtin').length === 1 ? '' : 's'}</span><span class="mono">Current revisions only</span><button class="button button-ghost" data-action="navigate" data-screen="library">Browse manuals ${icon('arrow-up-right',14)}</button></div>` : ''}</section>
      ${indexing ? `<div class="live-note library-progress" role="status">${icon('rotate',18)}<span>Preparing the built-in library: ${library.done || 0} of ${library.total || '…'} manuals indexed. Search covers the finished ones; this happens once.</span></div>` : ''}
      <div class="engine-strip"><span class="${ready ? 'text-teal' : 'text-amber'}">${icon('chip',16)}${ready ? `Local AI installed · ${esc(modelName())}` : live.backend === 'checking' ? 'Checking local engine…' : live.backend === 'ready' ? 'Keyword search ready · AI needs setup' : 'Start the local backend to search'}</span>${live.health?.network_mode === 'on_device' && !ready ? `<button data-action="settings" class="button button-ghost">${icon('settings',14)}Set up AI</button>` : `<button data-action="refresh-engine" class="button button-ghost">${icon('rotate',14)}Recheck</button>`}</div>
      <section class="query-area" aria-label="Ask a technical question"><form id="query-form" class="query-box"><span class="query-symbol">${icon('assistant',22)}</span><label class="sr-only" for="technical-query">Technical question</label><input id="technical-query" name="query" placeholder="${document ? 'Ask about the selected manual…' : 'Ask about this machine…'}" value="${esc(getQuery())}" maxlength="700" autocomplete="off" ${live.asking ? 'disabled' : ''}/><button class="button button-primary query-submit" type="submit" ${live.asking ? 'disabled' : ''}><span>Ask TorqueDoc</span>${icon('arrow-right',17)}</button></form><div class="suggestions"><button class="suggestion" data-action="keyword-search">${icon('search',14)}Search without AI</button><span>TRY A COMPONENT NAME, FAULT CODE, OR PART NUMBER</span></div></section>
      ${document?.status === 'partial' || document?.status === 'needs_ocr' ? `<div class="live-note">${icon('alert',18)}<span>${document.pages - document.text_pages} page(s) have little or no readable text. Search may miss scanned pages, images or diagrams. OCR is not enabled; inspect original pages.</span></div>` : ''}
      <div id="live-answer" aria-live="polite">${body}</div>`;
  }

  async function ask(raw, searchOnly = false) {
    const question = raw.trim();
    if (!question) { toast('Enter a question or a technical search term.'); return; }
    if (live.backend === 'checking') { await refresh(false); }
    if (!machineDocs().length) { toast('No manuals for this machine yet. Add its PDFs to the built-in library, or add an update.'); return; }
    askController?.abort(); askController = new AbortController();
    const request = ++live.request, documentId = selected()?.id || null, machine = getMachine();
    setQuery(question); live.asking = true; live.error = ''; live.result = null; navigate('assistant');
    try {
      const result = await api('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, signal:askController.signal, body:JSON.stringify({question, document_id:documentId, machine, search_only:searchOnly})}, window.TorqueDocWeb ? 300000 : 150000);
      if (request === live.request) live.result = result;
    } catch (error) { if (request === live.request) live.error = error.message; }
    finally { if (request === live.request) { live.asking = false; render(); } }
  }

  function bind() {
    document.getElementById('manual-selector')?.addEventListener('change', e => select(e.target.value));
    document.getElementById('technical-query')?.addEventListener('input', e => setQuery(e.target.value));
  }

  async function importFiles(files, legacyId = null) {
    if (live.importing) { toast('A manual import is already running.'); return; }
    if (!files.length) return;
    if (files.some(f => !f.name.toLowerCase().endsWith('.pdf') || f.size > 50 * 1024 * 1024)) { toast('Choose PDF files up to 50 MB each. Images need OCR before importing.'); return; }
    const machine = getMachine(), many = files.length > 1, preset = pendingSupersedes;
    pendingSupersedes = null;
    const replaceable = currentDocs();
    const presetDoc = replaceable.find(d => d.id === preset);
    const fields = (file, i) => `<fieldset class="import-file" data-file-index="${i}" ${i ? 'hidden' : ''}><legend>${many ? (i ? esc(file.name) : `<span data-shared-label>All ${files.length} files</span><span data-file-label hidden>${esc(file.name)}</span>`) : 'Manual details'}</legend>
      <label class="form-field">Exact equipment / engine variant<input id="import-variant${i ? `-${i}` : ''}" data-field="variant" ${i ? '' : 'required'} maxlength="120" placeholder="e.g. C6.4 · serial prefix / applicable range" value="${!i && presetDoc && !presetDoc.variant.startsWith('Not listed') ? esc(presetDoc.variant) : ''}"></label>
      <label class="form-field">Revision or publication date<input id="import-revision${i ? `-${i}` : ''}" data-field="revision" maxlength="120" placeholder="As printed in the manual, or leave blank"></label>
      <label class="form-field replaces-field" ${many && !i ? 'hidden' : ''}>Replaces<select id="import-supersedes${i ? `-${i}` : ''}" data-field="supersedes"><option value="">Nothing · this is an additional document</option>${replaceable.map(d => `<option value="${esc(d.id)}" ${!i && preset === d.id ? 'selected' : ''}>${esc(d.title)} · ${esc(d.revision)} (${sourceLabel(d)})</option>`).join('')}</select><small>The replaced manual stays viewable but is no longer searched.</small></label>
      <label class="form-field">Document type<select id="import-kind${i ? `-${i}` : ''}" data-field="kind">${Object.entries(kindLabels).filter(([value]) => value !== 'web').map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select></label></fieldset>`;
    openModal('Add an update', `${files.length} PDF${many ? 's' : ''} · ${machineNames[machine]}`,
      `<form id="import-form"><div class="live-note">${icon('info',18)}<span>Use this for newer revisions, service bulletins or documents not yet in the built-in library. Enter the applicability printed on the document; it is not detected automatically.</span></div><p class="import-file-names">${files.map(f => esc(f.name)).join('<br>')}</p>${many ? '<label class="import-same"><input type="checkbox" id="import-same" checked> Same variant, revision and type for every file</label>' : ''}${files.map(fields).join('')}<p class="live-small">Text PDFs are searchable. Scanned pages remain viewable but need OCR. Different revisions stay separate; currency and conflicts need manual review.</p><p id="import-error" role="alert" class="text-amber"></p></form>`,
      `<button class="button button-secondary" data-action="close-modal">Cancel</button><button id="import-confirm" class="button button-primary" type="submit" form="import-form">${icon('upload',16)}Save update</button>`);
    const sameBox = document.getElementById('import-same');
    sameBox?.addEventListener('change', () => {
      document.querySelectorAll('.import-file').forEach((set, i) => {
        if (i) { set.hidden = sameBox.checked; set.querySelector('[data-field="variant"]').required = !sameBox.checked; }
        else set.querySelector('.replaces-field').hidden = sameBox.checked;
      });
      document.querySelector('[data-shared-label]').hidden = !sameBox.checked;
      document.querySelector('[data-file-label]').hidden = sameBox.checked;
    });
    const details = i => {
      const set = document.querySelector(`.import-file[data-file-index="${sameBox?.checked === false ? i : 0}"]`);
      const value = name => set.querySelector(`[data-field="${name}"]`).value.trim();
      const shared = sameBox?.checked !== false && many;
      return {variant: value('variant'), revision: value('revision') || 'Not supplied', kind: value('kind'), supersedes: shared ? '' : value('supersedes')};
    };
    document.getElementById('import-form').addEventListener('submit', async event => {
      event.preventDefault(); if (live.importing) return;
      const metadata = files.map((file, i) => details(i));
      if (metadata.some(m => !m.variant)) return;
      live.importing = true;
      document.getElementById('import-confirm').disabled = true;
      document.getElementById('import-error').textContent = 'Extracting PDF text and indexing on this computer…';
      let imported = 0, last;
      try {
        for (const [i, file] of files.entries()) {
          const {variant, revision, kind, supersedes} = metadata[i];
          const form = new FormData(); form.append('file', file); form.append('machine', machine); form.append('variant', variant); form.append('revision', revision); form.append('kind', kind); form.append('supersedes', supersedes);
          last = await api('/api/documents', {method:'POST', body:form}, 180000); imported++;
        }
        if (legacyId) { try { localStorage.setItem(`torquedoc-migrated-${legacyId}`, last.id); } catch {} }
        await refresh(false); await readImports();
        reset(); closeModal(); navigate('assistant');
        toast(`${imported} update${imported === 1 ? '' : 's'} saved. ${prettyStatus(last)}${last.duplicate ? ' · Existing copy reused.' : '.'} Searches now include ${imported === 1 ? 'it' : 'them'}.`);
      } catch (error) {
        if (imported) await refresh(false);
        const message = `${imported ? `${imported} file(s) saved. ` : ''}${files[imported] ? `${files[imported].name}: ` : ''}${error.message}`;
        const errorBox = document.getElementById('import-error');
        if (errorBox) errorBox.textContent = message; else toast(message);
        const button = document.getElementById('import-confirm'); if (button) button.disabled = false;
      } finally { live.importing = false; const input = document.getElementById('file-input'); if (input) input.value = ''; }
    });
  }

  async function source(id, number = 1) {
    const manual = live.documents.find(d => d.id === id);
    if (!manual) { toast('Refresh the library to locate this manual.'); return; }
    const page = Math.min(manual.pages, Math.max(1, Number(number) || 1)), request = ++pageRequest;
    openModal(manual.title, `${manual.variant} · ${manual.revision}`, `<div class="live-empty" data-source-loading="${request}">Loading original page ${page}…</div>`, '', true);
    try {
      const detail = await api(`/api/documents/${encodeURIComponent(id)}/pages/${page}`, {}, 15000);
      if (request !== pageRequest || !document.querySelector(`[data-source-loading="${request}"]`)) return;
      const base = `/api/documents/${encodeURIComponent(id)}`;
      openModal(manual.title, `${manual.variant} · ${manual.revision}`,
        `<div class="source-controls"><button class="button button-secondary" data-action="live-source" data-id="${esc(id)}" data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}>${icon('chevron-left',16)}Previous</button><form id="page-form"><label for="source-page">PDF page</label><input id="source-page" type="number" min="1" max="${manual.pages}" value="${page}"><span>of ${manual.pages}</span><button class="button button-secondary" type="submit">Go</button></form><button class="button button-secondary" data-action="live-source" data-id="${esc(id)}" data-page="${page + 1}" ${page === manual.pages ? 'disabled' : ''}>Next${icon('chevron-right',16)}</button></div>
        ${manual.type === 'web' ? `<div class="live-note web-note">${icon('alert',18)}<span>Saved web page, not an OEM manual. ${manual.url ? `Source: ${webLink(manual)}` : ''}</span></div>` : ''}
        ${manual.superseded_by ? `<div class="live-note">${icon('alert',18)}<span>Replaced by ${esc(titleOf(manual.superseded_by))}. This older revision is not included in searches.</span></div>` : ''}
        <p class="live-small">${sourceLabel(manual)} · original PDF rendering · page label ${esc(detail.label)}. Check tables, conditions and adjacent pages. This page may contain diagrams that are not searchable.</p>
        <div class="pdf-page-scroll"><img class="source-page-image" data-source-page="${request}" ${window.TorqueDocWeb ? '' : `src="${base}/pages/${page}/image"`} alt="Original PDF page ${page} of ${esc(manual.title)}"><p class="page-image-error" hidden>The page image could not load.${window.TorqueDocWeb ? '' : ' Use Open PDF below.'}</p></div>
        <details class="source-text"><summary>Extracted text (layout may differ)</summary><pre>${esc(detail.text || 'No readable text on this page. OCR is not enabled.')}</pre></details>`,
        `${manual.source === 'builtin' ? `<button class="button button-ghost" data-action="update-manual" data-id="${esc(id)}">${icon('upload',16)}Add update for this manual</button>` : `<button class="button button-ghost button-danger" data-action="delete-manual" data-id="${esc(id)}">Delete update</button><button class="button button-ghost" data-action="edit-manual" data-id="${esc(id)}">Edit details</button>`}<a class="button button-secondary open-pdf" href="${base}/file#page=${page}" target="_blank" rel="noopener">${icon('arrow-up-right',16)}Open PDF</a><button class="button button-primary" data-action="use-manual" data-id="${esc(id)}">Ask this manual</button>`, true);
      document.getElementById('page-form').addEventListener('submit', event => { event.preventDefault(); source(id, document.getElementById('source-page').value); });
      const showImageError = () => { const message = document.querySelector('.page-image-error'); if (message) message.hidden = false; };
      document.querySelector('.source-page-image').addEventListener('error', showImageError);
      if (window.TorqueDocWeb) {  // phone app: pages are drawn from the built-in PDF on the device
        window.TorqueDocWeb.pageImage(manual, page).then(url => { const image = document.querySelector(`[data-source-page="${request}"]`); if (image) image.src = url; }).catch(showImageError);
      }
    } catch (error) { if (request === pageRequest) { closeModal(); toast(error.message); } }
  }

  function settings() {
    if (window.TorqueDocWeb) {  // phone app: built-in library and on-device AI
      const view = window.TorqueDocWeb.settings({icon, esc, live});
      openModal(view.title, view.subtitle, view.body, view.footer);
      return;
    }
    const engine = live.health?.engine;
    openModal('Local engine & storage', 'TorqueDoc core MVP',
      `<span data-settings-modal hidden></span><div class="setting-row"><div><strong>Python backend</strong><p>Keep the launcher running while using TorqueDoc.</p></div><span class="badge badge-${live.backend === 'ready' ? 'teal' : 'amber'}">${esc(live.backend)}</span></div>
      <div class="setting-row"><div><strong>Local AI · ${esc(modelName())}</strong><p>${esc(engine?.message || 'Start the backend and use Recheck.')}</p></div><span class="badge badge-amber">${esc(engine?.state || 'Unknown')}</span></div>
      <div class="setup-command"><span>One-time model download (internet needed)</span><code>ollama pull ${esc(modelName())}</code><p>After installation, start Ollama with cloud features disabled as described in README.md. TorqueDoc only calls its loopback endpoint.</p></div>
      <div class="setting-row"><div><strong>Built-in library</strong><p>${live.health?.builtin_documents ?? 0} manual(s) included with the application, indexed on this computer. ${({waiting:'Waiting to start indexing.', scanning:`Indexing ${live.health?.library?.done || 0} of ${live.health?.library?.total || '…'}.`, missing:'The library folder is missing.', none:''})[live.health?.library?.state] || 'Ready.'}</p>${live.health?.library?.errors?.length ? `<details class="library-errors"><summary>${live.health.library.errors.length} library file(s) could not be indexed</summary><ul>${live.health.library.errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></details>` : ''}</div><span class="badge badge-${live.health?.library?.state === 'ready' ? 'teal' : 'amber'}">${esc(live.health?.library?.state || 'unknown')}</span></div>
      ${(() => { const w = live.health?.web_sources || {}; const busy = ['downloading', 'indexing'].includes(w.state); return `<div class="setting-row"><div><strong>Web sources</strong><p>${w.listed || 0} listed in the library catalog · ${w.saved || 0} saved for offline use. ${busy ? (w.state === 'indexing' ? 'Adding them to the library…' : `Downloading ${Math.min((w.done || 0) + 1, w.total || 1)} of ${w.total || '…'}…`) : 'Downloading needs internet once; the saved copies then work offline.'}</p>${w.errors?.length ? `<details class="library-errors"><summary>${w.errors.length} web source(s) could not be saved</summary><ul>${w.errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></details>` : ''}</div><button class="button button-secondary" data-action="download-web" ${busy || !w.listed ? 'disabled' : ''}>${busy ? 'Working…' : w.saved ? 'Refresh' : 'Download'}</button></div>`; })()}
      <div class="setting-row"><div><strong>Updates you added</strong><p>${live.documents.filter(d => d.source === 'update').length} update(s) stored in the app's data folder. Search and page viewing do not need AI.</p></div><span class="mono">${bytes(live.health?.manual_bytes || 0)}</span></div>
      <div class="setting-row"><div><strong>Maintenance notes</strong><p>Saved on this computer. Export them as a backup or to move them; Import adds notes from an export (for example from the browser version).</p></div><span class="setting-actions"><button class="button button-secondary" data-action="import-logs">Import logs</button><button class="button button-secondary" data-action="export-logs">Export logs</button></span></div>
      <div class="live-note">${icon('info',18)}<span>OCR, voice, automatic revision checking, schematic interpretation and shop sync are not part of this build. Wiring and diagnostics screens are design previews.</span></div>`,
      `<button class="button button-secondary" data-action="refresh-engine">Recheck engine</button><button class="button button-primary" data-action="close-modal">Done</button>`);
  }

  function addWeb() {
    const machine = getMachine();
    openModal('Add web page', machineNames[machine],
      `<form id="web-form"><div class="live-note">${icon('info',18)}<span>TorqueDoc downloads the page once (internet needed now) and keeps an offline copy that is searched and cited like a manual, with its web address and save date. Pages that need a login or JavaScript may not save.</span></div>
      <label class="form-field">Web address<input id="web-url" type="url" required maxlength="2000" placeholder="https://…" inputmode="url" autocomplete="off"></label>
      <label class="form-field">Exact equipment / engine variant it covers<input id="web-variant" required maxlength="120" placeholder="e.g. 320D, serial prefix … (as stated on the page)"></label>
      <label class="form-field">Title<input id="web-title" maxlength="220" placeholder="Optional · the page title is used if blank"></label>
      <label class="form-field replaces-field">Replaces<select id="web-supersedes"><option value="">Nothing · additional source</option>${currentDocs().filter(d => d.type === 'web').map(d => `<option value="${esc(d.id)}">${esc(d.title)} · ${esc(d.revision)}</option>`).join('')}</select><small>Use this to refresh an older saved copy of the same page.</small></label>
      <p class="live-small">Web pages are not OEM documentation. Results from them are labeled, and answers should be confirmed in the manufacturer's manual.</p><p id="web-error" role="alert" class="text-amber"></p></form>`,
      `<button class="button button-secondary" data-action="close-modal">Cancel</button><button id="web-confirm" class="button button-primary" type="submit" form="web-form">${icon('download',16)}Save for offline use</button>`);
    document.getElementById('web-form').addEventListener('submit', async event => {
      event.preventDefault();
      const value = name => document.getElementById(`web-${name}`).value.trim();
      if (!value('url') || !value('variant')) return;
      const button = document.getElementById('web-confirm'), errorBox = document.getElementById('web-error');
      button.disabled = true; errorBox.textContent = 'Downloading the page and saving an offline copy…';
      try {
        const saved = await api('/api/web', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url:value('url'), machine, variant:value('variant'), title:value('title'), supersedes:value('supersedes') || null})}, 90000);
        reset(); await refresh(false); closeModal(); navigate('assistant');
        toast(`Saved “${saved.title}” for offline use.${saved.duplicate ? ' An identical copy already existed.' : ''}`);
      } catch (error) { if (document.getElementById('web-error')) { errorBox.textContent = error.message; button.disabled = false; } else toast(error.message); }
    });
  }

  async function downloadWebSources(button) {
    button.disabled = true;
    try {
      await api('/api/library/web-sources', {method:'POST'}, 15000);
      toast('Downloading web sources. They are added to the library as each one finishes.');
      await refresh(false); settings();
    } catch (error) { button.disabled = false; toast(error.message); }
  }

  function editManual(id) {
    const manual = live.documents.find(d => d.id === id);
    if (!manual) { toast('Refresh the library to locate this manual.'); return; }
    openModal('Edit manual details', manual.title,
      `<form id="edit-form"><div class="live-note">${icon('info',18)}<span>Correct the details entered at import. The stored PDF and its search index are not changed.</span></div>
      <label class="form-field">Fleet workspace<select id="edit-machine">${Object.entries(machineNames).map(([value, label]) => `<option value="${value}" ${manual.machine === value ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select></label>
      <label class="form-field">Exact equipment / engine variant<input id="edit-variant" required maxlength="120" value="${esc(manual.variant)}"></label>
      <label class="form-field">Revision or publication date<input id="edit-revision" maxlength="120" value="${esc(manual.revision === 'Not supplied' ? '' : manual.revision)}" placeholder="As printed in the manual, or leave blank"></label>
      <label class="form-field">Document type<select id="edit-kind">${Object.entries(kindLabels).filter(([value]) => (value === 'web') === (manual.type === 'web')).map(([value, label]) => `<option value="${value}" ${manual.type === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
      <label class="form-field">Replaces<select id="edit-supersedes"><option value="">Nothing · additional document</option>${live.documents.filter(d => d.machine === manual.machine && d.id !== id && (!d.superseded_by || d.superseded_by === id)).map(d => `<option value="${esc(d.id)}" ${d.superseded_by === id ? 'selected' : ''}>${esc(d.title)} · ${esc(d.revision)} (${sourceLabel(d)})</option>`).join('')}</select><small>Only manuals for the same workspace can be replaced.</small></label>
      <p id="edit-error" role="alert" class="text-amber"></p></form>`,
      `<button class="button button-secondary" data-action="close-modal">Cancel</button><button id="edit-confirm" class="button button-primary" type="submit" form="edit-form">${icon('check',16)}Save details</button>`);
    document.getElementById('edit-form').addEventListener('submit', async event => {
      event.preventDefault();
      const value = name => document.getElementById(`edit-${name}`).value.trim();
      if (!value('variant')) return;
      document.getElementById('edit-confirm').disabled = true;
      try {
        const updated = await api(`/api/documents/${encodeURIComponent(id)}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({machine:value('machine'), variant:value('variant'), revision:value('revision') || 'Not supplied', kind:value('kind'), supersedes:value('machine') === manual.machine ? value('supersedes') || null : null})}, 15000);
        if (updated.machine !== manual.machine && live.selection[manual.machine] === id) {
          delete live.selection[manual.machine]; live.selection[updated.machine] = id;
          try { localStorage.setItem('torquedoc-manual-selections', JSON.stringify(live.selection)); } catch {}
        }
        reset(); await refresh(false); closeModal(); render();
        toast(updated.machine === manual.machine ? 'Manual details updated.' : `Manual moved to ${machineNames[updated.machine]}.`);
      } catch (error) {
        document.getElementById('edit-error').textContent = error.message;
        document.getElementById('edit-confirm').disabled = false;
      }
    });
  }

  function confirmDelete(id) {
    const manual = live.documents.find(d => d.id === id);
    if (!manual) { toast('Refresh the library to locate this manual.'); return; }
    openModal('Delete this update?', manual.title,
      `<div class="live-note">${icon('alert',18)}<span>This removes the uploaded PDF, its extracted text and its search index from this computer.${live.documents.some(d => d.superseded_by === id) ? ' The manual it replaced becomes current again.' : ''} Built-in manuals and maintenance notes are kept.</span></div><p class="live-small">${esc(manual.variant)} · ${esc(manual.revision)} · ${manual.pages} pages</p>`,
      `<button class="button button-secondary" data-action="close-modal">Keep manual</button><button class="button button-primary button-danger" data-action="confirm-delete" data-id="${esc(id)}">Delete permanently</button>`);
  }

  async function deleteManual(id, button) {
    button.disabled = true;
    try {
      await api(`/api/documents/${encodeURIComponent(id)}`, {method:'DELETE'}, 15000);
      for (const [machine, selectedId] of Object.entries(live.selection)) if (selectedId === id) delete live.selection[machine];
      try { localStorage.setItem('torquedoc-manual-selections', JSON.stringify(live.selection)); } catch {}
      reset(); await refresh(false); await readImports(); closeModal(); render();
      toast('Update deleted from this computer.');
    } catch (error) { button.disabled = false; toast(error.message); }
  }

  async function action(name, target) {
    if (name === 'import-documents') { pendingSupersedes = null; return false; }
    if (window.TorqueDocWeb?.action(name, target)) return true;
    if (name === 'edit-manual') { editManual(target.dataset.id); return true; }
    if (name === 'add-web') { closeModal(); addWeb(); return true; }
    if (name === 'download-web') { downloadWebSources(target); return true; }
    if (name === 'update-manual') { pendingSupersedes = target.dataset.id; closeModal(); document.getElementById('file-input')?.click(); return true; }
    if (name === 'delete-manual') { confirmDelete(target.dataset.id); return true; }
    if (name === 'confirm-delete') { deleteManual(target.dataset.id, target); return true; }
    if (name === 'refresh-engine') { toast('Checking local backend and model…'); await refresh(true, true); if (document.querySelector('[data-settings-modal]')) settings(); return true; }
    if (name === 'keyword-search') { ask(document.getElementById('technical-query')?.value || getQuery(), true); return true; }
    if (name === 'cancel-query') { live.request++; askController?.abort(); live.asking = false; live.error = window.TorqueDocWeb ? 'Question cancelled. You can use keyword search now.' : 'Stopped waiting. You can run a keyword search while the local model finishes.'; render(); return true; }
    if (name === 'live-source') { source(target.dataset.id, target.dataset.page); return true; }
    if (name === 'use-manual') { select(target.dataset.id); closeModal(); navigate('assistant'); return true; }
    if (name === 'index-legacy') {
      try {
        const database = await db();
        const item = await new Promise((resolve,reject) => {const r=database.transaction('documents').objectStore('documents').get(target.dataset.id); r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error);});
        if (!item?.blob) throw new Error('Original file is unavailable. Import the PDF again.');
        closeModal(); importFiles([new File([item.blob], item.title, {type:'application/pdf'})], item.id);
      } catch (error) { toast(error.message); }
      return true;
    }
    return false;
  }

  function copyText() {
    if (live.result?.status !== 'supported') return '';
    return `TorqueDoc — original manual passages (check applicability before service)\nQuestion: ${live.result.question}\n\n${live.result.evidence.map(p => `${p.text}\nSource: ${p.title}; ${p.variant}; revision ${p.revision}; PDF page ${p.page} (label ${p.page_label})${p.url ? `; web page ${p.url} (not an OEM manual)` : ''}.`).join('\n\n')}\n\n${live.result.notice}`;
  }

  window.TorqueDocWeb?.attach({refresh, render, settings, toast});
  return {live, refresh, reset, select, assistant, ask, bind, importFiles, source, settings, action, copyText,
    documents: () => machineDocs().map(d => ({...d, server:true, size:bytes(d.bytes), replacedBy: d.superseded_by ? titleOf(d.superseded_by) : '', host: d.url ? (() => { try { return new URL(d.url).hostname; } catch { return ''; } })() : ''})),
    status: () => live.backend === 'ready' ? live.health?.engine?.state === 'ready' ? 'LOCAL AI INSTALLED' : 'LOCAL SEARCH READY' : live.backend === 'checking' ? 'CHECKING LOCAL ENGINE' : 'BACKEND DISCONNECTED',
    storedBytes: () => bytes(live.health?.manual_bytes || 0)};
}
