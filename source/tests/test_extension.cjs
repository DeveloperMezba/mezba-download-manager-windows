'use strict';
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
let handler, sent, disconnected = false, headerHandler, created, failWindow=false;
function event() { return {addListener(fn) { this.fn = fn; }}; }
const chrome = {
  runtime: {id: 'fixture', lastError: null, onInstalled:event(),getURL: name=>'chrome-extension://fixture/'+name,
    onMessage:{addListener(fn) {handler=fn;}},
    connectNative(name) {
      assert.equal(name,'io.mezba.mdm');
      const port={onMessage:event(),onDisconnect:event(),disconnect(){disconnected=true;},
        postMessage(message){sent=message;setImmediate(()=>port.onMessage.fn({ok:true,result:{version:'0.3.0',id:'abcdef123456'}}));}};
      return port;
    }},
  webRequest:{onHeadersReceived:{addListener(fn){headerHandler=fn;}}},
  tabs:{onRemoved:event(),onUpdated:event()},
  contextMenus:{onClicked:event(),removeAll(fn){fn();},create(){}},
  windows:{create(options,callback){created=options;if(failWindow)throw new Error('Popup unavailable');callback({id:9});}}
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension/chromium/background.js'),'utf8'),
                   {chrome,Map,URL,Promise,Error,setTimeout,clearTimeout});
const call = msg => new Promise(resolve => { assert.equal(handler(msg,{id:'fixture',tab:{id:5}},resolve),true); });
(async()=>{
  let result=await call({action:'ping'});assert.equal(result.ok,true);assert.equal(sent.action,'ping');assert.equal(disconnected,true);
  result=await call({action:'settings'});assert.equal(result.ok,false);
  result=await call({action:'add',url:'file:///etc/passwd'});assert.equal(result.ok,false);
  result=await call({action:'analyze',url:'https://example.com/video'});assert.equal(result.ok,true);
  assert.equal(handler({action:'ping'},{id:'different'},()=>{}),false);
  headerHandler({tabId:5,url:'https://media.example/stream.m3u8',responseHeaders:[{name:'Content-Type',value:'application/vnd.apple.mpegurl'}]});
  result=await call({action:'candidates'});assert.equal(result.result.length,1);assert.equal(result.result[0].type,'Stream manifest');
  chrome.tabs.onRemoved.fn(5);result=await call({action:'candidates'});assert.equal(result.result.length,0);
  result=await call({action:'add',url:'https://example.com/video'});assert.equal(result.ok,true);assert.equal(result.result.progressWindowOpened,true);
  assert.equal(created.url,'chrome-extension://fixture/progress.html?id=abcdef123456');assert.equal(created.type,'popup');
  failWindow=true;result=await call({action:'add',url:'https://example.com/video'});assert.equal(result.ok,true);assert.equal(result.result.progressWindowOpened,false);
  console.log('9 extension background checks passed, including progress opening and fallback without duplicate downloads.');
})().catch(error=>{console.error(error);process.exitCode=1;});
