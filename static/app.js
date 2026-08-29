const STORAGE_KEY = "puls-agent-v1";

const $ = (id) => document.getElementById(id);

const state = {
  conversations: [],
  currentId: null,
  busy: false,
  serverHasKey: false,
  settings: {
    apiKey: "",
    model: "gpt-4o-mini",
    temperature: 0.7,
    systemPrompt: "",
    toolsEnabled: true,
  },
};

function uid() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    state.conversations = data.conversations || [];
    state.currentId = data.currentId || null;
    Object.assign(state.settings, data.settings || {});
  } catch {
    /* ignore broken storage */
  }
}

function save() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      conversations: state.conversations,
      currentId: state.currentId,
      settings: { ...state.settings, apiKey: state.settings.apiKey },
    })
  );
}

function current() {
  return state.conversations.find((c) => c.id === state.currentId) || null;
}

function ensureChat() {
  if (current()) return current();
  const chat = {
    id: uid(),
    title: "Новый разговор",
    messages: [],
    createdAt: Date.now(),
  };
  state.conversations.unshift(chat);
  state.currentId = chat.id;
  save();
  return chat;
}

function renderList() {
  const list = $("convList");
  list.innerHTML = "";
  if (!state.conversations.length) {
    list.innerHTML = `<div class="conv"><small>Пока пусто</small></div>`;
    return;
  }
  for (const c of state.conversations) {
    const btn = document.createElement("button");
    btn.className = "conv" + (c.id === state.currentId ? " active" : "");
    btn.type = "button";
    const when = new Date(c.createdAt).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
    btn.innerHTML = `${escapeHtml(c.title)}<small>${when}</small>`;
    btn.addEventListener("click", () => {
      state.currentId = c.id;
      save();
      render();
      $("rail").classList.remove("open");
    });
    list.appendChild(btn);
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function md(text) {
  const raw = window.marked.parse(text || "", { breaks: true });
  return window.DOMPurify.sanitize(raw);
}

function renderThread() {
  const thread = $("thread");
  const chat = current();
  thread.innerHTML = "";
  if (!chat || !chat.messages.length) {
    thread.innerHTML = `
      <div class="empty">
        <h2>Агент на связи.</h2>
        <p>Пульс ходит в ChatGPT, считает, запоминает факты и читает публичные страницы.</p>
        <div class="chips">
          <button class="chip" type="button" data-q="Посчитай (17^3 - 89) / sqrt(16)">Посчитать выражение</button>
          <button class="chip" type="button" data-q="Запомни: меня зовут пользователь Пульса, я из Курска.">Запомнить обо мне</button>
          <button class="chip" type="button" data-q="Кто ты и какими инструментами пользуешься?">Расскажи о себе</button>
        </div>
      </div>`;
    thread.querySelectorAll("[data-q]").forEach((el) => {
      el.addEventListener("click", () => {
        $("input").value = el.dataset.q;
        $("input").focus();
      });
    });
    $("chatTitle").textContent = "Новый разговор";
    return;
  }
  $("chatTitle").textContent = chat.title;
  for (const msg of chat.messages) {
    thread.appendChild(messageEl(msg));
  }
  thread.scrollTop = thread.scrollHeight;
}

function messageEl(msg) {
  const el = document.createElement("div");
  el.className = `msg ${msg.role}${msg.error ? " error" : ""}`;
  if (msg.role === "assistant") {
    el.innerHTML = `<div class="who">пульс</div><div class="body">${md(msg.content || "")}</div>`;
  } else {
    el.textContent = msg.content;
  }
  return el;
}

function hasKey() {
  return Boolean(state.settings.apiKey || state.serverHasKey);
}

function updateStatus() {
  const line = $("statusLine");
  if (hasKey()) {
    line.textContent = state.settings.apiKey
      ? `${state.settings.model} · ключ в браузере`
      : `${state.settings.model} · ChatGPT подключён`;
    line.className = "ok";
  } else {
    line.textContent = "ChatGPT не подключён — откройте настройки";
    line.className = "bad";
  }
}

function render() {
  $("apiKey").value = state.settings.apiKey;
  $("model").value = state.settings.model;
  $("temperature").value = state.settings.temperature;
  $("tempVal").textContent = state.settings.temperature;
  $("systemPrompt").value = state.settings.systemPrompt;
  $("toolsToggle").checked = state.settings.toolsEnabled;
  updateStatus();
  renderList();
  renderThread();
}

function autosize() {
  const ta = $("input");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 180) + "px";
}

function showSettings(on) {
  $("settingsModal").hidden = !on;
}

async function testKey() {
  const key = $("apiKey").value.trim();
  const msg = $("testMsg");
  msg.className = "test-msg";
  msg.textContent = "Проверяю…";
  try {
    const res = await fetch("/api/ping-key", {
      method: "POST",
      headers: key ? { Authorization: `Bearer ${key}` } : {},
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Ключ не принят");
    msg.className = "test-msg ok";
    msg.textContent = "Ключ рабочий. Модели: " + (data.sample || "ok");
  } catch (err) {
    msg.className = "test-msg bad";
    msg.textContent = err.message || String(err);
  }
}

function saveSettings() {
  state.settings.apiKey = $("apiKey").value.trim();
  state.settings.model = $("model").value;
  state.settings.temperature = Number($("temperature").value);
  state.settings.systemPrompt = $("systemPrompt").value;
  save();
  updateStatus();
  showSettings(false);
}

async function sendMessage(text) {
  const content = (text ?? $("input").value).trim();
  if (!content || state.busy) return;
  if (!hasKey()) {
    showSettings(true);
    $("testMsg").textContent = "Сначала вставьте OpenAI API-ключ.";
    $("testMsg").className = "test-msg bad";
    return;
  }

  const chat = ensureChat();
  chat.messages.push({ role: "user", content });
  if (chat.title === "Новый разговор") {
    chat.title = content.slice(0, 42) + (content.length > 42 ? "…" : "");
  }
  $("input").value = "";
  autosize();
  save();
  render();

  const assistant = { role: "assistant", content: "" };
  chat.messages.push(assistant);
  const thread = $("thread");
  const el = messageEl(assistant);
  el.querySelector(".body").innerHTML = `<span class="cursor"></span>`;
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;

  state.busy = true;
  $("sendBtn").disabled = true;
  $("toolsLog").hidden = true;
  $("toolsLog").textContent = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(state.settings.apiKey ? { Authorization: `Bearer ${state.settings.apiKey}` } : {}),
      },
      body: JSON.stringify({
        messages: chat.messages
          .filter((m) => m.role === "user" || (m.role === "assistant" && m.content && !m.error))
          .slice(0, -1)
          .concat([{ role: "user", content }]),
        model: state.settings.model,
        system_prompt: state.settings.systemPrompt,
        tools_enabled: state.settings.toolsEnabled,
        temperature: state.settings.temperature,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const consume = (raw) => {
      let eventName = "message";
      const dataLines = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) return;
      handleEvent(eventName, dataLines.join("\n"), assistant, el);
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        consume(raw);
      }
    }
    if (buffer.trim()) consume(buffer);

    if (!assistant.content) assistant.content = "Пустой ответ модели.";
    el.querySelector(".body").innerHTML = md(assistant.content);
  } catch (err) {
    assistant.error = true;
    assistant.content = "Ошибка: " + (err.message || err);
    el.classList.add("error");
    el.querySelector(".body").textContent = assistant.content;
  } finally {
    state.busy = false;
    $("sendBtn").disabled = false;
    save();
    renderList();
    thread.scrollTop = thread.scrollHeight;
  }
}

function parseData(data) {
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

function handleEvent(name, data, assistant, el) {
  if (name === "token") {
    const token = parseData(data);
    assistant.content += typeof token === "string" ? token : String(token);
    el.querySelector(".body").innerHTML = md(assistant.content) + `<span class="cursor"></span>`;
    $("thread").scrollTop = $("thread").scrollHeight;
    return;
  }
  if (name === "tool") {
    const payload = parseData(data) || {};
    const log = $("toolsLog");
    log.hidden = false;
    const shortArgs = String(payload.args || "").slice(0, 80);
    if (payload.status === "running") {
      log.textContent += `▸ ${payload.name}(${shortArgs})\n`;
    } else {
      const result = String(payload.result || "").replace(/\s+/g, " ").slice(0, 160);
      log.textContent += `  ↳ ${result}\n`;
    }
    return;
  }
  if (name === "error") {
    let payload;
    try {
      payload = JSON.parse(data);
    } catch {
      payload = { message: data };
    }
    throw new Error(payload.message || "Ошибка OpenAI");
  }
}

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage();
});
$("input").addEventListener("input", autosize);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
$("newChat").addEventListener("click", () => {
  state.currentId = null;
  ensureChat();
  render();
});
$("openSettings").addEventListener("click", () => showSettings(true));
$("closeSettings").addEventListener("click", () => showSettings(false));
$("saveSettings").addEventListener("click", saveSettings);
$("testKey").addEventListener("click", testKey);
$("toolsToggle").addEventListener("change", (e) => {
  state.settings.toolsEnabled = e.target.checked;
  save();
});
$("temperature").addEventListener("input", (e) => {
  $("tempVal").textContent = e.target.value;
});
$("toggleRail").addEventListener("click", () => $("rail").classList.toggle("open"));
$("settingsModal").addEventListener("click", (e) => {
  if (e.target.id === "settingsModal") showSettings(false);
});

if (window.marked) {
  window.marked.setOptions({ gfm: true, breaks: true });
}

load();
if (!state.conversations.length) ensureChat();
render();
if (!state.settings.apiKey) {
  setTimeout(() => showSettings(true), 400);
}
