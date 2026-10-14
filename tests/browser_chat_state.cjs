// Exercise the browser script with a small DOM and API stub.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  const classes = new Set();
  return {
    children: [], value: '', textContent: '', disabled: false, scrollHeight: 0,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      toggle: (name, force) => {
        const on = force === undefined ? !classes.has(name) : force;
        if (on) classes.add(name); else classes.delete(name);
        return on;
      },
    },
    addEventListener(name, callback) { this[`on_${name}`] = callback; },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    remove() {}, setAttribute() {}, focus() {},
  };
}

async function run(savedChatId, startNewChat = false) {
  const nodes = new Map();
  const entries = new Map([['simple-rag-token', 'test-token']]);
  if (savedChatId !== null) entries.set('simple-rag-chat-id', String(savedChatId));
  const requests = [];
  const chat = { id: 2, title: 'Parent chat', status: 'active' };
  const context = {
    URLSearchParams,
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, element());
        return nodes.get(id);
      },
      createElement: element,
      addEventListener() {},
    },
    sessionStorage: {
      getItem: (key) => entries.get(key) ?? null,
      setItem: (key, value) => entries.set(key, value),
      removeItem: (key) => entries.delete(key),
    },
    async fetch(url, options = {}) {
      requests.push(`${options.method || 'GET'} ${url}`);
      let data;
      if (url === '/v1/users/me') data = { email: 'owner@example.com' };
      else if (url.startsWith('/v1/chats?')) data = { items: [chat], next_cursor: null };
      else if (url === '/v1/chats/2/messages?limit=100') data = { items: [], next_cursor: null };
      else if (url === '/v1/chats/2/messages' && options.method === 'POST') {
        data = {
          user_message: { id: 3, speaker: 'user', content: 'Follow-up', citations: [] },
          assistant_message: { id: 4, speaker: 'assistant', content: 'Answer', citations: [] },
        };
      } else if (url === '/v1/chats' && options.method === 'POST') {
        data = {
          chat,
          user_message: { id: 3, speaker: 'user', content: 'First question', citations: [] },
          assistant_message: { id: 4, speaker: 'assistant', content: 'Answer', citations: [] },
        };
      } else throw new Error(`Unexpected request: ${url}`);
      return { ok: true, status: options.method === 'POST' ? 201 : 200, json: async () => data };
    },
  };
  const script = fs.readFileSync(path.join(__dirname, '../src/api/static/chat.js'), 'utf8');
  vm.runInNewContext(script, context);
  for (let i = 0; i < 10; i++) await new Promise(setImmediate);
  if (startNewChat) nodes.get('new-chat').on_click();
  nodes.get('question').value = 'Follow-up';
  nodes.get('composer-form').on_submit({ preventDefault() {} });
  for (let i = 0; i < 10; i++) await new Promise(setImmediate);
  return { requests, entries };
}

(async () => {
  const restored = await run(2);
  assert(restored.requests.includes('POST /v1/chats/2/messages'));
  assert(!restored.requests.includes('POST /v1/chats'));
  assert.equal(restored.entries.get('simple-rag-chat-id'), '2');

  const fresh = await run(null);
  assert(fresh.requests.includes('POST /v1/chats'));
  assert.equal(fresh.entries.get('simple-rag-chat-id'), '2');

  const reset = await run(2, true);
  assert(reset.requests.includes('POST /v1/chats'));
  assert(!reset.requests.includes('POST /v1/chats/2/messages'));
})().catch((error) => { console.error(error); process.exitCode = 1; });
