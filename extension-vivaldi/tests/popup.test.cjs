const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

// Exercise real handlers without installing or modifying a browser.
/** Run real popup handlers against a controlled DOM and browser API harness. */
async function panel({oldVideo='demo',currentVideo='demo',clip=true}={}) {
  class Element {
    /** Initialize a controlled DOM element for the test harness. */
    constructor(id){this.id=id;this.value='';this.textContent='';this.checked=false;this.disabled=false;this.handlers={};}
    /** Record an event callback in the test element. */
    addEventListener(event,fn){this.handlers[event]=fn;}
    /** Invoke the asynchronous handler for a simulated user interaction. */
    async fire(event='click'){await this.handlers[event]?.();}
    /** Remove an attribute from the test element. */
    removeAttribute(key){delete this[key];}
  }
  const ids=['url','playlist','clip','start','end','mark-start','mark-end','destination','download','cancel',
    'detect','folder','open','connect','status','logs','current','detail','progress','percent','error','video-title','extension-id'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
  const mp4=new Element('mp4'),mp3=new Element('mp3');mp4.value='mp4';mp3.value='mp3';mp4.checked=true;
  const inputs=[...['url','playlist','clip','start','end','destination'].map(id=>elements[id]),mp4,mp3];
  const document={getElementById:id=>elements[id],querySelectorAll:query=>query==='input'?inputs:[...inputs,elements.detect,elements.folder],
    querySelector:query=>query.includes(':checked')?(mp3.checked?mp3:mp4):query.includes('mp3')?mp3:mp4};
  const calls=[];
  const saved={draft:{url:`https://www.youtube.com/watch?v=${oldVideo}`,format:'mp4',clip,start:'1:00',end:'3:00'}};
  const state={connected:true,busy:false,status:'Conectado',progress:0,logs:[]};
  const chrome={runtime:{id:'test',sendMessage:async message=>{calls.push(message);return {ok:true,state};}},
    storage:{local:{get:async()=>saved,set:async data=>Object.assign(saved,data)},onChanged:{addListener:()=>{}}},
    tabs:{query:async()=>[{id:1,url:`https://www.youtube.com/watch?v=${currentVideo}`}]},
    scripting:{executeScript:async()=>[{result:{url:`https://www.youtube.com/watch?v=${currentVideo}`,title:'Video de prueba',time:125.8}}]}};
  const context=vm.createContext({document,chrome,URL,URLSearchParams,console});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/popup.js'),'utf8'),context);
  for(let i=0;i<5;i++) await new Promise(resolve=>setImmediate(resolve));
  return {elements,mp3,mp4,calls,saved,context};
}

test('capture current playback time and preserve clip boundaries across panel sessions',async()=>{
  const app=await panel();
  assert.equal(app.elements.clip.checked,true);
  assert.equal(app.elements.start.value,'1:00');
  await app.elements['mark-start'].fire();
  assert.equal(app.elements.start.value,'2:05');
  assert.equal(app.saved.draft.start,'2:05');
});

test('automatically detect another video and clear stale boundaries',async()=>{
  const app=await panel({currentVideo:'otro'});
  assert.equal(app.elements.url.value,'https://www.youtube.com/watch?v=otro');
  assert.equal(app.elements.start.value,'');
  assert.equal(app.elements.clip.checked,false);
  assert.equal(app.elements['video-title'].textContent,'Video de prueba');
});

test('MP3 playlists disable clipping and submit the expected request',async()=>{
  const app=await panel();
  app.elements.url.value='https://www.youtube.com/playlist?list=PL123';
  app.elements.playlist.checked=true;await app.elements.playlist.fire('change');
  app.mp3.checked=true;app.mp4.checked=false;
  assert.equal(app.elements.start.disabled,true);
  assert.equal(app.elements.clip.checked,false);
  await app.elements.download.fire();
  const request=app.calls.find(call=>call.action==='download');
  assert.equal(request.data.formato,'mp3');
  assert.equal(request.data.playlist,true);
  assert.equal(request.data.recortar,false);
});

test('reject inverted clip boundaries before starting a download',async()=>{
  const app=await panel();
  app.elements.start.value='2:00';app.elements.end.value='1:00';
  await app.elements.download.fire();
  assert.equal(app.calls.some(call=>call.action==='download'),false);
  assert.match(app.elements.error.textContent,/posterior/);
});

test('do not capture playback positions from a different video',async()=>{
  const app=await panel();app.elements.url.value='https://youtu.be/diferente';
  await app.elements['mark-end'].fire();
  assert.match(app.elements.error.textContent,/no coincide/);
  assert.equal(app.elements.end.value,'3:00');
});
