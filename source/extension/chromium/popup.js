'use strict';
const $ = id => document.getElementById(id);
const menuStyle = document.createElement('style'); menuStyle.textContent = MDMMenu.css; document.head.append(menuStyle);
const picker = new MDMMenu.Picker(choice => { $('download').textContent = choice?.id.startsWith('playlist:') ? 'Download full playlist' : 'Download this item'; });
$('quality').append(picker.root);
let inspectedURL = '', generation = 0;
function send(message) {
  return new Promise((resolve,reject)=>chrome.runtime.sendMessage(message,response=>{
    if(chrome.runtime.lastError)reject(new Error(chrome.runtime.lastError.message));
    else if(!response?.ok)reject(new Error(response?.error || 'MDM is not responding.'));
    else resolve(response.result);
  }));
}
async function act(id,fn){$(id).disabled=true;try{await fn();}catch(error){$('status').textContent=error.message;}finally{$(id).disabled=false;}}
function invalidate(){generation++;$('formats').hidden=true;picker.setChoices([]);}
$('inspect').onclick=()=>act('inspect',async()=>{
  const current=++generation,url=$('url').value.trim();
  $('status').textContent='Finding video, audio and playlist options…';$('formats').hidden=true;picker.setChoices([]);
  const result=await send({action:'analyze',url});
  if(current!==generation || $('url').value.trim()!==url)return;
  inspectedURL=url;picker.setChoices(result.choices);$('formats').hidden=false;
  let text=result.title;
  if(result.playlist)text+='\nPlaylist available'+(result.playlist.count?' · '+result.playlist.count+' items':'')+'. Choose this item or the full playlist.';
  if(result.warning)text+='\n'+result.warning;
  $('status').textContent=text;
});
$('url').oninput=invalidate;
$('sources').onchange=()=>{if($('sources').value){$('url').value=$('sources').value;invalidate();}};
$('download').onclick=()=>act('download',async()=>{
  const choice=picker.selected;if(!choice)throw new Error('Inspect the video first.');
  $('status').textContent='Adding download and opening progress…';
  const added=await send({action:'add',kind:'media',url:choice.url || inspectedURL,quality:choice.id,title:choice.title || ''});
  $('status').textContent=added.progressWindowOpened?'Download added. Follow it in the progress window.':'Download added. Open MDM to follow its progress.';
});
$('file').onclick=()=>act('file',async()=>{$('status').textContent='Adding file and opening progress…';const added=await send({action:'add',kind:'file',url:$('url').value.trim()});$('status').textContent=added.progressWindowOpened?'File added. Progress window opened.':'File queued. Open MDM to follow it.';});
$('open').onclick=()=>act('open',()=>send({action:'open'}));
const initial=new URLSearchParams(location.search).get('url');if(initial)$('url').value=initial;
chrome.tabs.query({active:true,currentWindow:true},tabs=>{
  const tab=tabs[0];if(!initial && /^https?:/.test(tab?.url || ''))$('url').value=tab.url;
  if(tab)send({action:'candidates',tabId:tab.id}).then(items=>items.forEach((item,i)=>$('sources').add(new Option(item.type+' '+(i+1),item.url)))).catch(()=>{});
});
send({action:'ping'}).then(()=>{if(!generation)$('status').textContent='MDM connected. Ready to download.';}).catch(error=>{if(!generation)$('status').textContent=error.message+'\nInstall the Linux app first, then reload this extension.';});
