'use strict';
const HOST = 'io.mezba.mdm';
const candidates = new Map();
function native(message) {
  return new Promise((resolve, reject) => {
    const port = chrome.runtime.connectNative(HOST);
    let finished = false;
    const timer = setTimeout(() => finish(new Error('MDM timed out. Check that the app is installed.')), 120000);
    function finish(error, result) {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      port.disconnect();
      error ? reject(error) : resolve(result);
    }
    port.onMessage.addListener(response => response.ok
      ? finish(null, response.result) : finish(new Error(response.error || 'MDM request failed.')));
    port.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError;
      if (!finished) finish(new Error(error?.message || 'MDM disconnected. Open the MDM app, then retry. If it still fails, run the Windows installer again and reload the extension.'));
    });
    port.postMessage(message);
  });
}
function webURL(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password; }
  catch { return false; }
}
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  (async () => {
    if (message.action === 'candidates') return candidates.get(message.tabId || sender.tab?.id) || [];
    if (!['ping', 'analyze', 'add', 'open'].includes(message.action)) throw new Error('Unknown action.');
    if (['analyze', 'add'].includes(message.action) && !webURL(message.url)) throw new Error('Use a public HTTP/HTTPS video page or file URL.');
    const result = await native(message);
    if (message.action === 'add') {
      result.progressWindowOpened = await new Promise(resolve => {
        try { chrome.windows.create({url:chrome.runtime.getURL('progress.html')+'?id='+encodeURIComponent(result.id),
          type:'popup',width:440,height:365}, window => {
          const error=chrome.runtime.lastError;
          resolve(!error && !!window);
        }); } catch { resolve(false); }
      });
    }
    return result;
  })().then(result => sendResponse({ok: true, result}), error => sendResponse({ok: false, error: error.message}));
  return true;
});
chrome.webRequest.onHeadersReceived.addListener(details => {
  if (details.tabId < 0 || !webURL(details.url)) return;
  const type = details.responseHeaders?.find(h => h.name.toLowerCase() === 'content-type')?.value || '';
  const manifest = /mpegurl|dash\+xml/i.test(type) || /\.(m3u8|mpd)(\?|$)/i.test(details.url);
  const media = /^(video|audio)\//i.test(type) && !/\.(ts|m4s)(\?|$)/i.test(details.url);
  if (!manifest && !media) return;
  // In-memory only. No browsing-history database or remote telemetry.
  const existing = candidates.get(details.tabId) || [];
  if (!existing.some(c => c.url === details.url)) {
    existing.push({url: details.url, type: manifest ? 'Stream manifest' : 'Media file'});
    candidates.set(details.tabId, existing.slice(-20));
  }
}, {urls: ['http://*/*', 'https://*/*']}, ['responseHeaders']);
chrome.tabs.onRemoved.addListener(id => candidates.delete(id));
chrome.tabs.onUpdated.addListener((id, change) => { if (change.status === 'loading' || change.url) candidates.delete(id); });
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => chrome.contextMenus.create({id: 'mdm-download', title: 'Download with MDM…', contexts: ['link', 'video', 'audio']}));
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== 'mdm-download') return;
  const url = info.linkUrl || info.srcUrl || tab?.url;
  if (webURL(url)) chrome.windows.create({url: chrome.runtime.getURL('popup.html') + '?url=' + encodeURIComponent(url), type: 'popup', width: 440, height: 610});
});
