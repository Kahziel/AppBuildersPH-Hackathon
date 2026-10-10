const escape = (value = '') => String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));

const typeLabels = { manual: 'Shop manual', schematic: 'Schematic', bulletin: 'Service bulletin', web: 'Web page', import: 'Local import' };
const typeIcons = { manual: 'book', schematic: 'circuit', bulletin: 'alert', web: 'arrow-up-right', import: 'file' };
const logTimeFormatter = new Intl.DateTimeFormat('en-PH', { dateStyle: 'medium', timeStyle: 'short' });

function readableLogTime(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.getTime()) ? logTimeFormatter.format(date) : String(value || 'Time not recorded');
}

function readableMachine(value, machineName) {
  const name = String(value || '').trim();
  return !name || /^[a-z\d_-]+$/.test(name) ? machineName : name;
}

export function renderLibrary({ icon, documents = [], logs = [], query = '', filter = 'all', machineName = 'Selected machine' }) {
  const term = String(query).trim().toLowerCase();
  const matchesFilter = (document) => filter === 'all' || (filter === 'update' ? document.source === 'update' || document.status === 'legacy' : document.type === filter);
  const filtered = documents.filter((document) => matchesFilter(document) && `${document.title} ${document.revision} ${document.variant || ''} ${typeLabels[document.type] || ''}`.toLowerCase().includes(term));
  const notices = documents.filter((document) => ['needs_ocr','partial','legacy'].includes(document.status)).length;
  const builtin = documents.filter((document) => document.source === 'builtin').length;
  const updates = documents.filter((document) => document.source === 'update').length;
  const filters = [['all', 'All files'], ['manual', 'Manuals'], ['schematic', 'Schematics'], ['bulletin', 'Bulletins'], ['web', 'Web pages'], ['update', 'Updates']];
  const documentRows = filtered.map((document) => {
    const isImported = document.type === 'import' || document.status === 'imported';
    const replaced = Boolean(document.superseded_by);
    const status = replaced ? 'Replaced' : document.status === 'needs_ocr' ? 'Needs OCR' : document.status === 'partial' ? 'Partly indexed' : document.status === 'legacy' ? 'Not indexed' : 'Text indexed';
    const warn = replaced || ['needs_ocr','partial','legacy'].includes(document.status);
    const origin = (document.source === 'builtin' ? '<span class="source-chip source-chip--builtin">Built-in</span>' : document.source === 'update' ? '<span class="source-chip source-chip--update">Update</span>' : '') + (document.type === 'web' ? '<span class="source-chip source-chip--web">Web</span>' : '');
    return `<button class="library-document ${replaced ? 'library-document--replaced' : ''}" data-action="open-document" data-id="${escape(document.id)}" aria-label="Open ${escape(document.title)}" ${replaced ? `title="Replaced by ${escape(document.replacedBy)}"` : ''}>
      <span class="library-file-symbol library-file-symbol--${document.type === 'schematic' ? 'cyan' : 'amber'}">${icon(typeIcons[document.type] || 'file')}</span>
      <span class="library-file-info"><strong>${escape(document.title)} ${origin}</strong><span>${escape(typeLabels[document.type] || 'Document')} <span class="library-dot">·</span> ${escape(document.variant || 'Assign equipment when indexing')} <span class="library-dot">·</span> ${escape(document.revision || 'Revision not supplied')}${document.pages ? ` <span class="library-dot">·</span> ${escape(document.pages)} pages` : ''}${document.host ? ` <span class="library-dot">·</span> ${escape(document.host)}` : ''}${replaced ? ` <span class="library-dot">·</span> Replaced by ${escape(document.replacedBy)}` : ''}</span></span>
      <span class="library-file-size mono">${escape(document.size || '—')}</span>
      <span class="library-file-state ${warn ? 'library-file-state--warning' : ''}">${icon(warn ? 'alert' : 'check')}<span>${escape(status)}</span></span>
      <span class="library-file-arrow">${icon('chevron-right')}</span>
    </button>`;
  }).join('');
  const recentLogs = logs.slice(0, 5).map((log) => `<article class="library-log-item">
    <span class="library-log-mark">${icon(log.kind === 'fault' ? 'check' : log.kind === 'torque' ? 'wrench' : 'file')}</span>
    <div class="library-log-body"><div class="library-log-meta"><span class="mono" title="Device local time">${escape(readableLogTime(log.time))}</span><span title="${escape(readableMachine(log.machine, machineName))}">${escape(readableMachine(log.machine, machineName))}</span></div><h3 title="${escape(log.title)}">${escape(log.title)}</h3><p title="${escape(log.note || 'Saved on this device.')}">${escape(log.note || 'Saved on this device.')}</p><span class="library-log-saved">${icon('check')} Saved locally</span></div>
  </article>`).join('');

  return `<section class="library-screen">
    <div class="library-heading"><div><div class="eyebrow">YOUR FIELD REFERENCE</div><h1>Offline library<span class="library-heading-dot">.</span></h1><p class="muted">Every manual is built in and works without a connection.</p></div><div class="library-heading-actions"><button class="button button-secondary" data-action="add-web">${icon('arrow-up-right')} Add web page</button><button class="button button-secondary" data-action="import-documents">${icon('upload')} Add an update</button></div></div>
    <div class="library-stats">
      <div class="library-stat"><span class="library-stat-icon">${icon('folder')}</span><div><strong class="mono">${documents.length.toString().padStart(2, '0')}</strong><span>Reference files</span></div><span class="library-stat-foot">For the selected machine</span></div>
      <div class="library-stat"><span class="library-stat-icon library-stat-icon--teal">${icon('check')}</span><div><strong class="mono">${builtin.toString().padStart(2, '0')}</strong><span>Built-in manuals</span></div><span class="library-stat-foot">${updates} update${updates === 1 ? '' : 's'} added on this device</span></div>
      <div class="library-stat"><span class="library-stat-icon library-stat-icon--warning">${icon(notices ? 'alert' : 'check')}</span><div><strong class="mono">${notices.toString().padStart(2, '0')}</strong><span>Indexing ${notices === 1 ? 'notice' : 'notices'}</span></div><span class="library-stat-foot">${notices ? 'Some pages need attention' : 'Revision currency not checked'}</span></div>
    </div>
    <div class="library-columns">
      <div class="library-reference-column">
        <section class="panel library-reference-panel" aria-labelledby="library-reference-title">
          <div class="panel-header library-panel-header"><div><h2 id="library-reference-title">Technical documents</h2><p class="muted">${escape(machineName)}</p></div><span class="badge badge-teal">${icon('check')} LOCAL ACCESS</span></div>
          <div class="library-controls"><label class="library-search" for="library-search">${icon('search')}<input id="library-search" type="search" placeholder="Find a manual, schematic, or bulletin…" value="${escape(query)}" autocomplete="off" aria-label="Search technical documents"><span class="library-search-key">/</span></label><div class="library-filters" role="group" aria-label="Filter documents">${filters.map(([value, label]) => `<button class="library-filter ${filter === value ? 'is-active' : ''}" data-action="library-filter" data-filter="${value}" aria-pressed="${filter === value}">${label}${value === 'all' ? `<span>${documents.length}</span>` : ''}</button>`).join('')}</div></div>
          ${notices ? `<div class="library-conflict">${icon('alert')}<div><strong>Some documents need attention</strong><p>Scanned or sparse pages may not be searchable. Older browser imports need indexing. Open a file to inspect its original pages.</p></div></div>` : ''}
          <div class="library-table-head"><span>DOCUMENT NAME / REVISION</span><span>SIZE</span><span>AVAILABILITY</span></div>
          <div class="library-document-list">${documentRows || `<div class="library-empty">${icon('search')}<h3>No manuals here yet</h3><p>Add this machine's PDFs to the built-in library folder, add an update, or choose another filter.</p><button class="button button-secondary" data-action="library-filter" data-filter="all">Show all file types</button></div>`}</div>
          <div class="library-table-footer"><span>${filtered.length} of ${documents.length} files</span><span>${icon('check')} Available without a connection</span></div>
        </section>
        <div class="library-drop-zone" id="drop-zone"><span class="library-drop-symbol">${icon('upload')}</span><div class="library-import-copy"><strong>Got a newer revision or bulletin?</strong><p>Drop the PDF here to add it as an update. It can replace an older manual; the original stays viewable.</p><span>PDFs up to 50 MB · OCR not included · exact page citations.</span></div><div class="library-import-actions"><button class="button button-secondary" data-action="import-documents">${icon('upload')} Add an update</button><button class="button button-secondary" data-action="scan-document">${icon('scan')} OCR status</button></div></div>
      </div>
      <aside class="panel library-history-panel" aria-labelledby="library-history-title"><div class="panel-header library-panel-header"><div><div class="eyebrow">MACHINE RECORD</div><h2 id="library-history-title">Maintenance log</h2></div><span class="library-history-icon">${icon('clock')}</span></div><div class="library-history-machine">${icon('wrench')}<span>${escape(machineName)}</span><span class="library-local-dot"></span></div><div class="library-logs">${recentLogs || `<div class="library-empty library-empty--logs">${icon('wrench')}<h3>A clean maintenance record</h3><p>Add your first repair, test result, or inspection note for this machine.</p></div>`}</div><div class="library-log-actions"><button class="button button-primary" data-action="add-log">${icon('plus')} Add a log entry</button><button class="button button-secondary" data-action="export-logs">${icon('download')} Export maintenance log</button></div><div class="library-sync-note">${icon('check')}<p><strong>Your work is saved locally.</strong><span>Ready for export back at the shop.</span></p></div></aside>
    </div>
  </section>`;
}
