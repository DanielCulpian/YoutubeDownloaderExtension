/* Inject the player interface without exposing the native bridge to YouTube. */
(() => {
  const buttonId = 'ytdl-player-button';
  const hostId = 'ytdl-player-panel';
  let host = null;
  let frame = null;
  let lastUrl = location.href;
  let pending = false;
  let sizeObserver = null;
  let referenceControl = null;
  let outsidePress = null;
  let ownTabId = null;
  let completionNotice = null;

  const glowStyle = document.createElement('style');
  glowStyle.textContent = `
    #ytdl-player-button[data-ytdl-complete="true"] svg {
      color:#79ffda;animation:ytdl-neon-pulse 1.6s ease-in-out infinite;
    }
    #ytdl-player-button[data-ytdl-complete="true"]::before {
      content:"";position:absolute;left:50%;top:50%;width:72%;height:72%;
      transform:translate(-50%,-50%);border-radius:50%;pointer-events:none;
      background:radial-gradient(circle,rgba(84,255,204,.25),rgba(84,255,204,0) 72%);
      animation:ytdl-neon-halo 1.6s ease-in-out infinite;
    }
    @keyframes ytdl-neon-pulse {
      0%,100% {opacity:.5;filter:drop-shadow(0 0 2px #54ffcc66)}
      50% {opacity:1;filter:drop-shadow(0 0 5px #54ffcccc) drop-shadow(0 0 10px #54ffcc77)}
    }
    @keyframes ytdl-neon-halo {0%,100%{opacity:.15}50%{opacity:.85}}
    @media(prefers-reduced-motion:reduce) {
      #ytdl-player-button[data-ytdl-complete="true"] svg {animation:none;filter:drop-shadow(0 0 5px #54ffccaa)}
      #ytdl-player-button[data-ytdl-complete="true"]::before {animation:none;opacity:.5}
    }
  `;
  document.documentElement.append(glowStyle);

  /** Reflect an unread successful completion on the matching player button. */
  function updateGlow() {
    const button = document.getElementById(buttonId);
    if (!button) return;
    const completed = ownTabId !== null && completionNotice?.tabId === ownTabId;
    button.setAttribute('data-ytdl-complete', String(completed));
    button.title = completed ? 'Descarga completada · abrir YouTube Downloader' : 'Descargar vídeo o fragmento';
    button.setAttribute('aria-label', completed ? 'Descarga completada. Abrir YouTube Downloader' : 'Abrir YouTube Downloader');
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.completionNotice) {
      completionNotice = changes.completionNotice.newValue;
      updateGlow();
    }
  });
  (async () => {
    const context = await chrome.runtime.sendMessage({action:'player-context'});
    if (!context?.ok) return;
    ownTabId = context.context.tabId;
    const saved = await chrome.storage.local.get('completionNotice');
    completionNotice = saved.completionNotice;
    updateGlow();
  })().catch(() => {});

  /** Check the composed event path against the panel and its trigger. */
  function insidePanelOrButton(event) {
    const path = event.composedPath();
    return path.includes(host) || path.includes(document.getElementById(buttonId));
  }

  /** Match the neighboring player control dimensions and watch resize changes. */
  function alignIcon(button, reference) {
    // Follow the neighboring native control in each player size and mode.
    const box = reference?.getBoundingClientRect?.();
    const width = reference?.offsetWidth || box?.width;
    const height = reference?.offsetHeight || box?.height;
    button.style.width = width > 0 ? width + 'px' : '48px';
    button.style.height = height > 0 ? height + 'px' : '100%';
    if (reference && reference !== referenceControl && typeof ResizeObserver !== 'undefined') {
      sizeObserver?.disconnect();
      referenceControl = reference;
      sizeObserver = new ResizeObserver(() => alignIcon(button, reference));
      sizeObserver.observe(reference);
    }
  }

  /** Dismiss the embedded panel without canceling the background download. */
  function close() {
    host?.remove(); host = null; frame = null;
    outsidePress = null;
  }

  /** Open or close the isolated extension panel over the YouTube page. */
  async function toggle(event) {
    event.preventDefault(); event.stopPropagation();
    if (host) { close(); return; }
    try {
      const result = await chrome.runtime.sendMessage({action: 'player-context'});
      if (!result?.ok) throw new Error(result?.error || 'No se pudo abrir el panel.');
      const player = document.querySelector('#movie_player, .html5-video-player');
      if (!player) return;
      host = document.createElement('div'); host.id = hostId;
      host.style.cssText = 'position:fixed;right:20px;bottom:70px;width:min(464px,calc(100vw - 40px));height:min(760px,calc(100vh - 110px));z-index:2147483647;';
      const shadow = host.attachShadow({mode: 'closed'});
      const style = document.createElement('style');
      style.textContent = ':host{color-scheme:dark}iframe{display:block;width:100%;height:100%;border:1px solid #33505b;border-radius:14px;background:#0c1320;box-shadow:0 12px 60px #0009}';
      frame = document.createElement('iframe');
      frame.title = 'YouTube Downloader';
      const query = new URLSearchParams({embedded:'1',tabId:String(result.context.tabId)});
      frame.src = chrome.runtime.getURL('popup.html') + '?' + query;
      shadow.append(style, frame);
      (document.fullscreenElement || document.body || player).append(host);
      chrome.runtime.sendMessage({action:'ack-completion'}).catch(() => {});
      // Keep YouTube keyboard shortcuts from consuming input inside the panel.
      host.addEventListener('keydown', e => e.stopPropagation());
    } catch (error) {
      close();
      const button = document.getElementById(buttonId);
      if (button) button.title = 'Recarga esta página de YouTube después de actualizar la extensión. ' + error.message;
    }
  }

  /** Insert one correctly aligned download button into the current player. */
  function install() {
    pending = false;
    if (location.href !== lastUrl) { close(); lastUrl = location.href; }
    const controls = document.querySelector('#movie_player .ytp-right-controls, .html5-video-player .ytp-right-controls');
    if (!controls) return;
    const settings = controls.querySelector('.ytp-settings-button');
    const existing = controls.querySelector('#' + buttonId);
    if (existing) { alignIcon(existing, settings); updateGlow(); return; }
    const button = document.createElement('button');
    button.id = buttonId; button.className = 'ytp-button'; button.type = 'button';
    button.title = 'Descargar vídeo o fragmento';
    button.setAttribute('aria-label', 'Abrir YouTube Downloader');
    button.style.cssText = 'position:relative;box-sizing:border-box;padding:0;border:0;line-height:0;vertical-align:top;flex:0 0 auto;';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
    svg.style.cssText = 'position:absolute;left:50%;top:50%;width:60%;height:60%;max-width:32px;max-height:32px;display:block;transform:translate(-50%,-50%);pointer-events:none;';
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('fill', 'currentColor');
    path.setAttribute('d', 'M11 3h2v10l4-4 1.4 1.4L12 16.8l-6.4-6.4L7 9l4 4V3zM5 18h14v3H5z');
    svg.append(path); button.append(svg);
    button.addEventListener('click', toggle);
    if (settings) settings.insertAdjacentElement('afterend', button);
    else controls.prepend(button);
    alignIcon(button, settings);
    updateGlow();
  }

  window.addEventListener('message', event => {
    if (frame && event.source === frame.contentWindow &&
        event.origin === 'chrome-extension://' + chrome.runtime.id && event.data?.type === 'YTDL_CLOSE') close();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  document.addEventListener('pointerdown', event => {
    outsidePress = host && event.button === 0 && !insidePanelOrButton(event)
      ? {x:event.clientX,y:event.clientY,id:event.pointerId,moved:false} : null;
  }, true);
  document.addEventListener('pointermove', event => {
    if (outsidePress && event.pointerId === outsidePress.id &&
        Math.hypot(event.clientX - outsidePress.x, event.clientY - outsidePress.y) > 6) outsidePress.moved = true;
  }, {capture:true,passive:true});
  document.addEventListener('pointercancel', () => { outsidePress = null; }, true);
  for (const name of ['scroll','wheel','touchmove']) {
    document.addEventListener(name, () => { if (outsidePress) outsidePress.moved = true; }, {capture:true,passive:true});
  }
  document.addEventListener('click', event => {
    const press = outsidePress;
    outsidePress = null;
    if (host && press && !press.moved && event.button === 0 && !insidePanelOrButton(event) &&
        Math.hypot(event.clientX - press.x, event.clientY - press.y) <= 6) close();
  }, true);
  document.addEventListener('yt-navigate-finish', install);
  document.addEventListener('fullscreenchange', () => {
    if (host) (document.fullscreenElement || document.body).append(host);
  });
  const observer = new MutationObserver(() => {
    if (!pending) { pending = true; requestAnimationFrame(install); }
  });
  observer.observe(document.documentElement, {subtree:true,childList:true});
  install();
})();
