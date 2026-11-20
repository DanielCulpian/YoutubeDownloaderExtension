const HOST = 'com.ytdl.vivaldi';
let port = null;
let state = { connected: false, busy: false, status: 'Conecta el motor local', logs: [] };
const ready = chrome.storage.session.get('state').then(data => {
  if (data.state) state = { ...data.state, connected: false, busy: false, running: false };
});

/** Persist job state so reopening the panel does not lose progress. */
function save() { return chrome.storage.session.set({ state }); }
/** Append a bounded plain-text entry to the interface log. */
function log(text) { state.logs = [...state.logs, text].slice(-35); }

/** Connect to the native host and coordinate its lifecycle events. */
function connect() {
  if (port) return;
  port = chrome.runtime.connectNative(HOST);
  port.onMessage.addListener(message => {
    switch (message.tipo) {
      case 'conectado':
        state.connected = true;
        state.defaultDestination = message.destino;
        // Migrate only the former default directory; preserve personal folder choices.
        chrome.storage.local.get('destination').then(saved => {
          if (!saved.destination || (message.legacyDestination &&
              saved.destination.replaceAll('\\','/').toLowerCase() === message.legacyDestination.replaceAll('\\','/').toLowerCase())) {
            return chrome.storage.local.set({destination:message.destino});
          }
        });
        if (!state.busy) state.status = 'Motor local conectado';
        break;
      case 'iniciado':
        state.busy = true; state.running = true; state.status = 'Preparando descarga…';
        state.downloadSucceeded = false;
        state.progress = null; state.title = ''; state.detail = '';
        log('Nueva descarga → ' + message.destino); break;
      case 'progreso': {
        state.title = message.titulo || '';
        state.progress = message.bytes ? Math.min(100, message.descargado / message.bytes * 100) : null;
        state.status = message.estado === 'downloading' ? 'Descargando…' : 'Procesando…';
        const speed = ((message.velocidad || 0) / 1048576).toFixed(1);
        state.detail = `${message.indice ? 'Vídeo ' + message.indice + '/' + (message.total || '?') + ' · ' : ''}${speed} MB/s${message.eta != null ? ' · ' + Math.ceil(message.eta) + ' s restantes' : ''}`;
        break;
      }
      case 'procesando': state.status = 'Uniendo / convirtiendo…'; state.progress = null; break;
      // Individual playlist files update the log, never the completion glow.
      case 'archivo': case 'mensaje': log(message.texto || ''); break;
      case 'error':
        state.status = 'Error'; log(message.texto);
        if (typeof message.busy === 'boolean') { state.busy = message.busy; state.running = message.busy; }
        break;
      case 'fin':
        state.downloadSucceeded = !!message.correcto;
        state.status = message.correcto ? 'Descarga completada' : 'Completada con errores'; break;
      case 'terminado':
        // This terminal event covers the entire request, including a complete playlist.
        state.busy = false; state.running = false;
        if (message.cancelado) state.status = 'Descarga cancelada';
        else if (message.codigo) state.status = 'Descarga incompleta · consulta el registro';
        state.progress = message.codigo || message.cancelado ? 0 : 100;
        if (message.codigo === 0 && !message.cancelado && state.downloadSucceeded) {
          chrome.storage.local.set({completionNotice:{id:crypto.randomUUID(),tabId:state.downloadTabId}});
        }
        break;
      case 'carpeta':
        if (message.ruta) chrome.storage.local.set({ destination: message.ruta });
        break;
    }
    save();
  });
  port.onDisconnect.addListener(() => {
    const error = chrome.runtime.lastError?.message;
    port = null;
    state.connected = false; state.busy = false; state.running = false;
    state.status = 'Motor local desconectado';
    if (error) log(error + ' · Ejecuta install.bat y vuelve a conectar.');
    save();
  });
  port.postMessage({ accion: 'ping' });
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  (async () => {
    await ready;
    if (message.action === 'player-context') {
      const url = new URL(sender.tab?.url || 'about:blank');
      if (!sender.tab?.id || !(url.hostname === 'youtube.com' || url.hostname.endsWith('.youtube.com'))) throw new Error('Esta opción solo está disponible en YouTube.');
      return {tabId:sender.tab.id,url:url.href};
    }
    if (message.action === 'ack-completion') {
      const tabId = sender.tab?.id ?? message.sourceTabId;
      const saved = await chrome.storage.local.get('completionNotice');
      if (saved.completionNotice && saved.completionNotice.tabId === tabId) {
        await chrome.storage.local.set({completionNotice:null});
      }
      return state;
    }
    if (message.action === 'state') return state;
    if (message.action === 'connect') { connect(); return state; }
    if (!port || !state.connected) throw new Error('Conecta primero el motor local.');
    if (message.action === 'download') {
      if (state.busy) throw new Error('Ya hay una descarga en curso.');
      state.busy = true; state.running = false; state.logs = []; state.status = 'Validando…';
      state.downloadTabId = sender.tab?.id ?? message.sourceTabId ?? null;
      state.downloadSucceeded = false;
      await chrome.storage.local.set({completionNotice:null});
      await save();
      port.postMessage({ accion: 'descargar', datos: message.data });
    } else if (message.action === 'cancel') {
      state.status = 'Cancelando…'; port.postMessage({ accion: 'cancelar' });
    } else if (message.action === 'folder') {
      port.postMessage({ accion: 'carpeta', requestId: crypto.randomUUID() });
    } else if (message.action === 'open') {
      port.postMessage({ accion: 'abrir', destino: message.destination });
    } else throw new Error('Acción no válida.');
    await save();
    return state;
  })().then(value => respond(message.action === 'player-context' ? {ok:true,context:value} : { ok: true, state: value }), error => respond({ ok: false, error: error.message }));
  return true;
});
