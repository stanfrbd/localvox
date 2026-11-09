'use strict';
const $ = id => document.getElementById(id);
const tasks = [];
let busy = false;
function notice(text) { $('notice').textContent = text; }
function render() {
  $('results').replaceChildren();
  for (const t of tasks) {
    const item = document.createElement('article'); item.className = 'task';
    const title = document.createElement('h3'); title.textContent = t.filename;
    const state = document.createElement('p'); state.textContent = t.status;
    const content = document.createElement('p'); content.className = t.error ? 'error' : 'transcript';
    content.textContent = t.error || t.text || '';
    item.append(title, state, content);
    if (t.text) { const b = document.createElement('button'); b.textContent = 'Copy transcription'; b.className = 'quiet'; b.onclick = () => copy(t.text); item.append(b); }
    $('results').append(item);
  }
  $('start').disabled = busy || !tasks.some(t => t.status === 'waiting');
  $('clear').disabled = busy;
  $('progress').textContent = `${tasks.filter(t => t.status === 'done').length} of ${tasks.length} completed`;
}
function addFiles(files, ready = false) {
  for (const file of files) tasks.push({ file, ready, filename: file.name, status: 'waiting', text: null, error: null, duration_seconds: null });
  render();
  if (ready) processQueue();
}
$('files').onchange = e => { addFiles(e.target.files); e.target.value = ''; };
$('drop').ondragover = e => { e.preventDefault(); $('drop').classList.add('over'); };
$('drop').ondragleave = () => $('drop').classList.remove('over');
$('drop').ondrop = e => { e.preventDefault(); $('drop').classList.remove('over'); addFiles(e.dataTransfer.files); };
async function processQueue() {
  if (busy) return;
  busy = true; render();
  // Re-read the queue after each file so newly shared files join the same runner.
  // Manual selections remain waiting until explicitly started.
  let t;
  while ((t = tasks.find(task => task.status === 'waiting' && task.ready))) {
    t.status = 'processing'; render();
    try {
      const body = new FormData(); body.append('files', t.file);
      const response = await fetch('/api/transcribe', { method: 'POST', body });
      if (response.status === 401) throw new Error('Session expired. Sign in again, then select your files.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Request failed.');
      Object.assign(t, data.results[0]);
    } catch (error) { t.status = 'error'; t.error = error.message || 'Network error. Retry by selecting the file again.'; }
    t.file = null; t.ready = false; render();
  }
  busy = false; render();
}
$('start').onclick = () => {
  for (const task of tasks.filter(t => t.status === 'waiting')) task.ready = true;
  processQueue();
};
$('clear').onclick = () => { tasks.length = 0; render(); notice('Results cleared from this tab.'); };
const resultRows = () => tasks.map(({file, ready, ...row}) => row);
const allText = () => tasks.map(t => `${t.filename}\n${t.text || t.error || t.status}`).join('\n\n');
async function copy(text) {
  try { await navigator.clipboard.writeText(text); notice('Copied.'); }
  catch { notice('Clipboard access requires HTTPS in many browsers. Select the text manually, or download the results.'); }
}
$('copy-all').onclick = () => copy(allText());
function download(content, type, ext) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const a = document.createElement('a'); a.href = url; a.download = `localvox-results.${ext}`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('text').onclick = () => download(allText(), 'text/plain;charset=utf-8', 'txt');
$('json').onclick = () => download(JSON.stringify({results: resultRows()}, null, 2), 'application/json', 'json');
fetch('/api/model').then(r => r.json()).then(m => {
  $('model').textContent = m.backend === 'mock' ? 'Demo mode · simulated backend, no speech recognition' : `${m.name} · ${m.downloaded ? 'download present; verified on load' : 'download required on server'}`;
  $('limits').textContent = `Server batch limit: ${m.max_files} files · ${m.max_file_mb} MB/file · ${m.max_seconds} seconds/file. This interface sends files sequentially.`;
}).catch(() => { $('model').textContent = 'Model status unavailable. Sign in again if your session expired.'; });
if (!window.isSecureContext) $('network').textContent = 'HTTP connection: audio and credentials are unencrypted. Android installation and sharing need HTTPS; the file picker works on a trusted LAN.';
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').then(async () => {
    await navigator.serviceWorker.ready;
    const requestShared = () => navigator.serviceWorker.controller?.postMessage({type:'GET_SHARED'});
    navigator.serviceWorker.addEventListener('message', e => {
      if (e.data?.type === 'SHARED_FILES' && e.data.files?.length) {
        notice('Shared files received. Transcription starts automatically.');
        addFiles(e.data.files, true);
        history.replaceState(null, '', '/');
      }
    });
    navigator.serviceWorker.addEventListener('controllerchange', requestShared);
    requestShared();
  }).catch(() => notice('Android share integration unavailable. Use the file picker.'));
}
render();
