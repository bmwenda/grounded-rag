(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { token: sessionStorage.getItem("simple-rag-token") || "", chatId: null,
    chats: [], nextChatCursor: null, filter: "active", busy: false, requestId: 0,
    listRequestId: 0, listLoading: false, listError: null, listAppend: false,
    renamingChatId: null, renameDraft: "" };

  function showNotice(message, action) {
    $("notice-text").textContent = message;
    $("notice").classList.remove("hidden");
    $("notice-action").classList.toggle("hidden", !action);
    $("notice-action").onclick = action || null;
  }
  function hideNotice() { $("notice").classList.add("hidden"); }
  function setBusy(busy) {
    state.busy = busy;
    $("send-button").disabled = busy;
    $("question").disabled = busy;
    $("new-chat").disabled = busy;
  }
  function closeSidebar() {
    $("sidebar").classList.remove("open");
    $("menu-toggle").setAttribute("aria-expanded", "false");
  }
  function disconnect(message) {
    sessionStorage.removeItem("simple-rag-token");
    sessionStorage.removeItem("simple-rag-chat-id");
    state.token = "";
    state.chatId = null;
    state.chats = [];
    state.nextChatCursor = null;
    state.requestId++;
    state.listRequestId++;
    state.listLoading = false;
    state.listError = null;
    state.renamingChatId = null;
    $("chat-list").replaceChildren();
    $("profile-name").textContent = "Your workspace";
    $("app-shell").classList.add("logged-out");
    $("chat-heading").textContent = "Log in";
    $("auth-view").classList.remove("hidden");
    $("chat-view").classList.add("hidden");
    $("auth-error").textContent = message || "";
    $("auth-error").classList.toggle("hidden", !message);
    $("token").value = "";
    $("token").focus();
    closeSidebar();
  }
  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(`/v1${path}`, {
        ...options,
        headers: { Authorization: `Bearer ${state.token}`, ...(options.body ? { "Content-Type": "application/json" } : {}) },
      });
    } catch (_) { throw new Error("Could not reach the service. Check your connection."); }
    if (response.status === 401) {
      disconnect("Your token was rejected. Enter a valid token to continue.");
      throw new Error("Authentication required");
    }
    if (!response.ok) {
      let code = "";
      try { code = (await response.json()).error?.code || ""; } catch (_) { /* no JSON body */ }
      if (response.status === 409 && code === "chat_archived") throw new Error("This chat is archived. Reactivate it to keep asking questions.");
      if (response.status === 409 && code === "chat_busy") throw new Error("This chat is still answering another question. Reload the conversation shortly.");
      if (response.status === 400) throw new Error("The request was not accepted. Check your question and try again.");
      throw new Error("The service could not complete the request. Reload to check what was saved.");
    }
    return response.status === 204 ? null : response.json();
  }
  function welcome() {
    const box = document.createElement("div");
    box.className = "welcome";
    const mark = document.createElement("div"); mark.className = "welcome-mark"; mark.textContent = "▦";
    const title = document.createElement("h1"); title.textContent = "Find answers across your organisation";
    const hint = document.createElement("p"); hint.textContent = "Ask a question to search your organisation's knowledge base. Answers include source references.";
    box.append(mark, title, hint);
    $("message-list").replaceChildren(box);
  }
  function renderChats() {
    const list = $("chat-list"); list.replaceChildren();
    if (!state.chats.length && !state.listLoading && !state.listError) {
      const empty = document.createElement("p"); empty.className = "sidebar-empty";
      empty.textContent = state.filter === "active" ? "No chats yet. Start with a question." : "No archived chats.";
      list.append(empty);
    }
    for (const chat of state.chats) {
      const entry = document.createElement("div"); entry.className = "chat-entry";
      if (state.renamingChatId === chat.id) {
        const form = document.createElement("form"); form.className = "rename-form";
        const input = document.createElement("input");
        input.id = "rename-chat-title"; input.type = "text"; input.maxLength = 120;
        input.value = state.renameDraft; input.setAttribute("aria-label", "Chat name");
        input.addEventListener("input", () => { state.renameDraft = input.value; });
        input.addEventListener("keydown", event => {
          if (event.key === "Escape") { event.stopPropagation(); cancelRename(); }
        });
        const save = document.createElement("button"); save.type = "submit";
        save.textContent = "Save";
        const cancel = document.createElement("button"); cancel.type = "button";
        cancel.textContent = "Cancel"; cancel.addEventListener("click", cancelRename);
        form.addEventListener("submit", async event => {
          event.preventDefault();
          const title = state.renameDraft.trim();
          if (!title) { showNotice("Enter a chat name."); input.focus(); return; }
          if (title === chat.title) { cancelRename(); return; }
          input.disabled = true; save.disabled = true;
          try {
            const updated = await api(`/chats/${chat.id}`, {
              method: "PATCH", body: JSON.stringify({ title }),
            });
            if (!state.token) return;
            state.chats = [updated, ...state.chats.filter(item => item.id !== chat.id)];
            if (state.chatId === chat.id) $("chat-heading").textContent = updated.title;
            state.renamingChatId = null;
            hideNotice(); renderChats();
          } catch (error) {
            if (state.token) showNotice(error.message);
          } finally { input.disabled = false; save.disabled = false; }
        });
        form.append(input, save, cancel); entry.append(form);
        list.append(entry);
        continue;
      }
      const row = document.createElement("div"); row.className = "chat-row";
      const button = document.createElement("button");
      button.type = "button"; button.className = `chat-item${chat.id === state.chatId ? " active" : ""}`;
      button.textContent = chat.title;
      button.title = chat.title;
      button.setAttribute("aria-current", chat.id === state.chatId ? "page" : "false");
      button.addEventListener("click", () => selectChat(chat));
      const actions = document.createElement("details"); actions.className = "chat-actions";
      actions.addEventListener("toggle", () => {
        entry.classList.toggle("menu-open", actions.open);
      });
      const summary = document.createElement("summary");
      summary.textContent = "⋯";
      summary.setAttribute("aria-label", `Manage ${chat.title}`);
      summary.title = `Manage ${chat.title}`;
      const menu = document.createElement("div"); menu.className = "chat-menu";
      const rename = document.createElement("button"); rename.type = "button";
      rename.textContent = "Rename"; rename.addEventListener("click", () => startRename(chat));
      const status = document.createElement("button"); status.type = "button";
      status.textContent = chat.status === "archived" ? "Reactivate" : "Archive";
      status.addEventListener("click", () => changeChatStatus(chat));
      menu.append(rename, status); actions.append(summary, menu);
      row.append(button, actions); entry.append(row); list.append(entry);
    }
    if (state.listLoading) {
      const loading = document.createElement("p"); loading.className = "sidebar-state";
      loading.textContent = state.listAppend ? "Loading more chats…" : "Loading chats…";
      loading.setAttribute("role", "status"); list.append(loading);
    } else if (state.listError) {
      const failure = document.createElement("div"); failure.className = "sidebar-state sidebar-failure";
      failure.setAttribute("role", "alert");
      const message = document.createElement("p"); message.textContent = state.listError;
      const retry = document.createElement("button"); retry.type = "button";
      retry.textContent = "Retry"; retry.addEventListener("click", () => loadChats(state.listAppend));
      failure.append(message, retry); list.append(failure);
    }
    $("more-chats").classList.toggle("hidden", !state.nextChatCursor);
    $("more-chats").disabled = state.listLoading;
  }
  async function loadChats(append = false) {
    if (append && !state.nextChatCursor) return;
    const requestId = ++state.listRequestId;
    const cursor = append ? state.nextChatCursor : null;
    const params = new URLSearchParams({ status: state.filter, limit: "30" });
    if (cursor) params.set("cursor", cursor);
    state.listLoading = true; state.listError = null; state.listAppend = append;
    renderChats();
    try {
      const page = await api(`/chats?${params}`);
      if (requestId !== state.listRequestId) return;
      state.chats = append ? [...state.chats, ...page.items] : page.items;
      state.nextChatCursor = page.next_cursor;
    } catch {
      if (requestId === state.listRequestId && state.token) {
        state.listError = "Could not load chats. Check your connection and retry.";
      }
    } finally {
      if (requestId === state.listRequestId) {
        state.listLoading = false;
        renderChats();
      }
    }
  }
  function startRename(chat) {
    if (state.busy) return;
    state.renamingChatId = chat.id; state.renameDraft = chat.title;
    renderChats(); $("rename-chat-title").focus();
  }
  function cancelRename() {
    state.renamingChatId = null; state.renameDraft = ""; renderChats();
  }
  async function changeChatStatus(chat) {
    if (state.busy) return;
    const status = chat.status === "archived" ? "active" : "archived";
    try {
      const updated = await api(`/chats/${chat.id}`, {
        method: "PATCH", body: JSON.stringify({ status }),
      });
      if (!state.token) return;
      state.chats = state.chats.filter(item => item.id !== chat.id);
      if (state.chatId === chat.id) {
        state.filter = status;
        $("history-filter").textContent = status === "active" ? "Archived" : "Active";
        state.chats = [];
        selectChat(updated);
        await loadChats();
      } else {
        renderChats();
        showNotice(status === "archived"
          ? "Chat archived. Open Archived to find or reactivate it."
          : "Chat reactivated. Open Active to find it.");
      }
    } catch (error) {
      if (state.token) showNotice(error.message);
    }
  }
  function renderMessage(message) {
    const row = document.createElement("article");
    row.className = `message ${message.speaker === "assistant" ? "assistant" : "user"}`;
    const avatar = document.createElement("div"); avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true"); avatar.textContent = message.speaker === "assistant" ? "▦" : "U";
    const body = document.createElement("div");
    const role = document.createElement("div"); role.className = "message-role";
    role.textContent = message.speaker === "assistant" ? "Assistant" : "You";
    const content = document.createElement("div"); content.className = "message-content";
    content.textContent = message.content;
    body.append(role, content);
    if (message.citations?.length) {
      const citations = document.createElement("div"); citations.className = "citations";
      citations.setAttribute("aria-label", "Sources");
      for (const item of message.citations) {
        const details = document.createElement("details"); details.className = "citation";
        const summary = document.createElement("summary");
        summary.textContent = `[${item.citation_number}] ${item.display_name}${item.page_number ? ` · p. ${item.page_number}` : ""}`;
        details.append(summary);
        const reference = document.createElement("p");
        reference.textContent = `Document ${item.document_id} · version ${item.index_version} · chunk ${item.chunk_index}`;
        details.append(reference);
        if (item.excerpt) { const excerpt = document.createElement("p"); excerpt.textContent = item.excerpt; details.append(excerpt); }
        citations.append(details);
      }
      body.append(citations);
    }
    row.append(avatar, body);
    return row;
  }
  async function loadMessages(chatId) {
    const requestId = ++state.requestId;
    $("message-list").replaceChildren();
    const loading = document.createElement("p"); loading.className = "pending"; loading.textContent = "Loading conversation…";
    $("message-list").append(loading);
    try {
      let cursor = null;
      const messages = [];
      do {
        const params = new URLSearchParams({ limit: "100" });
        if (cursor) params.set("cursor", cursor);
        const page = await api(`/chats/${chatId}/messages?${params}`);
        if (requestId !== state.requestId) return;
        messages.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      if (requestId !== state.requestId) return;
      $("message-list").replaceChildren(...messages.map(renderMessage));
      if (!messages.length) welcome();
      $("conversation").scrollTop = $("conversation").scrollHeight;
    } catch (error) {
      if (requestId === state.requestId && state.token) {
        $("message-list").replaceChildren();
        showNotice(error.message, () => loadMessages(chatId));
      }
    }
  }
  function selectChat(chat) {
    if (state.busy) return;
    state.chatId = chat.id;
    sessionStorage.setItem("simple-rag-chat-id", String(chat.id));
    $("chat-heading").textContent = chat.title;
    $("question").disabled = chat.status === "archived";
    $("question").placeholder = chat.status === "archived" ? "Archived chat · reactivate it to ask" : "Ask a follow-up question…";
    $("send-button").disabled = chat.status === "archived";
    hideNotice(); renderChats(); closeSidebar(); loadMessages(chat.id);
  }
  function newChat() {
    if (state.busy) return;
    state.requestId++;
    state.chatId = null;
    sessionStorage.removeItem("simple-rag-chat-id");
    if (state.filter !== "active") {
      state.filter = "active";
      $("history-filter").textContent = "Archived";
      state.chats = [];
      state.nextChatCursor = null;
      loadChats();
    }
    $("chat-heading").textContent = "New chat";
    $("question").disabled = false;
    $("send-button").disabled = false;
    $("question").placeholder = "Ask a question about your documents…";
    hideNotice(); renderChats(); welcome(); closeSidebar(); $("question").focus();
  }
  async function connect(token) {
    state.token = token.trim();
    $("auth-error").classList.add("hidden");
    try {
      const profile = await api("/users/me");
      sessionStorage.setItem("simple-rag-token", state.token);
      $("profile-name").textContent = profile.first_name || profile.email;
      const savedChatId = Number(sessionStorage.getItem("simple-rag-chat-id"));
      $("auth-view").classList.add("hidden");
      $("chat-view").classList.remove("hidden");
      $("app-shell").classList.remove("logged-out");
      $("chat-heading").textContent = "Loading chats";
      $("question").disabled = true;
      $("send-button").disabled = true;
      $("new-chat").disabled = true;
      welcome();
      await loadChats();
      if (!state.token) return;
      $("new-chat").disabled = false;
      if (Number.isSafeInteger(savedChatId) && savedChatId > 0) {
        try {
          const chat = state.chats.find(item => item.id === savedChatId)
            || await api(`/chats/${savedChatId}`);
          if (chat.status === state.filter && !state.chats.some(item => item.id === chat.id)) {
            state.chats.unshift(chat);
          }
          selectChat(chat);
        } catch (error) {
          if (!state.token) return;
          newChat();
          showNotice("The previous chat could not be reopened. Select it from history or start a new chat.");
        }
      } else newChat();
    } catch (error) {
      if (state.token) {
        $("auth-error").textContent = error.message;
        $("auth-error").classList.remove("hidden");
      }
    }
  }
  async function sendQuestion() {
    const content = $("question").value.trim();
    if (!content || state.busy || !state.token) return;
    const chatId = state.chatId;
    setBusy(true); hideNotice();
    const pending = document.createElement("p"); pending.className = "pending";
    pending.textContent = "Waiting for an answer…";
    $("message-list").append(pending);
    $("conversation").scrollTop = $("conversation").scrollHeight;
    try {
      const path = chatId === null ? "/chats" : `/chats/${chatId}/messages`;
      const result = await api(path, { method: "POST", body: JSON.stringify({ content }) });
      pending.remove();
      $("question").value = "";
      if (chatId === null) {
        state.chatId = result.chat.id;
        sessionStorage.setItem("simple-rag-chat-id", String(result.chat.id));
        $("chat-heading").textContent = result.chat.title;
        $("message-list").replaceChildren();
      }
      $("message-list").append(renderMessage(result.user_message), renderMessage(result.assistant_message));
      $("conversation").scrollTop = $("conversation").scrollHeight;
      await loadChats();
    } catch (error) {
      pending.remove();
      if (state.token) {
        showNotice(`${error.message} Your question may have been saved. Check the conversation before sending again.`, async () => {
          hideNotice();
          state.filter = "active";
          $("history-filter").textContent = "Archived";
          await loadChats();
          if (chatId !== null) await loadMessages(chatId);
          else if (state.chats.length) selectChat(state.chats[0]);
        });
      }
    } finally { setBusy(false); }
  }
  $("auth-form").addEventListener("submit", (event) => { event.preventDefault(); connect($("token").value); });
  $("composer-form").addEventListener("submit", (event) => { event.preventDefault(); sendQuestion(); });
  $("question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendQuestion(); }
  });
  $("new-chat").addEventListener("click", newChat);
  $("sign-out").addEventListener("click", () => disconnect());
  $("more-chats").addEventListener("click", () => loadChats(true));
  $("history-filter").addEventListener("click", async () => {
    state.filter = state.filter === "active" ? "archived" : "active";
    $("history-filter").textContent = state.filter === "active" ? "Archived" : "Active";
    state.renamingChatId = null;
    state.chats = []; state.nextChatCursor = null;
    await loadChats();
  });
  $("menu-toggle").addEventListener("click", () => {
    const open = $("sidebar").classList.toggle("open");
    $("menu-toggle").setAttribute("aria-expanded", String(open));
  });
  $("sidebar-close").addEventListener("click", closeSidebar);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
  });
  if (state.token) connect(state.token); else disconnect();
})();
