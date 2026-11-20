/** Resolve a panel control by its stable element ID. */
const $ = id => document.getElementById(id);
let busy = false;
let connected = false;
let defaultDestination = '';
let tabId = null;
const parameters = new URLSearchParams(globalThis.location?.search || '');
const embeddedTab = parameters.get('tabId');
if (parameters.get('embedded') === '1') {
  document.body.classList.add('embedded');
  $('close-panel').hidden = false;
  $('close-panel').addEventListener('click', () => parent.postMessage({type:'YTDL_CLOSE'}, '*'));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') parent.postMessage({type:'YTDL_CLOSE'}, '*');
  });
}

/** Return the YouTube tab associated with the popup or embedded panel. */
async function sourceTab() {
  return embeddedTab ? await chrome.tabs.get(Number(embeddedTab)) : (await chrome.tabs.query({active:true,currentWindow:true}))[0];
}

/** Send a command to the background service and render its latest state. */
async function send(action, data = {}) {
  const response = await chrome.runtime.sendMessage({ action, ...data });
  if (!response?.ok) throw new Error(response?.error || 'No se pudo contactar con la extensión.');
  if (response.state) render(response.state);
  return response.state;
}
/** Display an actionable error without exposing HTML from external data. */
function fail(error) { $('error').textContent = error.message || String(error); }
/** Format playback seconds as a compact human-readable timestamp. */
function formatTime(value) {
  const seconds = Math.max(0, Math.floor(value));
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds / 60) % 60;
  return hours ? `${hours}:${String(minutes).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}` : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2,'0')}`;
}
/** Parse and validate a timestamp before sending a clip request. */
function seconds(value) {
  value = value.trim();
  if (!/^\d+(?::\d{1,2}){0,2}$/.test(value)) throw new Error('Usa HH:MM:SS, MM:SS o segundos enteros.');
  const parts = value.split(':').map(Number);
  if ((parts.length > 1 && parts.at(-1) >= 60) || (parts.length === 3 && parts[1] >= 60)) throw new Error('Los campos de tiempo deben ser menores de 60.');
  const result = parts.reduce((sum,n) => sum*60+n, 0);
  if (!Number.isSafeInteger(result)) throw new Error('Tiempo demasiado grande.');
  return result;
}
/** Enable only the controls compatible with the current request mode. */
function modes() {
  if ($('playlist').checked) $('clip').checked = false;
  $('clip').disabled = busy || $('playlist').checked;
  for (const id of ['start','end','mark-start','mark-end']) $(id).disabled = busy || !$('clip').checked;
}
/** Update controls, progress, and logs from the background job state. */
function render(state) {
  busy = !!state.busy; connected = !!state.connected;
  defaultDestination = state.defaultDestination || defaultDestination;
  $('status').textContent = state.status;
  $('logs').textContent = state.logs?.join('\n') || 'Sin mensajes.';
  $('current').textContent = state.title || '';
  $('detail').textContent = state.detail || '';
  if (state.progress == null && busy) { $('progress').removeAttribute('value'); $('percent').textContent = ''; }
  else { $('progress').value = state.progress || 0; $('percent').textContent = `${Math.round(state.progress || 0)}%`; }
  for (const el of document.querySelectorAll('input, #detect, #folder')) el.disabled = busy;
  $('download').disabled = busy || !connected;
  $('cancel').disabled = !busy;
  $('connect').disabled = connected;
  $('open').disabled = !connected;
  $('folder').disabled = busy || !connected;
  modes();
}
/** Read the URL, title, playback position, and ad state of the source tab. */
async function snapshot() {
  if (tabId == null) throw new Error('No hay ninguna pestaña seleccionada.');
  const results = await chrome.scripting.executeScript({ target: { tabId }, func: () => {
    const videos = [...document.querySelectorAll('video')];
    const video = videos.find(v => v.offsetWidth && v.offsetHeight) || videos[0];
    return { url: location.href, title: document.title.replace(/ - YouTube$/, ''), time: video?.currentTime ?? null,
      ad: !!document.querySelector('.ad-showing') };
  }});
  return results[0].result;
}
/** Detect the active YouTube video and reset stale clip boundaries. */
async function detect() {
  const tab = await sourceTab();
  tabId = tab?.id;
  const url = new URL(tab?.url || 'about:blank');
  if (!['youtube.com','www.youtube.com','m.youtube.com','youtu.be'].includes(url.hostname)) throw new Error('Abre un vídeo o playlist de YouTube, o pega su enlace.');
  const changed = $('url').value !== url.href;
  $('url').value = url.href;
  if (changed) { $('start').value = ''; $('end').value = ''; $('clip').checked = false; }
  $('playlist').checked = url.pathname === '/playlist';
  modes();
  const data = await snapshot();
  $('video-title').textContent = data.title;
  $('error').textContent = '';
  await storeDraft();
}
/** Collect the current form values into a serializable draft. */
function draft() {
  return { url: $('url').value, format: document.querySelector('[name=format]:checked').value,
    playlist: $('playlist').checked, clip: $('clip').checked, start: $('start').value, end: $('end').value };
}
/** Persist form choices and the selected destination across panel sessions. */
async function storeDraft() { await chrome.storage.local.set({ draft: draft(), destination: $('destination').value }); }
/** Extract a video identifier from supported YouTube URL shapes. */
function youtubeVideoId(value) {
  const url = new URL(value);
  return url.hostname === 'youtu.be' ? url.pathname.slice(1) : url.searchParams.get('v') || url.pathname.split('/')[2];
}
/** Capture the current playback position for a matching, ad-free video. */
async function mark(target) {
  const data = await snapshot();
  if (!youtubeVideoId(data.url) || youtubeVideoId(data.url) !== youtubeVideoId($('url').value)) throw new Error('La pestaña actual no coincide con el vídeo del enlace. Pulsa Detectar pestaña.');
  if (data.time == null) throw new Error('No se ha encontrado un reproductor de vídeo.');
  if (data.ad) throw new Error('Espera a que termine el anuncio para marcar un tiempo.');
  $(target).value = formatTime(data.time);
  await storeDraft();
}
/** Bind a button action with consistent asynchronous error reporting. */
function action(id, callback) {
  $(id).addEventListener('click', async () => {
    $('error').textContent = '';
    try { await callback(); } catch (error) { fail(error); }
  });
}
action('detect', detect);
action('mark-start', () => mark('start'));
action('mark-end', () => mark('end'));
action('connect', () => send('connect'));
action('cancel', () => send('cancel'));
action('folder', () => send('folder'));
action('open', () => send('open', { destination: $('destination').value || defaultDestination }));
action('download', async () => {
  const data = draft();
  const url = new URL(data.url.trim());
  if (!['http:','https:'].includes(url.protocol) || !(url.hostname === 'youtu.be' || url.hostname === 'youtube.com' || url.hostname.endsWith('.youtube.com'))) throw new Error('Introduce un enlace válido de YouTube.');
  if (data.clip && seconds(data.end) <= seconds(data.start)) throw new Error('El final debe ser posterior al inicio.');
  await storeDraft();
  await send('download', { data: { url: url.href, formato: data.format, playlist: data.playlist,
    recortar: data.clip, inicio: data.start, fin: data.end, destino: $('destination').value || defaultDestination }, sourceTabId:tabId });
});
for (const input of document.querySelectorAll('input')) input.addEventListener('change', () => { modes(); storeDraft().catch(fail); });
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'session' && changes.state) render(changes.state.newValue);
  if (area === 'local' && changes.destination) $('destination').value = changes.destination.newValue || '';
});
(async () => {
  $('extension-id').textContent = 'ID: ' + chrome.runtime.id;
  const saved = await chrome.storage.local.get(['draft','destination']);
  $('destination').value = saved.destination || '';
  const data = saved.draft;
  if (data) {
    $('url').value = data.url || ''; $('playlist').checked = !!data.playlist; $('clip').checked = !!data.clip;
    $('start').value = data.start || ''; $('end').value = data.end || '';
    document.querySelector(`[name=format][value=${data.format === 'mp3' ? 'mp3' : 'mp4'}]`).checked = true;
  }
  await send('state');
  await send('connect');
  const tab = await sourceTab();
  tabId = tab?.id;
  await send('ack-completion', {sourceTabId:tabId});
  // Detect another video automatically while retaining this video's clip boundaries.
  let sameVideo = false;
  try { sameVideo = youtubeVideoId(data?.url) && youtubeVideoId(data.url) === youtubeVideoId(tab?.url); } catch {}
  if (!busy && (!data?.url || (!sameVideo && tab?.url !== data.url))) {
    try { await detect(); } catch (error) { if (!data?.url) fail(error); }
  }
  modes();
})().catch(fail);
