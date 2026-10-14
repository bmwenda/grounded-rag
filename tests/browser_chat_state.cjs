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
      contains: (name) => classes.has(name),
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

async function run(savedChatId, startNewChat = false, options = {}) {
  const nodes = new Map();
  const entries = new Map();
  if (options.token !== false) entries.set('simple-rag-token', 'test-token');
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
  const script = fs.readFileSync(path.join(__dirname, '../src/static/chat.js'), 'utf8');
  vm.runInNewContext(script, context);
  for (let i = 0; i < 10; i++) await new Promise(setImmediate);
  if (startNewChat) nodes.get('new-chat').on_click();
  if (options.send !== false) {
    nodes.get('question').value = 'Follow-up';
    nodes.get('composer-form').on_submit({ preventDefault() {} });
    for (let i = 0; i < 10; i++) await new Promise(setImmediate);
  }
  return { requests, entries, nodes };
}

(async () => {
  const restored = await run(2);
  assert(restored.requests.includes('POST /v1/chats/2/messages'));
  assert(!restored.requests.includes('POST /v1/chats'));
  assert.equal(restored.entries.get('simple-rag-chat-id'), '2');

  const fresh = await run(null);
  assert(fresh.requests.includes('POST /v1/chats'));
  assert.equal(fresh.entries.get('simple-rag-chat-id'), '2');

  const emptyChat = await run(null, false, { send: false });
  const welcome = emptyChat.nodes.get('message-list').children[0];
  assert.equal(welcome.children[1].textContent, 'Find answers across your organisation');
  assert.match(welcome.children[2].textContent, /organisation's knowledge base/);

  const reset = await run(2, true);
  assert(reset.requests.includes('POST /v1/chats'));
  assert(!reset.requests.includes('POST /v1/chats/2/messages'));

  const loggedOut = await run(null, false, { token: false, send: false });
  assert(loggedOut.nodes.get('app-shell').classList.contains('logged-out'));
  assert(loggedOut.nodes.get('chat-view').classList.contains('hidden'));
  assert(!loggedOut.nodes.get('auth-view').classList.contains('hidden'));
  assert.equal(loggedOut.nodes.get('chat-heading').textContent, 'Log in');
  assert.equal(loggedOut.requests.length, 0);

  const loggedIn = await run(2, false, { send: false });
  assert(!loggedIn.nodes.get('app-shell').classList.contains('logged-out'));
  assert(loggedIn.nodes.get('auth-view').classList.contains('hidden'));
  loggedIn.nodes.get('sign-out').on_click();
  assert(loggedIn.nodes.get('app-shell').classList.contains('logged-out'));
  assert.equal(loggedIn.entries.has('simple-rag-token'), false);
})().catch((error) => { console.error(error); process.exitCode = 1; });
