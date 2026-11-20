const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

/** Build an isolated background-service test harness. */
function setup() {
  let listener, nativeListener, disconnected;
  const commands = [];
  const storage = {};
  const port = {
    postMessage: message => commands.push(message),
    onMessage: { addListener: fn => { nativeListener = fn; } },
    onDisconnect: { addListener: fn => { disconnected = fn; } },
  };
  const chrome = {
    storage: {
      session: { get: async () => ({}), set: async value => Object.assign(storage, structuredClone(value)) },
      local: { get: async key => ({[key]:storage[key]}), set: async value => Object.assign(storage, structuredClone(value)) },
    },
    runtime: { id: 'test', connectNative: () => port, onMessage: { addListener: fn => { listener = fn; } } },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../extension/background.js'), 'utf8'),
                     { chrome, URL, crypto: require('node:crypto').webcrypto });
  return {
    commands, storage,
    call: (action, data={}, tab) => new Promise(resolve => listener({action,...data}, {id:'test',tab}, resolve)),
    native: message => nativeListener(message),
    disconnect: () => disconnected(),
  };
}

test('connection and failed validation allow another attempt', async () => {
  const app = setup();
  await app.call('connect');
  assert.equal(app.commands[0].accion, 'ping');
  app.native({tipo:'conectado',destino:'C:/descargas'});
  await app.call('download', {data:{url:'invalid',formato:'mp4'}});
  assert.equal((await app.call('state')).state.busy, true);
  app.native({tipo:'error',texto:'URL no valida',busy:false});
  assert.equal((await app.call('state')).state.busy, false);
  assert.equal((await app.call('download', {data:{url:'test',formato:'mp3'}})).ok, true);
});

test('progress survives panel closure and rejects overlapping requests', async () => {
  const app=setup();
  await app.call('connect'); app.native({tipo:'conectado'});
  await app.call('download', {data:{formato:'mp4'}});
  app.native({tipo:'iniciado',destino:'C:/descargas'});
  app.native({tipo:'progreso',estado:'downloading',titulo:'Video',descargado:50,bytes:100,velocidad:1048576});
  const reopened = await app.call('state');
  assert.equal(reopened.state.progress, 50);
  assert.equal(reopened.state.title, 'Video');
  assert.equal((await app.call('download',{data:{}})).ok,false);
  await app.call('cancel');
  assert.equal(app.commands.at(-1).accion,'cancelar');
  app.native({tipo:'terminado',codigo:1,cancelado:true});
  assert.equal((await app.call('state')).state.busy,false);
  assert.equal(app.storage.state.status,'Descarga cancelada');
});

test('worker errors retain the busy state until process termination', async () => {
  const app=setup(); await app.call('connect'); app.native({tipo:'conectado'});
  await app.call('download',{data:{}});
  app.native({tipo:'iniciado',destino:'C:/descargas'});
  app.native({tipo:'error',texto:'Error de FFmpeg'});
  assert.equal((await app.call('state')).state.busy,true);
  app.native({tipo:'terminado',codigo:1});
  assert.equal((await app.call('state')).state.busy,false);
});

test('host disconnection and folder selection update stored state', async () => {
  const app=setup(); await app.call('connect'); app.native({tipo:'conectado'});
  await app.call('folder'); assert.equal(app.commands.at(-1).accion,'carpeta');
  app.native({tipo:'carpeta',ruta:'C:/musica'});
  assert.equal(app.storage.destination,'C:/musica');
  app.disconnect();
  assert.equal((await app.call('state')).state.connected,false);
  assert.equal((await app.call('download',{data:{}})).ok,false);
});

test('player requests receive context only for their own YouTube tab',async()=>{
  const app=setup();
  const context=await app.call('player-context',{}, {id:17,url:'https://www.youtube.com/watch?v=one'});
  assert.equal(context.context.tabId,17);
  assert.equal((await app.call('player-context',{}, {id:18,url:'https://example.com'})).ok,false);
});

test('migrate the former default destination while preserving personal choices',async()=>{
  const app=setup();app.storage.destination='C:\\proyecto\\downloads';
  await app.call('connect');
  app.native({tipo:'conectado',destino:'D:/Descargas',legacyDestination:'C:/proyecto/downloads'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(app.storage.destination,'D:/Descargas');
  app.storage.destination='D:/Musica';
  app.native({tipo:'conectado',destino:'D:/Descargas',legacyDestination:'C:/proyecto/downloads'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(app.storage.destination,'D:/Musica');
});

test('completion glow requires request success and acknowledgment from its source tab',async()=>{
  const app=setup();await app.call('connect');app.native({tipo:'conectado'});
  await app.call('download',{data:{},sourceTabId:17});
  app.native({tipo:'iniciado'});app.native({tipo:'fin',correcto:true});
  assert.equal(app.storage.completionNotice,null);
  app.native({tipo:'terminado',codigo:0,cancelado:false});
  assert.equal(app.storage.completionNotice.tabId,17);
  await app.call('ack-completion',{sourceTabId:18});
  assert.equal(app.storage.completionNotice.tabId,17);
  await app.call('ack-completion',{}, {id:17});
  assert.equal(app.storage.completionNotice,null);
});

test('new requests clear the glow and canceled or failed requests never activate it',async()=>{
  const app=setup();await app.call('connect');app.native({tipo:'conectado'});
  for(const outcome of [{codigo:1,cancelado:false},{codigo:0,cancelado:true}]) {
    app.storage.completionNotice={id:'anterior',tabId:17};
    await app.call('download',{data:{},sourceTabId:17});
    assert.equal(app.storage.completionNotice,null);
    app.native({tipo:'iniciado'});app.native({tipo:'fin',correcto:true});
    app.native({tipo:'terminado',...outcome});
    assert.equal(app.storage.completionNotice,null);
  }
});

test('playlist file events never activate the glow before the whole request finishes',async()=>{
  const app=setup();await app.call('connect');app.native({tipo:'conectado'});
  await app.call('download',{data:{playlist:true,formato:'mp3'},sourceTabId:17});
  app.native({tipo:'iniciado'});
  for(let index=1;index<=3;index++) {
    app.native({tipo:'progreso',estado:'finished',indice:index,total:3});
    app.native({tipo:'procesando'});
    app.native({tipo:'archivo',texto:`Mi playlist/${index}.mp3`});
    assert.equal(app.storage.completionNotice,null);
    assert.equal((await app.call('state')).state.busy,true);
  }
  app.native({tipo:'fin',correcto:true});
  assert.equal(app.storage.completionNotice,null);
  app.native({tipo:'terminado',codigo:0,cancelado:false});
  assert.equal(app.storage.completionNotice.tabId,17);
  assert.equal((await app.call('state')).state.busy,false);
});
