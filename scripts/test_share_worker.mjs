// Unit exercise of the service worker's multipart handoff; not an Android test.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const listeners = {};
const timers = [];
const origin = 'https://localvox.test';
const context = {
  self: {
    location: {origin},
    clients: {claim: async () => {}},
    skipWaiting: async () => {},
    addEventListener: (name, handler) => { listeners[name] = handler; },
  },
  URL, File, Response, setTimeout: handler => timers.push(handler),
};
vm.runInNewContext(readFileSync('localvox/static/sw.js', 'utf8'), context);
const form = new FormData();
form.append('files', new File(['first'], 'first.ogg', {type:'application/ogg'}));
form.append('files', new File(['second'], 'second.opus', {type:'application/octet-stream'}));
const request = new Request(origin + '/share', {method:'POST', body:form});
let responsePromise;
listeners.fetch({request, respondWith: value => { responsePromise = value; }});
const response = await responsePromise;
assert.equal(response.status, 303);
assert.equal(response.headers.get('location'), origin + '/#shared');
let delivered;
const source = {url:origin + '/', postMessage: value => { delivered = value; }};
listeners.message({data:{type:'GET_SHARED'}, source});
assert.equal(delivered.type, 'SHARED_FILES');
assert.deepEqual(Array.from(delivered.files, f => f.name), ['first.ogg', 'second.opus']);
assert.equal(await delivered.files[0].text(), 'first');
assert.equal(delivered.files[0].type, 'application/ogg');
assert.equal(delivered.files[1].type, 'application/octet-stream');
listeners.message({data:{type:'GET_SHARED'}, source});
assert.equal(delivered.files.length, 0);
assert.equal(timers.length, 1);
console.log('Share worker multipart redirect, two-file handoff, and one-time consumption passed.');
