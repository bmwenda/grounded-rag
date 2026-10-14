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
    contains(target) {
      return this === target || this.children.some(child => child.contains?.(target));
    },
    remove() {}, setAttribute() {}, focus() {},
  };
}

async function run(savedChatId, startNewChat = false, scenario = {}) {
  const nodes = new Map();
  const entries = new Map();
  if (scenario.token !== false) entries.set('simple-rag-token', 'test-token');
  if (savedChatId !== null) entries.set('simple-rag-chat-id', String(savedChatId));
  const requests = [];
  const payloads = [];
  const documentEvents = new Map();
  let listCalls = 0;
  let chat = { id: 2, title: 'Parent chat', status: 'active' };
  const context = {
    URL,
    URLSearchParams,
    document: {
      getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, element());
        return nodes.get(id);
      },
      createElement() {
        const node = element();
        Object.defineProperty(node, 'id', { set(value) { nodes.set(value, node); } });
        return node;
      },
      addEventListener(name, callback) { documentEvents.set(name, callback); },
    },
    sessionStorage: {
      getItem: (key) => entries.get(key) ?? null,
      setItem: (key, value) => entries.set(key, value),
      removeItem: (key) => entries.delete(key),
    },
    async fetch(url, request = {}) {
      requests.push(`${request.method || 'GET'} ${url}`);
      if (request.body) payloads.push(JSON.parse(request.body));
      let data;
      if (url === '/v1/users/me') data = { email: 'owner@example.com' };
      else if (url.startsWith('/v1/chats?')) {
        listCalls++;
        if (scenario.failListOnce && listCalls === 1) {
          return { ok: false, status: 503, json: async () => ({ error: { code: 'service_unavailable' } }) };
        }
        const params = new URL(url, 'http://localhost').searchParams;
        const status = params.get('status');
        if (scenario.paginate && status === 'active') {
          data = params.get('cursor') === 'page2'
            ? { items: [{ id: 3, title: 'Older chat', status: 'active' }], next_cursor: null }
            : { items: [chat], next_cursor: 'page2' };
        } else data = { items: chat.status === status ? [chat] : [], next_cursor: null };
      }
      else if (url === '/v1/chats/2' && request.method === 'PATCH') {
        chat = { ...chat, ...JSON.parse(request.body) };
        data = chat;
      }
      else if (url === '/v1/chats/9') {
        return { ok: false, status: 404, json: async () => ({ error: { code: 'not_found' } }) };
      }
      else if (url === '/v1/chats/2/messages?limit=100') data = { items: [], next_cursor: null };
      else if (url === '/v1/chats/2/messages' && request.method === 'POST') {
        data = {
          user_message: { id: 3, speaker: 'user', content: 'Follow-up', citations: [] },
          assistant_message: { id: 4, speaker: 'assistant', content: 'Answer', citations: [] },
        };
      } else if (url === '/v1/chats' && request.method === 'POST') {
        data = {
          chat,
          user_message: { id: 3, speaker: 'user', content: 'First question', citations: [] },
          assistant_message: { id: 4, speaker: 'assistant', content: 'Answer', citations: [] },
        };
      } else throw new Error(`Unexpected request: ${url}`);
      return { ok: true, status: request.method === 'POST' ? 201 : 200, json: async () => data };
    },
  };
  const script = fs.readFileSync(path.join(__dirname, '../src/static/chat.js'), 'utf8');
  vm.runInNewContext(script, context);
  for (let i = 0; i < 10; i++) await new Promise(setImmediate);
  if (startNewChat) nodes.get('new-chat').on_click();
  if (scenario.send !== false) {
    nodes.get('question').value = 'Follow-up';
    nodes.get('composer-form').on_submit({ preventDefault() {} });
    for (let i = 0; i < 10; i++) await new Promise(setImmediate);
  }
  return { requests, payloads, entries, nodes, documentEvents };
}

function chatMenu(nodes, index = 0) {
  return nodes.get('chat-list').children[index].children[0].children[1];
}

function chatAction(nodes, index) {
  return chatMenu(nodes).children[1].children[index];
}

(async () => {
  const html = fs.readFileSync(path.join(__dirname, '../src/static/index.html'), 'utf8');
  assert.match(html, /id="active-chats"[^>]*>Chats<\/button>/);
  assert.match(html, /id="history-filter"[^>]*>Archived<\/button>/);

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

  const managed = await run(2, false, { send: false });
  const activeMenu = chatMenu(managed.nodes);
  activeMenu.open = true; activeMenu.on_toggle();
  managed.documentEvents.get('click')({ target: chatAction(managed.nodes, 0) });
  assert.equal(activeMenu.open, true);
  managed.documentEvents.get('click')({ target: managed.nodes.get('question') });
  assert.equal(activeMenu.open, false);

  chatAction(managed.nodes, 0).on_click();
  const nameInput = managed.nodes.get('rename-chat-title');
  nameInput.value = 'Benefits and policies';
  nameInput.on_input();
  const renameForm = managed.nodes.get('chat-list').children[0].children[0];
  await renameForm.on_submit({ preventDefault() {} });
  assert(managed.requests.includes('PATCH /v1/chats/2'));
  assert(managed.payloads.some(payload => payload.title === 'Benefits and policies'));
  assert.equal(managed.nodes.get('chat-heading').textContent, 'Benefits and policies');

  await chatAction(managed.nodes, 1).on_click();
  assert(managed.payloads.some(payload => payload.status === 'archived'));
  assert(managed.nodes.get('history-filter').classList.contains('selected'));
  assert(!managed.nodes.get('active-chats').classList.contains('selected'));
  assert.equal(managed.nodes.get('question').disabled, true);
  assert.equal(chatAction(managed.nodes, 1).textContent, 'Reactivate');
  const archivedMenu = chatMenu(managed.nodes);
  archivedMenu.open = true; archivedMenu.on_toggle();
  managed.documentEvents.get('click')({ target: managed.nodes.get('conversation') });
  assert.equal(archivedMenu.open, false);

  await managed.nodes.get('active-chats').on_click();
  assert(managed.requests.at(-1).includes('status=active'));
  assert(managed.nodes.get('active-chats').classList.contains('selected'));
  assert(!managed.nodes.get('history-filter').classList.contains('selected'));
  assert.equal(managed.nodes.get('chat-list').children[0].textContent,
    'No chats yet. Start with a question.');

  await managed.nodes.get('history-filter').on_click();
  assert(managed.requests.at(-1).includes('status=archived'));
  await chatAction(managed.nodes, 1).on_click();
  assert(managed.payloads.some(payload => payload.status === 'active'));
  assert(managed.nodes.get('active-chats').classList.contains('selected'));
  assert(!managed.nodes.get('history-filter').classList.contains('selected'));
  assert.equal(managed.nodes.get('question').disabled, false);

  const invalidRename = await run(2, false, { send: false });
  chatAction(invalidRename.nodes, 0).on_click();
  const invalidInput = invalidRename.nodes.get('rename-chat-title');
  invalidInput.value = '   ';
  invalidInput.on_input();
  await invalidRename.nodes.get('chat-list').children[0].children[0]
    .on_submit({ preventDefault() {} });
  assert(!invalidRename.requests.includes('PATCH /v1/chats/2'));

  const foreignSelection = await run(9, false, { send: false });
  assert(foreignSelection.requests.includes('GET /v1/chats/9'));
  assert.equal(foreignSelection.nodes.get('chat-heading').textContent, 'New chat');
  assert.equal(foreignSelection.entries.has('simple-rag-chat-id'), false);

  const failedList = await run(null, false, { send: false, failListOnce: true });
  const failure = failedList.nodes.get('chat-list').children[0];
  assert(failure.className.includes('sidebar-failure'));
  await failure.children[1].on_click();
  assert.equal(failedList.nodes.get('chat-list').children[0].className, 'chat-entry');

  const loading = await run(null, false, { send: false });
  const filterChange = loading.nodes.get('history-filter').on_click();
  assert.equal(loading.nodes.get('chat-list').children[0].textContent, 'Loading chats…');
  await filterChange;

  const paginated = await run(null, false, { send: false, paginate: true });
  assert(!paginated.nodes.get('more-chats').classList.contains('hidden'));
  await paginated.nodes.get('more-chats').on_click();
  assert(paginated.requests.some(request => request.includes('cursor=page2')));
  assert.equal(paginated.nodes.get('chat-list').children.length, 2);
  const firstMenu = chatMenu(paginated.nodes);
  const secondMenu = chatMenu(paginated.nodes, 1);
  firstMenu.open = true; firstMenu.on_toggle();
  secondMenu.open = true; secondMenu.on_toggle();
  assert.equal(firstMenu.open, false);
  assert.equal(secondMenu.open, true);
})().catch((error) => { console.error(error); process.exitCode = 1; });
