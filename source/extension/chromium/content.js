(() => {
  'use strict';
  const overlays = new Map();
  const style = `:host{all:initial;font-family:system-ui,sans-serif;color:#eaf0fb}*{box-sizing:border-box}button,select{font:600 13px system-ui,sans-serif;border-radius:9px;border:1px solid #34455f;padding:9px 12px;background:#172435;color:#eaf0fb;cursor:pointer}button:hover{background:#2c4356}button:disabled{opacity:.6;cursor:wait}.trigger,.download{background:#70e0c2;color:#0b2821;border-color:#70e0c2}.trigger{display:block;margin-left:auto}.panel{margin-top:6px;width:100%;padding:14px;border:1px solid #34455f;border-radius:13px;background:#101925;box-shadow:0 8px 30px #0007;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin}.panel[hidden]{display:none}select{width:100%;min-width:0;margin:10px 0}p{font:12px/1.5 system-ui,sans-serif;white-space:normal;overflow-wrap:anywhere;margin:0 0 9px}.row{display:flex;gap:8px;flex-wrap:wrap}.note{color:#9cacc1}` + MDMMenu.css;
  function send(message) {
    return new Promise((resolve, reject) => chrome.runtime.sendMessage(message, response => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else if (!response?.ok) reject(new Error(response?.error || 'MDM did not respond.'));
      else resolve(response.result);
    }));
  }
  function pageFor(video) {
    const article = video.closest('article, [role="article"]');
    if (article) {
      const link = [...article.querySelectorAll('a[href]')].find(a => /\/(reel|reels|p|watch|videos)\//.test(a.pathname));
      if (link) return link.href;
    }
    // Retain playlist query parameters on watch pages.
    return location.href;
  }
  function viewport() {
    const v = window.visualViewport;
    return {left:v?.offsetLeft || 0, top:v?.offsetTop || 0, width:v?.width || innerWidth, height:v?.height || innerHeight};
  }
  function place(video, entry) {
    const {host, panel} = entry, v = viewport(), r = video.getBoundingClientRect();
    const width = Math.max(1, Math.min(panel.hidden ? 92 : 340, v.width - 16));
    host.style.width = width + 'px';
    panel.style.maxHeight = Math.max(40, v.height - 66) + 'px';
    host.style.setProperty('--mdm-list-height', Math.max(50, Math.min(240, v.height * .4)) + 'px');
    const height = host.getBoundingClientRect().height;
    const point = MDMMenu.position(r,{width,height},v);
    host.style.left = point.left + 'px';
    host.style.top = point.top + 'px';
  }
  function attach(video) {
    const host = document.createElement('div'); host.setAttribute('data-mdm-overlay', '');
    Object.assign(host.style, {position:'fixed', display:'block', zIndex:'2147483647', pointerEvents:'auto'});
    const shadow = host.attachShadow({mode:'closed'});
    const css = document.createElement('style'); css.textContent = style; shadow.append(css);
    const trigger = document.createElement('button'); trigger.className = 'trigger'; trigger.textContent = '↓ MDM';
    trigger.setAttribute('aria-expanded', 'false'); trigger.title = 'Download video, audio or playlist with MDM';
    const panel = document.createElement('div'); panel.className = 'panel'; panel.hidden = true;
    const text = document.createElement('p'); text.setAttribute('role', 'status');
    const sources = document.createElement('select'); sources.setAttribute('aria-label', 'Video source');
    const row = document.createElement('div'); row.className = 'row';
    const download = document.createElement('button'); download.className = 'download'; download.textContent = 'Download'; download.disabled = true;
    const close = document.createElement('button'); close.textContent = 'Close';
    const note = document.createElement('p'); note.className = 'note';
    const picker = new MDMMenu.Picker(choice => {
      download.textContent = choice?.id.startsWith('playlist:') ? 'Download full playlist' : 'Download this item';
    }, () => { if (host.isConnected) place(video, {host,panel}); });
    row.append(download, close); panel.append(text, sources, picker.root, row, note); shadow.append(trigger, panel);
    document.documentElement.append(host);
    let selectedURL = '', generation = 0, busy = false;
    function hide() { panel.hidden = true; trigger.setAttribute('aria-expanded','false'); picker.open(false); place(video,{host,panel}); }
    async function inspect(url) {
      const current = ++generation;
      selectedURL = url; picker.setChoices([]); download.disabled = true; text.textContent = 'Finding video, audio and playlist options…'; note.textContent = '';
      place(video,{host,panel});
      try {
        const result = await send({action:'analyze',url});
        if (current !== generation || !host.isConnected) return;
        text.textContent = result.title; picker.setChoices(result.choices);
        note.textContent = result.playlist ? ('Playlist available' + (result.playlist.count ? ' · ' + result.playlist.count + ' items' : '') + '. Full-playlist quality is chosen separately for each item.') : 'Choose this item as video or audio.';
        if (result.warning) note.textContent += ' ' + result.warning;
        download.disabled = !picker.selected || busy;
      } catch(error) {
        if(current !== generation) return;
        text.textContent = error.message + ' Try a detected source or the individual video/playlist page.';
      }
      place(video,{host,panel});
    }
    trigger.addEventListener('click', async event => {
      if (!event.isTrusted) return;
      event.preventDefault(); event.stopPropagation();
      if (!panel.hidden) { hide(); return; }
      panel.hidden = false; trigger.setAttribute('aria-expanded','true');
      sources.replaceChildren(new Option('This video / playlist page',pageFor(video)));
      const source = video.currentSrc || video.src;
      if (/^https?:/.test(source)) sources.add(new Option('Direct video source',source));
      inspect(sources.value);
      try {
        const found = await send({action:'candidates'});
        for (const [index,item] of found.entries()) if (![...sources.options].some(o => o.value === item.url)) sources.add(new Option(item.type+' '+(index+1),item.url));
      } catch (_) { /* Inspection displays connection errors. */ }
    });
    sources.addEventListener('change', event => { if(event.isTrusted && !busy) inspect(sources.value); });
    close.addEventListener('click',hide);
    panel.addEventListener('keydown', event => { if (event.key === 'Escape') { hide(); trigger.focus(); } });
    download.addEventListener('click', async event => {
      if (!event.isTrusted || download.disabled || !picker.selected) return;
      const choice = picker.selected;
      busy = true; download.disabled = true; sources.disabled = true;
      text.textContent = 'Adding download and opening progress…';
      try {
        const added = await send({action:'add',kind:'media',url:choice.url || selectedURL,quality:choice.id,title:choice.title || ''});
        text.textContent = added.progressWindowOpened ? 'Download added. Follow it in the progress window.' : 'Download added. The progress window could not open; open MDM to follow it.';
      } catch(error) { text.textContent = error.message; }
      finally { busy = false; sources.disabled = false; download.disabled = !picker.selected; place(video,{host,panel}); }
    });
    overlays.set(video,{host,panel});
  }
  function update() {
    if (document.hidden) return;
    const videos = [...document.querySelectorAll('video')].filter(v => {const r=v.getBoundingClientRect();return r.width>140 && r.height>80 && r.bottom>0 && r.top<innerHeight;}).slice(0,12);
    for(const [video,{host}] of overlays) if(!video.isConnected || !videos.includes(video)){host.remove();overlays.delete(video);}
    for(const video of videos){if(!overlays.has(video))attach(video);place(video,overlays.get(video));}
  }
  setInterval(update,800);
  addEventListener('scroll',update,{passive:true});addEventListener('resize',update,{passive:true});
  window.visualViewport?.addEventListener('resize',update,{passive:true});
  window.visualViewport?.addEventListener('scroll',update,{passive:true});
  update();
})();
