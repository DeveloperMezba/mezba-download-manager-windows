'use strict';
const $=id=>document.getElementById(id),id=new URLSearchParams(location.search).get('id');
let port=null,sequence=0,pending=new Map(),timer=null,current=null,closed=false;
function human(n){n=Number(n)||0;for(const u of ['B','KiB','MiB','GiB','TiB']){if(n<1024||u==='TiB')return n.toFixed(1)+' '+u;n/=1024;}}
function connect(){
 if(closed)return;
 if(port)port.disconnect();
 port=chrome.runtime.connectNative('io.mezba.mdm');
 const connected=port;
 port.onMessage.addListener(response=>{
  const item=pending.get(response.request_id);if(!item)return;
  pending.delete(response.request_id);clearTimeout(item.timer);
  response.ok?item.resolve(response.result):item.reject(new Error(response.error||'MDM request failed.'));
 });
 port.onDisconnect.addListener(()=>{
  const error=chrome.runtime.lastError;
  if(port!==connected)return;port=null;
  for(const item of pending.values()){clearTimeout(item.timer);item.reject(new Error(error?.message||'MDM disconnected.'));}pending.clear();
  if(!closed){
   if(current?.status!=='complete'){$('state').textContent='Connection interrupted';$('error').textContent='Your download may still be running. Reconnect or open MDM.';}
   $('reconnect').hidden=false;
  }
 });
 $('reconnect').hidden=true;poll();
}
function send(action){
 return new Promise((resolve,reject)=>{
  if(!port)return reject(new Error('MDM is disconnected. Click Reconnect.'));
  const request_id=++sequence;
  const timeout=setTimeout(()=>{pending.delete(request_id);reject(new Error('MDM is not responding. It may be updating.'));},30000);
  pending.set(request_id,{resolve,reject,timer:timeout});port.postMessage({action,id,request_id});
 });
}
function render(task){
 current=task;document.body.dataset.status=task.status;$('title').textContent=task.title;$('error').textContent=task.error||'';
 const states={queued:'Queued',downloading:'Downloading',pausing:'Saving progress…',paused:'Paused',error:'Download needs attention',complete:'Completed'};
 $('state').textContent=states[task.status]||task.status;
 if(task.status==='downloading'&&!task.done)$('state').textContent='Connecting / preparing download…';
 if(task.status==='queued'&&task.start_at>Date.now()/1000)$('state').textContent='Scheduled for '+new Date(task.start_at*1000).toLocaleTimeString();
 const total=Number(task.total)||0,done=Number(task.done)||0,speed=Number(task.speed)||0;
 if(task.status==='downloading'&&total>0&&done>=total)$('state').textContent='Finishing / processing current file…';
 if(task.status==='complete')$('bar').value=1;
 else if(total>0)$('bar').value=Math.min(1,done/total);
 else if(['queued','downloading','pausing'].includes(task.status))$('bar').removeAttribute('value');
 else $('bar').value=0;
 let detail=human(done)+(total?' / '+human(total):'')+(speed?' · '+human(speed)+'/s':'');
 if(speed&&total>done)detail+=' · '+Math.ceil((total-done)/speed)+'s left';
 if(task.quality?.startsWith('playlist:'))detail='Playlist item '+(task.playlist_index||'?')+'/'+(task.playlist_count||'?')+' · '+detail;
 if(task.status==='complete'&&task.quality?.startsWith('playlist:'))detail='Playlist saved. Open the folder to see all downloaded items.';
 $('details').textContent=detail;
 $('pause').textContent=['queued','downloading'].includes(task.status)?'Pause':task.status==='error'?'Retry':'Resume';
 $('pause').disabled=['complete','pausing'].includes(task.status);
 document.title=(task.status==='complete'?'100% · ':total?Math.floor(done/total*100)+'% · ':'')+'MDM · '+task.title;
}
async function poll(){
 clearTimeout(timer);if(closed||!port)return;
 try{render(await send('status'));$('reconnect').hidden=true;}catch(error){if(current?.status!=='complete')$('error').textContent=error.message;}
 if(!closed&&port&&current?.status!=='complete')timer=setTimeout(poll,1200);
}
$('pause').onclick=async()=>{if(!current)return;$('pause').disabled=true;try{render(await send(['queued','downloading'].includes(current.status)?'pause':'resume'));}catch(error){$('error').textContent=error.message;}poll();};
$('folder').onclick=()=>send('folder').catch(e=>{$('error').textContent=e.message;});
$('app').onclick=()=>send('open').catch(e=>{$('error').textContent=e.message;});
$('reconnect').onclick=connect;
addEventListener('unload',()=>{closed=true;clearTimeout(timer);if(port)port.disconnect();});
if(/^[0-9a-f]{12}$/.test(id||''))connect();else{$('state').textContent='Invalid download';$('error').textContent='Open progress from a valid MDM download.';}
