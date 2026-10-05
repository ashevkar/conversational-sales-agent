// Chat UI for the Olist sales agent (layout per ui.txt). Talks to server.py's JSON API.
// Model output is always inserted with textContent; only the static icon strings
// below are inserted as markup. Metric tiles show values copied from the result
// table, never computed or invented ones.

const $ = (id) => document.getElementById(id);
const chat = $("chat"), welcome = $("welcome"), messagesEl = $("messages");
const form = $("composer"), input = $("input"), sendBtn = $("send");
const historyEl = $("history"), historyEmpty = $("history-empty");
const sidebar = $("sidebar"), scrim = $("scrim");
const settingsBtn = $("settings"), settingsPanel = $("settings-panel");

let busy = false;
let info = { model: "local model", base_url: "" };

// ---- icons (inline SVG, static strings) ---------------------------------------
const ICONS = {
  chart: '<path d="M5 17V9M12 17V5M19 17v-8"/><path d="M3 19h18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  sun: '<path d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/><circle cx="12" cy="12" r="4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.7 1.7-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-2.4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L8 17l.1-.1A1.7 1.7 0 0 0 8.4 15a1.7 1.7 0 0 0-1.6-1H6v-2.4h.8a1.7 1.7 0 0 0 1.6-1A1.7 1.7 0 0 0 8.1 9L8 8.9 9.7 7.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.2h2.4V6a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L20 8.9l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v2.4h-.2a1.7 1.7 0 0 0-1.8.7z"/>',
  bubble: '<path d="M4 17.5V6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 3v-3.2A2.5 2.5 0 0 1 4 17.5Z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/>',
  send: '<path d="m5 12 14-7-4 14-3.5-6.5L5 12Z"/><path d="M11.5 12.5 19 5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  spark: '<path d="M12 3v4M7 5l2 3M17 5l-2 3M5 12h4M15 12h4M7 19l2-3M17 19l-2-3"/><circle cx="12" cy="12" r="4"/>',
  check: '<path d="m5 12 5 5L20 7"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
  code: '<path d="m9 8-5 4 5 4M15 8l5 4-5 4"/>',
  reply: '<path d="m17 14 4-4-4-4M21 10H9a5 5 0 0 0-5 5v1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.7M12 17h.01"/>',
  ban: '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
  alert: '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>',
  review: '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
  trend: '<path d="M4 19V5M4 19h17"/><path d="m7 15 4-4 3 2 5-7"/>',
  list: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  pin: '<path d="M12 21s7-6.2 7-12a7 7 0 0 0-14 0c0 5.8 7 12 7 12Z"/><circle cx="12" cy="9" r="2.5"/>',
  box: '<path d="M3 7l9-4 9 4-9 4-9-4Z"/><path d="M3 7v10l9 4 9-4V7M12 11v10"/>',
  card: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/>',
  truck: '<path d="M3 6h11v10H3zM14 9h4l3 3v4h-7"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>',
  chat: '<path d="M4 5h16v12H7l-3 3z"/>',
  // Logo (robot, from svgrepo.com): a filled icon, drawn in currentColor.
  robot: '<path d="M9,15a1,1,0,1,0,1,1A1,1,0,0,0,9,15ZM2,14a1,1,0,0,0-1,1v2a1,1,0,0,0,2,0V15A1,1,0,0,0,2,14Zm20,0a1,1,0,0,0-1,1v2a1,1,0,0,0,2,0V15A1,1,0,0,0,22,14ZM17,7H13V5.72A2,2,0,0,0,14,4a2,2,0,0,0-4,0,2,2,0,0,0,1,1.72V7H7a3,3,0,0,0-3,3v9a3,3,0,0,0,3,3H17a3,3,0,0,0,3-3V10A3,3,0,0,0,17,7ZM13.72,9l-.5,2H10.78l-.5-2ZM18,19a1,1,0,0,1-1,1H7a1,1,0,0,1-1-1V10A1,1,0,0,1,7,9H8.22L9,12.24A1,1,0,0,0,10,13h4a1,1,0,0,0,1-.76L15.78,9H17a1,1,0,0,1,1,1Zm-3-4a1,1,0,1,0,1,1A1,1,0,0,0,15,15Z"/>',
};
const FILLED = new Set(["robot"]);

function icon(name) {
  const t = document.createElement("template");
  const cls = FILLED.has(name) ? ' class="filled"' : "";
  t.innerHTML = `<svg viewBox="0 0 24 24"${cls} aria-hidden="true">${ICONS[name] || ""}</svg>`;
  return t.content.firstChild;
}
document.querySelectorAll("[data-icon]").forEach((n) => n.prepend(icon(n.dataset.icon)));

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

// ---- motion (GSAP when available; nothing when reduced motion is requested) ----
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const G = () => (!reducedMotion && window.gsap ? window.gsap : null);

function enter(node, vars = {}) {
  const g = G();
  if (g) g.from(node, { opacity: 0, y: 14, duration: 0.45, ease: "power3.out", clearProps: "transform,opacity", ...vars });
}

function countUp(node, text) {
  // Animate a number up to its exact value; the final text is the original string.
  const g = G();
  const m = /^-?[\d,]+(\.(\d+))?$/.exec(text);
  if (!g || !m) { node.textContent = text; return; }
  const target = parseFloat(text.replace(/,/g, ""));
  const decimals = m[2] ? m[2].length : 0;
  const useCommas = text.includes(",") || Math.abs(target) >= 1000;
  const fmt = (v) => useCommas
    ? v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    : v.toFixed(decimals);
  const state = { v: 0 };
  g.to(state, { v: target, duration: 0.8, ease: "power2.out",
                onUpdate: () => (node.textContent = fmt(state.v)),
                onComplete: () => (node.textContent = text) });
}

function introAnimation() {
  const g = G();
  if (!g) return;
  const tl = g.timeline({ defaults: { ease: "power3.out", clearProps: "transform,opacity" } });
  tl.from(".brand, .new-chat, .section-label", { opacity: 0, x: -12, duration: 0.4, stagger: 0.06 })
    .from(".status", { opacity: 0, y: 10, duration: 0.4 }, "<0.1")
    .from(".topbar > *", { opacity: 0, y: -8, duration: 0.35, stagger: 0.05 }, 0.05)
    .from(".welcome-icon", { opacity: 0, scale: 0.6, duration: 0.55, ease: "back.out(2)" }, 0.15)
    .from(".welcome h1, .welcome p", { opacity: 0, y: 14, duration: 0.45, stagger: 0.08 }, 0.25)
    .from(".suggestion", { opacity: 0, y: 16, duration: 0.45, stagger: 0.07 }, 0.35)
    .from(".input-box", { opacity: 0, y: 18, duration: 0.5 }, 0.3);
  // Safeguard: if animation frames are throttled (background tab), never leave
  // the intro half-faded; jump to the end.
  setTimeout(() => tl.progress(1), 2500);
}

// ---- chat history (localStorage, best effort) -----------------------------------
// Each chat: { id, title, updated, messages: [{role:"user", text, ts} | {role:"agent", reply, asked, ts}] }
// The chat id doubles as the server session id, so reopening a chat keeps its
// follow-up context for as long as server.py keeps running.
const STORE_KEY = "sales-agent-chats";
const MAX_CHATS = 30;

function loadChats() {
  try {
    const data = JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
    return Array.isArray(data) ? data : [];
  } catch { return []; }
}
function saveChats() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(chats.slice(0, MAX_CHATS))); } catch { /* unavailable */ }
}

let chats = loadChats();
let activeId = null;
const newId = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + String(Math.random()).slice(2));
const activeChat = () => chats.find((c) => c.id === activeId);

function record(message) {
  let c = activeChat();
  if (!c) {
    c = { id: activeId, title: message.text, updated: Date.now(), messages: [] };
    chats.unshift(c);
  }
  c.messages.push(message);
  c.updated = Date.now();
  chats = [c, ...chats.filter((x) => x !== c)];
  saveChats();
  renderHistory();
}

function historyIcon(title) {
  const t = title.toLowerCase();
  if (/review|rating|score/.test(t)) return "review";
  if (/deliver|late|shipping|freight/.test(t)) return "truck";
  if (/pay|boleto|card|installment/.test(t)) return "card";
  if (/state|s[ãa]o paulo|rio|city|region/.test(t)) return "pin";
  if (/revenue|trend|month|quarter|year|compare/.test(t)) return "trend";
  if (/categor|product/.test(t)) return "list";
  if (/order/.test(t)) return "box";
  return "chat";
}

function renderHistory() {
  historyEl.replaceChildren();
  historyEmpty.hidden = chats.length > 0;
  for (const c of chats) {
    const item = el("div", "history-item" + (c.id === activeId ? " active" : ""));
    const open = el("button", "open");
    open.type = "button";
    open.title = c.title;
    open.append(icon(historyIcon(c.title)), el("span", null, c.title));
    open.addEventListener("click", () => openChat(c.id));
    const del = el("button", "delete");
    del.type = "button";
    del.setAttribute("aria-label", "Delete conversation");
    del.append(icon("x"));
    del.addEventListener("click", () => deleteChat(c.id, item));
    item.append(open, del);
    historyEl.append(item);
  }
}

function clearMessages() { messagesEl.replaceChildren(); }

function showWelcome(show) {
  if (welcome.hidden === !show) return;
  welcome.hidden = !show;
  if (show) enter(welcome, { y: 10 });
}

function openChat(id) {
  if (busy) return;
  const c = chats.find((x) => x.id === id);
  if (!c) return;
  activeId = id;
  clearMessages();
  showWelcome(false);
  for (const m of c.messages) {
    if (m.role === "user") addUser(m.text, m.ts, false, m.followUpOf || null);
    else addAgent(m.reply, m.asked, m.ts, false);
  }
  const g = G();
  if (g) g.from(messagesEl.children, { opacity: 0, y: 8, duration: 0.3, stagger: 0.03, clearProps: "all" });
  renderHistory();
  closeSidebar();
  endFollowUp();
  scrollToBottom(false);
  input.focus();
}

function newChat() {
  if (busy) return;
  activeId = null;
  clearMessages();
  showWelcome(true);
  renderHistory();
  closeSidebar();
  endFollowUp();
  input.focus();
}

function deleteChat(id, item) {
  if (busy && id === activeId) return;
  const done = () => {
    chats = chats.filter((c) => c.id !== id);
    saveChats();
    if (id === activeId) newChat(); else renderHistory();
  };
  const g = G();
  if (g && item) g.to(item, { opacity: 0, x: -16, height: 0, duration: 0.25, ease: "power2.in", onComplete: done });
  else done();
}

// ---- result table: parse db.format_table's plain-text output ---------------------
const NUMERIC = /^-?[\d,]+(\.\d+)?%?$/;
const TIME_COL = /(^|_)(year|quarter|month)$/i;
const COUNT_COL = /(^|_)(orders?|count|n|reviews?|items?|customers?|sellers?)$/i;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December"];

function parseTable(text) {
  const lines = (text || "").split("\n");
  if (lines.length < 2 || !/^-+(-\+-+)*-*$/.test(lines[1].trim())) return null;
  const split = (line) => line.split(" | ").map((c) => c.trim());
  const header = split(lines[0]);
  const rows = [], captions = [];
  for (const line of lines.slice(2)) {
    const cells = split(line);
    if (cells.length === header.length && !line.startsWith("(") && !line.startsWith("...")) rows.push(cells);
    else if (line.trim()) captions.push(line.trim());
  }
  return { header, rows, captions };
}

const human = (col) => col.replace(/_/g, " ");

function roles(header, rows) {
  const labels = [], measures = [];
  header.forEach((h, i) => {
    const vals = rows.map((r) => r[i]).filter((v) => v !== "NULL");
    if (!TIME_COL.test(h) && vals.length && vals.every((v) => NUMERIC.test(v))) measures.push(i);
    else labels.push(i);
  });
  return { labels, measures };
}

function labelOf(header, row, labels) {
  return labels.map((i) => {
    const h = header[i].toLowerCase(), v = row[i];
    if (/month$/.test(h) && /^\d+$/.test(v) && +v >= 1 && +v <= 12) return MONTHS[+v - 1];
    if (/quarter$/.test(h) && /^\d$/.test(v)) return "Q" + v;
    return v;
  }).join(" · ");
}

// Metric tiles: values copied from the table (a single row's values, or the row
// count plus the highest and lowest row of the main measure). Nothing computed.
function metricsFor(parsed) {
  if (!parsed || !parsed.rows.length) return [];
  const { header, rows, captions } = parsed;
  const { labels, measures } = roles(header, rows);
  if (!measures.length) return [];
  if (rows.length === 1) {
    return measures.slice(0, 3).map((i) => ({ label: human(header[i]), value: rows[0][i],
                                             sub: labels.length ? labelOf(header, rows[0], labels) : "" }));
  }
  const main = measures.find((i) => !COUNT_COL.test(header[i])) ?? measures[0];
  const num = (v) => parseFloat(v.replace(/[,%]/g, ""));
  const valid = rows.filter((r) => r[main] !== "NULL");
  let hi = valid[0], lo = valid[0];
  for (const r of valid) {
    if (num(r[main]) > num(hi[main])) hi = r;
    if (num(r[main]) < num(lo[main])) lo = r;
  }
  const truncated = captions.some((c) => c.startsWith("..."));
  return [
    { label: "Rows", value: String(rows.length) + (truncated ? "+" : ""), sub: truncated ? "first 50 shown" : "in the result" },
    // A cut-off result only shows its first 50 rows: say "shown", not overall.
    { label: `Highest ${human(header[main])}${truncated ? " shown" : ""}`, value: hi[main], sub: labelOf(header, hi, labels) },
    { label: `Lowest ${human(header[main])}${truncated ? " shown" : ""}`, value: lo[main], sub: labelOf(header, lo, labels) },
  ];
}

function renderTable(parsed, text) {
  const frag = document.createDocumentFragment();
  if (!parsed) { frag.append(el("pre", "sql", text)); return frag; }
  const { header, rows, captions } = parsed;
  const numeric = header.map((_, i) => {
    const vals = rows.map((r) => r[i]).filter((v) => v !== "NULL");
    return vals.length > 0 && vals.every((v) => NUMERIC.test(v));
  });
  const ranked = rows.length > 1;
  const table = el("table", "table");
  const hr = el("tr");
  if (ranked) hr.append(el("th", "rank", "#"));
  header.forEach((h, i) => hr.append(el("th", numeric[i] ? "num" : "", human(h))));
  const thead = el("thead"); thead.append(hr);
  const tbody = el("tbody");
  rows.forEach((r, n) => {
    const tr = el("tr");
    if (ranked) tr.append(el("td", "rank", String(n + 1)));
    r.forEach((v, i) => tr.append(el("td", numeric[i] ? "num" : "", v)));
    tbody.append(tr);
  });
  table.append(thead, tbody);
  const wrap = el("div", "table-wrap"); wrap.append(table);
  frag.append(wrap);
  for (const c of captions) frag.append(el("p", "caption", c));
  return frag;
}

// ---- messages -------------------------------------------------------------------
const timeOf = (ts) => new Date(ts || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function messageShell(kind, name, ts) {
  const row = el("div", "message");
  const avatar = el("div", "avatar " + kind);
  avatar.append(icon(kind === "user" ? "user" : "spark"));
  const content = el("div", "message-content");
  const meta = el("div", "message-meta", name);
  meta.append(el("time", null, typeof ts === "string" ? ts : timeOf(ts)));
  content.append(meta);
  row.append(avatar, content);
  return { row, content, meta };
}

// followUpOf: the earlier question this message follows up on (shown as a quote).
function addUser(text, ts, animate = true, followUpOf = null) {
  const { row, content } = messageShell("user", "You", ts);
  const bubble = el("div", "bubble");
  if (followUpOf) {
    const quote = el("div", "reply-quote");
    quote.title = followUpOf;
    quote.append(icon("reply"), el("span", "reply-quote-label", "Following up on"),
                 el("span", "reply-quote-text", `"${followUpOf}"`));
    bubble.append(quote);
  }
  bubble.append(el("span", "user-bubble", text));
  content.append(bubble);
  messagesEl.append(row);
  if (animate) enter(row);
  scrollToBottom();
}

function copyButton(cls, label, getText) {
  const btn = el("button", cls);
  btn.type = "button";
  const text = el("span", null, label);
  btn.append(icon("copy"), text);
  btn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(getText()); text.textContent = "Copied"; }
    catch { text.textContent = "Copy failed"; }
    setTimeout(() => (text.textContent = label), 1500);
  });
  return btn;
}

function splitNote(text) {
  const i = (text || "").indexOf("\nNote: ");
  return i < 0 ? [text || "", ""] : [text.slice(0, i), text.slice(i + 7)];
}

const CALLOUTS = {
  clarify: ["help", "Needs a detail"],
  cannot: ["ban", "Can't answer from this data"],
  error: ["alert", "Couldn't answer"],
};

function addAgent(reply, asked, ts, animate = true) {
  const { row, content } = messageShell("ai", "Sales Analyst", ts);
  const kind = reply.kind || "answer";
  const [mainText, note] = splitNote(reply.text);

  if (kind !== "answer") {
    // Small talk ("chat") is a plain, friendly reply: no label, no card, no SQL.
    // (Older saved chats stored it as a code-written "cannot" reply.)
    const smallTalk = kind === "chat"
      || (kind === "cannot" && !reply.attempts && mainText.startsWith("I answer questions"));
    if (reply.question && reply.question !== asked && !smallTalk) {
      const p = el("p", "interpreted", "Interpreted as: ");
      p.append(el("b", null, reply.question));
      content.append(p);
    }
    if (smallTalk) {
      content.append(el("div", "bubble", mainText));
    } else {
      const box = el("div", "callout " + kind);
      const [ic, label] = CALLOUTS[kind] || CALLOUTS.error;
      const lab = el("span", "label"); lab.append(icon(ic), el("span", null, label));
      box.append(lab, document.createElement("br"), document.createTextNode(mainText));
      content.append(box);
    }
  } else {
    content.append(el("div", "bubble", mainText));
    if (note) {
      const n = el("div", "note"); n.append(icon("info"), el("span", null, note));
      content.append(n);
    }
    content.append(answerCard(reply, asked, animate));
  }
  const followButtons = messagesEl.querySelectorAll(".follow-btn");
  followButtons.forEach((b) => b.remove());
  messagesEl.append(row);
  if (animate) enter(row);
  scrollToBottom();
}

function answerCard(reply, asked, animate) {
  const card = el("div", "answer-card");
  const parsed = parseTable(reply.table);

  const head = el("div", "answer-head");
  head.append(el("strong", null, reply.question || asked));
  const status = el("span");
  const parts = ["Query completed"];
  if (reply.elapsed != null) parts.push(`${reply.elapsed}s`);
  if (reply.attempts > 1) parts.push(`${reply.attempts} attempts`);
  status.append(icon("check"), el("span", null, parts.join(" · ")));
  head.append(status);
  card.append(head);

  const metrics = metricsFor(parsed);
  if (metrics.length) {
    const rowEl = el("div", "metric-row");
    rowEl.style.setProperty("--cols", metrics.length);
    const values = [];
    for (const m of metrics) {
      const tile = el("div", "metric");
      const value = el("div", "metric-value");
      tile.append(el("div", "metric-label", m.label), value);
      if (m.sub) tile.append(el("div", "metric-sub", m.sub));
      rowEl.append(tile);
      values.push([value, m.value]);
    }
    card.append(rowEl);
    for (const [node, text] of values) animate ? countUp(node, text) : (node.textContent = text);
    const g = G();
    if (animate && g) g.from(rowEl.children, { opacity: 0, y: 10, duration: 0.4, stagger: 0.08, delay: 0.15,
                                                ease: "power3.out", clearProps: "transform,opacity" });
  }

  // Result table, collapsed until asked for. The SQL is not shown in the UI
  // (the terminal chat and the eval results still record it).
  const details = el("div", "details");
  details.hidden = true;
  if (reply.table) {
    const step = el("div", "step");
    const n = parsed ? parsed.rows.length : null;
    const title = el("p", "step-title");
    title.append(icon("table"), el("span", null, n == null ? "Result" : `Result · ${n} row${n === 1 ? "" : "s"}`));
    step.append(title, renderTable(parsed, reply.table));
    details.append(step);
  }
  card.append(details);

  const footer = el("div", "answer-footer");
  if (reply.table) {
    const toggle = el("button", "mini-btn");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    const toggleText = el("span", null, "Show result table");
    toggle.append(icon("table"), toggleText);
    toggle.addEventListener("click", () => toggleDetails(details, toggle, toggleText));
    footer.append(toggle);
  }
  // The agent follows up on the latest answered question, so only the latest
  // answer offers "Follow up" (older buttons are removed when a new answer arrives).
  const follow = el("button", "mini-btn follow-btn");
  follow.type = "button";
  follow.append(icon("reply"), el("span", null, "Follow up"));
  follow.addEventListener("click", () => startFollowUp(asked, reply.question, parsed));
  footer.append(copyButton("mini-btn", "Copy answer", () => reply.text || ""), follow);
  card.append(footer);
  return card;
}

const followup = $("followup"), followupText = $("followup-text"), followupFull = $("followup-full");
let followUpOf = null;  // the question the next message follows up on, while the card is shown

// Show the question the user asked (their own words); if the agent rewrote it
// into a fuller standalone question, show that too, so the context is clear.
function startFollowUp(asked, interpreted, parsed) {
  followUpOf = asked;
  followupText.textContent = `"${asked}"`;
  const differs = interpreted && interpreted.trim() !== asked.trim();
  followupFull.hidden = !differs;
  followupFull.textContent = differs ? `Understood as: ${interpreted}` : "";
  const wasHidden = followup.hidden;
  followup.hidden = false;
  // Suggest a follow-up that fits the result's shape.
  const multi = parsed && parsed.rows.length > 1;
  input.placeholder = multi ? "Ask a follow-up, e.g. only count delivered orders, or: break that down by state"
                            : "Ask a follow-up, e.g. how does that compare with the previous year?";
  scrollToBottom();
  input.focus();
  const g = G();
  if (g) {
    if (wasHidden) g.from(followup, { opacity: 0, y: 8, scale: 0.96, duration: 0.3, ease: "back.out(2)", clearProps: "all" });
    g.fromTo(".input-box", { boxShadow: "0 0 0 0 rgba(99, 91, 255, .45)" },
             { boxShadow: "0 0 0 6px rgba(99, 91, 255, 0)", duration: 0.7, ease: "power2.out", clearProps: "boxShadow" });
  }
}

function endFollowUp() {
  followUpOf = null;
  followup.hidden = true;
  input.placeholder = "Ask a question about your sales data...";
}
$("followup-close").addEventListener("click", () => { endFollowUp(); input.focus(); });

function toggleDetails(details, toggle, text) {
  const opening = details.hidden;
  toggle.setAttribute("aria-expanded", String(opening));
  text.textContent = opening ? "Hide result table" : "Show result table";
  const g = G();
  if (opening) {
    details.hidden = false;
    if (g) g.fromTo(details, { height: 0, opacity: 0 }, { height: "auto", opacity: 1, duration: 0.35,
                                                         ease: "power2.out", clearProps: "height,opacity" });
  } else if (g) {
    g.to(details, { height: 0, opacity: 0, duration: 0.25, ease: "power2.in",
                    onComplete: () => { details.hidden = true; g.set(details, { clearProps: "height,opacity" }); } });
  } else {
    details.hidden = true;
  }
}

function addThinking() {
  const { row, content } = messageShell("ai", "Sales Analyst", "thinking…");
  const card = el("div", "thinking-card");
  const line = el("div", "thinking-line");
  const dots = el("span", "dots"); dots.append(el("i"), el("i"), el("i"));
  const label = el("span", null, "Thinking… writing and checking the SQL");
  line.append(dots, label);
  const s1 = el("div", "skeleton"); s1.style.width = "72%";
  const s2 = el("div", "skeleton"); s2.style.width = "46%";
  card.append(line, s1, s2);
  content.append(card);
  messagesEl.append(row);
  enter(row);
  scrollToBottom();

  const g = G();
  const pulse = g ? g.to(dots.children, { opacity: 1, y: -3, duration: 0.4, stagger: 0.15, repeat: -1,
                                          yoyo: true, ease: "sine.inOut" }) : null;
  const start = Date.now();
  const timer = setInterval(() => {
    const s = Math.round((Date.now() - start) / 1000);
    label.textContent = `Thinking… ${s}s · writing and checking the SQL on your local model`;
  }, 1000);
  return () => { clearInterval(timer); if (pulse) pulse.kill(); row.remove(); };
}

function scrollToBottom(smooth = true) {
  requestAnimationFrame(() => chat.scrollTo({ top: chat.scrollHeight, behavior: smooth ? "smooth" : "auto" }));
}

// ---- API --------------------------------------------------------------------------
async function post(path, body) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify(body) });
  let data = {};
  try { data = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) throw new Error(data.error || `Server error (${res.status})`);
  return data;
}

function setBusy(on) {
  busy = on;
  input.disabled = on;
  sendBtn.disabled = on;
  document.body.classList.toggle("busy", on);
  if (!on) input.focus();
}

async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  const g = G();
  if (g) g.fromTo(sendBtn, { scale: 0.86 }, { scale: 1, duration: 0.4, ease: "back.out(3)", clearProps: "transform" });
  if (!activeId) activeId = newId();
  const chatId = activeId;
  showWelcome(false);
  const ts = Date.now();
  const quoted = followUpOf;  // captured before endFollowUp() clears it below
  addUser(text, ts, true, quoted);
  record({ role: "user", text, ts, ...(quoted ? { followUpOf: quoted } : {}) });
  input.value = "";
  endFollowUp();
  autosize();
  setBusy(true);
  const stopThinking = addThinking();
  let reply;
  try {
    reply = await post("/api/chat", { session: chatId, message: text });
  } catch (e) {
    const msg = e instanceof TypeError ? "Can't reach the UI server. Is server.py still running?" : e.message;
    reply = { kind: "error", text: msg };
    checkHealth();
  }
  stopThinking();
  const replyTs = Date.now();
  addAgent(reply, text, replyTs);
  record({ role: "agent", reply, asked: text, ts: replyTs });
  setBusy(false);
}

// ---- status, theme, settings, drawer -------------------------------------------------
function runtimeOf(url) {
  if (/:8080\b/.test(url)) return "llama.cpp";
  if (/:11434\b/.test(url)) return "Ollama";
  if (/:1234\b/.test(url)) return "LM Studio";
  return "local server";
}

async function checkHealth() {
  const status = $("status"), badge = $("online-badge");
  try {
    const h = await (await fetch("/api/health")).json();
    status.classList.toggle("ok", h.ok);
    status.classList.toggle("err", !h.ok);
    badge.className = "badge " + (h.ok ? "ok" : "err");
    badge.textContent = h.ok ? "Online" : "Offline";
    $("status-text").textContent = h.ok ? "Local model connected" : "Local model unavailable";
    $("status-sub").textContent = h.ok ? `${info.model} · ${runtimeOf(info.base_url)} · ready`
                                       : (h.error || "Model server not reachable").slice(0, 160);
  } catch {
    status.classList.remove("ok"); status.classList.add("err");
    badge.className = "badge err"; badge.textContent = "Offline";
    $("status-text").textContent = "UI server unreachable";
    $("status-sub").textContent = "Is server.py still running?";
  }
}

const THEME_KEY = "sales-agent-theme";
function currentTheme() {
  return document.documentElement.dataset.theme
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function applyTheme(theme, animate) {
  document.documentElement.dataset.theme = theme;
  const btn = $("theme");
  btn.replaceChildren(icon(theme === "dark" ? "moon" : "sun"));
  const g = G();
  if (animate && g) g.from(btn.firstChild, { rotate: -90, scale: 0.6, opacity: 0, duration: 0.4, ease: "back.out(2)" });
}
try { const saved = localStorage.getItem(THEME_KEY); if (saved) applyTheme(saved, false); } catch { /* ignore */ }
applyTheme(currentTheme(), false);
$("theme").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  applyTheme(next, true);
  try { localStorage.setItem(THEME_KEY, next); } catch { /* ignore */ }
});

function toggleSettings(open = settingsPanel.hidden) {
  settingsPanel.hidden = !open;
  settingsBtn.setAttribute("aria-expanded", String(open));
  const g = G();
  if (open && g) g.from(settingsPanel, { opacity: 0, y: -6, duration: 0.25, ease: "power2.out", clearProps: "all" });
}
settingsBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleSettings(); });
settingsPanel.addEventListener("click", (e) => e.stopPropagation());
document.addEventListener("click", () => { if (!settingsPanel.hidden) toggleSettings(false); });
$("clear-all").addEventListener("click", () => {
  if (busy || !confirm("Delete all saved conversations from this browser?")) return;
  chats = [];
  saveChats();
  newChat();
  toggleSettings(false);
});

function openSidebar() {
  sidebar.classList.add("open");
  scrim.hidden = false;
  const g = G();
  if (g) {
    g.fromTo(sidebar, { x: "-100%" }, { x: 0, duration: 0.32, ease: "power3.out" });
    g.fromTo(scrim, { opacity: 0 }, { opacity: 1, duration: 0.25 });
  }
}
function closeSidebar() {
  if (!sidebar.classList.contains("open")) return;
  const g = G();
  const done = () => { sidebar.classList.remove("open"); scrim.hidden = true; if (g) g.set([sidebar, scrim], { clearProps: "all" }); };
  if (g) {
    g.to(scrim, { opacity: 0, duration: 0.2 });
    g.to(sidebar, { x: "-100%", duration: 0.25, ease: "power2.in", onComplete: done });
  } else done();
}
$("menu").addEventListener("click", openSidebar);
scrim.addEventListener("click", closeSidebar);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeSidebar(); if (!settingsPanel.hidden) toggleSettings(false); }
});

// ---- wiring ---------------------------------------------------------------------------
function autosize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}
form.addEventListener("submit", (e) => { e.preventDefault(); send(input.value); });
input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(input.value); }
});
$("new-chat").addEventListener("click", newChat);
document.querySelectorAll(".suggestion").forEach((card) => {
  card.addEventListener("click", () => send(card.dataset.q));
  const g = G();
  if (g) {
    card.addEventListener("mouseenter", () => g.to(card, { y: -2, duration: 0.2, ease: "power2.out" }));
    card.addEventListener("mouseleave", () => g.to(card, { y: 0, duration: 0.25, ease: "power2.out" }));
  }
});

fetch("/api/info")
  .then((r) => r.json())
  .then((d) => {
    info = d;
    $("info-model").textContent = d.model;
    $("info-server").textContent = d.base_url;
    $("info-runtime").textContent = runtimeOf(d.base_url);
  })
  .catch(() => {})
  .finally(checkHealth);
setInterval(() => { if (!busy) checkHealth(); }, 30000);

renderHistory();
introAnimation();
input.focus();
