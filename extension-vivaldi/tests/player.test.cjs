const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

/** Build a minimal YouTube player DOM for content-script regression tests. */
function player() {
  const windowEvents={},documentEvents={};
  let observer;
  let storageListener;
  let notice=null;
  class Element {
    /** Initialize a controlled DOM element for the test harness. */
    constructor(tag){this.tagName=tag;this.children=[];this.style={};this.handlers={};this.attributes={};this.contentWindow={};}
    /** Attach test elements in DOM order. */
    append(...elements){for(const el of elements){el.parent=this;this.children.push(el);}}
    /** Insert a test element before its siblings. */
    prepend(el){el.parent=this;this.children.unshift(el);}
    /** Detach this test element from its parent. */
    remove(){if(this.parent)this.parent.children=this.parent.children.filter(el=>el!==this);}
    /** Store an attribute for later assertions. */
    setAttribute(key,value){this.attributes[key]=value;}
    /** Record an event callback in the test element. */
    addEventListener(name,fn){this.handlers[name]=fn;}
    /** Create an isolated test shadow root. */
    attachShadow(){this.shadow=new Element('shadow');return this.shadow;}
    /** Resolve a supported selector in the controlled DOM. */
    querySelector(query){return this.children.find(el=>query.startsWith('#')?el.id===query.slice(1):el.className?.includes('ytp-settings-button'));}
    /** Insert a test element next to the native settings button. */
    insertAdjacentElement(position,el){el.parent=this.parent;this.parent.children.splice(this.parent.children.indexOf(this)+1,0,el);}
  }
  const controls=new Element('controls'), movie=new Element('player'), settings=new Element('button');
  settings.className='ytp-settings-button';controls.append(settings);
  const document={documentElement:new Element('html'),querySelector:query=>query.includes('right-controls')?controls:movie,
    getElementById:id=>controls.children.find(el=>el.id===id),
    createElement:tag=>new Element(tag),createElementNS:(ns,tag)=>{const el=new Element(tag);el.namespaceURI=ns;return el;},
    addEventListener:(name,fn)=>documentEvents[name]=fn};
  const location={href:'https://www.youtube.com/watch?v=one'};
  const chrome={runtime:{id:'unit',getURL:file=>'chrome-extension://unit/'+file,
    sendMessage:async()=>({ok:true,context:{tabId:17,url:location.href}})},
    storage:{local:{get:async()=>({completionNotice:notice})},onChanged:{addListener:fn=>{storageListener=fn;}}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension/player.js'),'utf8'),
    {document,location,chrome,URLSearchParams,URL,window:{addEventListener:(name,fn)=>windowEvents[name]=fn},
      MutationObserver:class {constructor(fn){observer=fn;}observe(){}},requestAnimationFrame:fn=>fn()});
  /** Simulate activating the player's download button. */
  const click=()=>controls.children[1].handlers.click({preventDefault(){},stopPropagation(){}});
  /** Publish a simulated local-storage completion notification. */
  const setNotice=value=>{notice=value;storageListener({completionNotice:{newValue:value}},'local');};
  return {controls,movie,settings,click,windowEvents,documentEvents,location,observer,setNotice};
}

test('insert one download button next to settings without duplication',()=>{
  const app=player();
  assert.equal(app.controls.children.length,2);
  assert.equal(app.controls.children[0],app.settings);
  assert.equal(app.controls.children[1].id,'ytdl-player-button');
  app.observer();app.observer();
  assert.equal(app.controls.children.length,2);
});

test('open an isolated player panel and reject forged close messages',async()=>{
  const app=player();await app.click();
  const host=app.movie.children[0], frame=host.shadow.children[1];
  assert.match(frame.src,/popup.html\?embedded=1&tabId=17/);
  app.windowEvents.message({origin:'https://www.youtube.com',source:frame.contentWindow,data:{type:'YTDL_CLOSE'}});
  assert.equal(app.movie.children.length,1);
  app.windowEvents.message({origin:'chrome-extension://unit',source:frame.contentWindow,data:{type:'YTDL_CLOSE'}});
  assert.equal(app.movie.children.length,0);
});

test('navigation to another video dismisses the previous panel',async()=>{
  const app=player();await app.click();
  app.location.href='https://www.youtube.com/watch?v=two';
  app.documentEvents['yt-navigate-finish']();
  assert.equal(app.movie.children.length,0);
  assert.equal(app.controls.children.length,2);
});

test('an outside click dismisses the panel',async()=>{
  const app=player();await app.click();
  const event={button:0,pointerId:1,clientX:100,clientY:100,composedPath:()=>[]};
  app.documentEvents.pointerdown(event);
  app.documentEvents.click(event);
  assert.equal(app.movie.children.length,0);
});

test('scrolling and dragging keep the panel open',async()=>{
  const app=player();await app.click();
  const event={button:0,pointerId:1,clientX:100,clientY:100,composedPath:()=>[]};
  app.documentEvents.wheel();
  assert.equal(app.movie.children.length,1);
  app.documentEvents.pointerdown(event);
  app.documentEvents.scroll();
  app.documentEvents.click(event);
  assert.equal(app.movie.children.length,1);
  app.documentEvents.pointerdown(event);
  app.documentEvents.pointermove({...event,clientX:130});
  app.documentEvents.click(event);
  assert.equal(app.movie.children.length,1);
});

test('clicks inside the panel or on its button are not outside clicks',async()=>{
  const app=player();await app.click();
  for(const target of [app.movie.children[0],app.controls.children[1]]) {
    const event={button:0,pointerId:1,clientX:100,clientY:100,composedPath:()=>[target]};
    app.documentEvents.pointerdown(event);
    app.documentEvents.click(event);
    assert.equal(app.movie.children.length,1);
  }
});

test('completion glow applies only to the source tab and clears on acknowledgment',async()=>{
  const app=player();await new Promise(resolve=>setImmediate(resolve));
  const button=app.controls.children[1];
  app.setNotice({id:'finished',tabId:18});
  assert.equal(button.attributes['data-ytdl-complete'],'false');
  app.setNotice({id:'finished',tabId:17});
  assert.equal(button.attributes['data-ytdl-complete'],'true');
  assert.match(button.title,/completada/);
  app.observer();
  assert.equal(button.attributes['data-ytdl-complete'],'true');
  app.setNotice(null);
  assert.equal(button.attributes['data-ytdl-complete'],'false');
});
