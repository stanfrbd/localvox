// Exercise app.js through UI events and service-worker messages without a model.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
class Element {
  textContent = ''; children = []; classList = {add() {}, remove() {}};
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
}
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, new Element());
  return elements.get(id);
};
const listeners = {};
const requests = [];
let inFlight = 0, maxInFlight = 0;
const context = {
  document: {getElementById:element, createElement:() => new Element()},
  window: {isSecureContext:true}, history:{replaceState() {}},
  navigator: {serviceWorker:{
    register:async () => {}, ready:Promise.resolve(),
    controller:{postMessage() {}}, addEventListener:(name, fn) => { listeners[name] = fn; },
  }},
  FormData, URL, Blob, setTimeout,
  fetch: (url, options) => {
    if (url === '/api/model') return Promise.resolve({json:async () => ({backend:'mock'})});
    assert.equal(url, '/api/transcribe');
    inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
    return new Promise(resolve => requests.push({
      name:options.body.get('files').name,
      finish(error = null) {
        inFlight--;
        resolve({ok:true, status:200, json:async () => ({results:[{
          filename:this.name, status:error ? 'error' : 'done',
          text:error ? null : 'Synthetic result', error, duration_seconds:.1,
        }]})});
      },
    }));
  },
};
vm.runInNewContext(readFileSync('localvox/static/app.js', 'utf8'), context);
const flush = () => new Promise(setImmediate);
await flush();
const file = name => new File(['synthetic'], name, {type:'audio/ogg'});
const states = () => element('results').children.map(row => [row.children[0].textContent, row.children[1].textContent]);
const share = files => listeners.message({data:{type:'SHARED_FILES', files}});
// Picker and drag/drop both require an explicit start.
element('files').onchange({target:{files:[file('manual.ogg')], value:''}});
element('drop').ondrop({preventDefault() {}, dataTransfer:{files:[file('dropped.ogg')]}});
assert.equal(requests.length, 0);
share([file('shared-1.ogg'), file('shared-2.ogg')]);
assert.deepEqual(requests.map(r => r.name), ['shared-1.ogg']);
// A subsequent share joins the active queue; manual additions still wait.
share([file('shared-3.ogg')]);
element('files').onchange({target:{files:[file('manual-later.ogg')], value:''}});
share([]);
assert.equal(requests.length, 1);
requests[0].finish('Synthetic per-file failure'); await flush();
assert.equal(requests[1].name, 'shared-2.ogg');
requests[1].finish(); await flush();
assert.equal(requests[2].name, 'shared-3.ogg');
requests[2].finish(); await flush();
assert.deepEqual(states(), [
  ['manual.ogg','waiting'], ['dropped.ogg','waiting'], ['shared-1.ogg','error'],
  ['shared-2.ogg','done'], ['shared-3.ogg','done'], ['manual-later.ogg','waiting'],
]);
assert.equal(element('start').disabled, false);
element('start').onclick();
for (const [index, name] of [[3,'manual.ogg'],[4,'dropped.ogg'],[5,'manual-later.ogg']]) {
  assert.equal(requests[index].name, name);
  requests[index].finish(); await flush();
}
assert.equal(requests.length, 6);
assert.equal(maxInFlight, 1);
assert.equal(element('start').disabled, true);
console.log('Shared files auto-start, manual picker/drop wait, shares join active queue, error isolation, and serial requests passed.');
