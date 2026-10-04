/* DOM behavior test; native messages are fixtures, not a real browser host. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const root=path.join(__dirname,'../extension/chromium');
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(root,'progress.html'),'utf8'),{runScripts:'outside-only',url:'https://extension.example/progress.html?id=abcdef123456'});
 const w=dom.window,$=id=>w.document.getElementById(id),messages=[],ports=[];
 let task={id:'abcdef123456',title:'Album',quality:'playlist:mp3',status:'queued',done:0,total:null,speed:0,start_at:0,error:''};
 w.chrome={runtime:{lastError:null,connectNative(name){
  assert.equal(name,'io.mezba.mdm');
  const port={onMessage:{addListener(fn){this.fn=fn;}},onDisconnect:{addListener(fn){this.fn=fn;}},
   disconnect(){port.onDisconnect.fn();},postMessage(message){
    messages.push(message);
    if(message.action==='pause')task={...task,status:'paused'};
    if(message.action==='resume')task={...task,status:'downloading'};
    queueMicrotask(()=>port.onMessage.fn({request_id:message.request_id,ok:true,result:{...task}}));
   }};ports.push(port);return port;
 }}};
 w.eval(fs.readFileSync(path.join(root,'progress.js'),'utf8')+'\nwindow.testPoll=poll;');await turn();
 assert.equal($('state').textContent,'Queued');assert.equal($('bar').hasAttribute('value'),false);
 task={...task,status:'downloading',done:50,total:100,speed:10,playlist_index:2,playlist_count:8};
 await w.testPoll();assert.equal($('bar').value,.5);assert.match($('details').textContent,/Playlist item 2\/8/);assert.match($('details').textContent,/5s left/);
 $('pause').click();await turn();assert.equal($('state').textContent,'Paused');assert.equal($('pause').textContent,'Resume');
 $('pause').click();await turn();assert.equal($('state').textContent,'Downloading');
 task={...task,status:'error',error:'Source temporarily unavailable'};await w.testPoll();assert.equal($('pause').textContent,'Retry');assert.match($('error').textContent,/temporarily/);
 $('pause').click();await turn();assert.equal($('state').textContent,'Downloading');
 task={...task,done:100};await w.testPoll();assert.match($('state').textContent,/Finishing/);
 task={...task,status:'complete',error:''};await w.testPoll();assert.equal($('bar').value,1);assert.equal($('pause').disabled,true);assert.match($('details').textContent,/Playlist saved/);
 $('folder').click();$('app').click();await turn();assert.ok(messages.some(m=>m.action==='folder'));assert.ok(messages.some(m=>m.action==='open'));
 ports[0].disconnect();assert.equal($('reconnect').hidden,false);assert.equal($('state').textContent,'Completed');assert.equal($('error').textContent,'');assert.match(w.document.title,/^100%/);
 $('reconnect').click();await turn();assert.equal(ports.length,2);assert.equal($('reconnect').hidden,true);
 const count=messages.length;w.dispatchEvent(new w.Event('unload'));assert.equal(messages.length,count);assert.ok(!messages.some(m=>['shutdown','remove','settings'].includes(m.action)));
 dom.window.close();
 console.log('Progress window: queue, live percentage/ETA, playlist item, pause/resume/retry, processing, completion, folder/app actions, reconnect, and close-without-stopping passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
