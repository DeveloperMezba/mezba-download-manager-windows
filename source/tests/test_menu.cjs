/* Dev-only dependency: npm install --prefix /tmp/mdm-test-deps jsdom
   NODE_PATH=/tmp/mdm-test-deps/node_modules node tests/test_menu.cjs
   jsdom tests DOM/keyboard behavior; it does not render browser layout. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const root=path.join(__dirname,'../extension/chromium');
const dom=new JSDOM('<html><head></head><body></body></html>',{runScripts:'outside-only',url:'https://example.org/watch'});
const w=dom.window;
w.eval(fs.readFileSync(path.join(root,'choices.js'),'utf8'));
const style=w.document.createElement('style');style.textContent=w.MDMMenu.css;w.document.head.append(style);
let selected=null,changes=0;
const picker=new w.MDMMenu.Picker(value=>{selected=value;changes++;});w.document.body.append(picker.root);
const items=Array.from({length:80},(_,i)=>({id:i<40?'v:'+i:'playlist:v:'+i,label:'Choice '+i,group:i<40?'This item only':'Full playlist',url:'https://example.org/list'}));
picker.setChoices(items);
assert.equal(picker.selected.id,'v:0');assert.equal(picker.options.length,80);
assert.equal(picker.list.querySelectorAll('.mdm-picker-group').length,2);
assert.equal(w.getComputedStyle(picker.list).overflowY,'auto');
assert.ok(w.getComputedStyle(picker.list).maxHeight.includes('240px'));
picker.toggle.click();assert.equal(picker.list.hidden,false);assert.equal(picker.toggle.getAttribute('aria-expanded'),'true');
picker.open(true,true);assert.equal(w.document.activeElement,picker.options[0]);
picker.options[0].dispatchEvent(new w.KeyboardEvent('keydown',{key:'End',bubbles:true}));assert.equal(w.document.activeElement,picker.options[79]);
picker.options[79].click();assert.equal(selected.id,'playlist:v:79');assert.equal(picker.list.hidden,true);
assert.equal(picker.options[79].getAttribute('aria-selected'),'true');assert.equal(picker.options[0].getAttribute('aria-selected'),'false');
picker.open(true,true);picker.options[79].dispatchEvent(new w.KeyboardEvent('keydown',{key:'Home',bubbles:true}));assert.equal(w.document.activeElement,picker.options[0]);
picker.options[0].dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(picker.list.hidden,true);assert.equal(w.document.activeElement,picker.toggle);
picker.setChoices([{id:'audio',label:'Audio',group:'This item only'}]);assert.equal(picker.options.length,1);assert.equal(picker.selected.id,'audio');
picker.setChoices([]);assert.equal(picker.toggle.disabled,true);assert.equal(picker.selected,null);
for(const view of [{left:0,top:0,width:640,height:360},{left:0,top:0,width:320,height:568},{left:0,top:0,width:1280,height:720},{left:100,top:200,width:300,height:240}]){
  const size={width:Math.min(340,view.width-16),height:Math.min(300,view.height-16)};
  for(const rect of [{right:9999,top:9999},{right:-500,top:-500},{right:160,top:210}]){
    const pos=w.MDMMenu.position(rect,size,view);
    assert.ok(pos.left>=view.left+8 && pos.left+size.width<=view.left+view.width-8);
    assert.ok(pos.top>=view.top+8 && pos.top+size.height<=view.top+view.height-8);
  }
}
console.log('Dropdown: 80 choices, grouping, scroll constraints, keyboard selection, reset, and 12 viewport bounds passed.');
dom.window.close();

(async()=>{
 const html=fs.readFileSync(path.join(root,'popup.html'),'utf8');
 for(const mode of ['best','mp4:best','playlist:mp3','playlist:mp4:v:1080']){
  const popup=new JSDOM(html,{runScripts:'outside-only',url:'https://extension.example/popup.html'}),p=popup.window;
  const added=[];
  p.chrome={runtime:{lastError:null,sendMessage(message,callback){
   let result={};
   if(message.action==='candidates')result=[];
   if(message.action==='analyze')result={title:'Current song',playlist:{title:'Album',count:12},choices:[
    {id:'best',label:'This item only · Video',group:'This item only',url:'https://example.org/current',title:'Current song'},
    {id:'mp4:best',label:'This item only · MP4',group:'This item only',url:'https://example.org/current',title:'Current song'},
    {id:'playlist:mp4:v:1080',label:'Full playlist · MP4 1080p',group:'Full playlist',url:'https://example.org/list',title:'Album'},
    {id:'playlist:mp3',label:'Full playlist · Audio · MP3',group:'Full playlist',url:'https://example.org/list',title:'Album'}]};
   if(message.action==='add')added.push(message);
   callback({ok:true,result});
  }},tabs:{query(options,callback){callback([{id:1,url:'https://example.org/watch?v=current&list=album'}]);}}};
  p.eval(fs.readFileSync(path.join(root,'choices.js'),'utf8'));p.eval(fs.readFileSync(path.join(root,'popup.js'),'utf8'));
  p.document.getElementById('inspect').click();await new Promise(r=>setImmediate(r));
  assert.equal(p.document.getElementById('formats').hidden,false);
  p.document.querySelector('.mdm-picker-toggle').click();
  p.document.querySelector('[data-id="'+mode+'"]').click();
  p.document.getElementById('download').click();await new Promise(r=>setImmediate(r));
  assert.equal(added.length,1);assert.equal(added[0].quality,mode);
  assert.equal(added[0].url,mode.startsWith('playlist:')?'https://example.org/list':'https://example.org/current');
  const url=p.document.getElementById('url');url.value='https://example.org/new';url.dispatchEvent(new p.Event('input'));
  assert.equal(p.document.getElementById('formats').hidden,true);
  p.document.getElementById('download').click();await new Promise(r=>setImmediate(r));assert.equal(added.length,1);
  popup.window.close();
 }
 console.log('Popup: current-item and full-playlist actions use the selected URL/format; edited links invalidate old choices.');
})().catch(error=>{console.error(error);process.exitCode=1;});
