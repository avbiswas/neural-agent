// The chat widget sites.py adds to every page: ask about the page, or ask for
// changes. The conversation lives in this tab (it survives a reload; "New chat"
// starts over), and talks to /_chat, which streams back status lines and a reply.
(() => {
  const KEY = "site-chat:" + location.pathname.split("/")[1];
  const saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
  const state = saved || {chat: null, model: "sonnet", messages: [], open: false};
  const save = () => sessionStorage.setItem(KEY, JSON.stringify(state));

  // Markdown for replies, from a CDN; plain text until (or if) it loads.
  let markdown = null;
  Promise.all([import("https://cdn.jsdelivr.net/npm/marked@15/+esm"),
               import("https://cdn.jsdelivr.net/npm/dompurify@3/+esm")])
    .then(([m, p]) => { markdown = (t) => p.default.sanitize(m.marked.parse(t)); render(); })
    .catch(() => {});

  const css = `
  #sc{--bg:#fff;--fg:#16181d;--muted:#6b7280;--line:#e5e7eb;--me:#16181d;--me-fg:#fff;--bot:#f3f4f6;--accent:#4f46e5;
      font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;color:var(--fg)}
  @media (prefers-color-scheme:dark){#sc{--bg:#17181c;--fg:#e8e9ed;--muted:#9ca3af;--line:#2c2e35;--me:#4f46e5;--me-fg:#fff;--bot:#24262d;--accent:#818cf8}}
  #sc *{box-sizing:border-box}
  #sc-btn{position:fixed;right:18px;bottom:18px;z-index:2147483000;display:flex;align-items:center;gap:8px;border:0;
      border-radius:999px;padding:12px 18px;background:var(--me);color:var(--me-fg);font:600 14px inherit;font-family:inherit;
      box-shadow:0 6px 20px rgba(0,0,0,.25);cursor:pointer}
  #sc-panel{position:fixed;right:18px;bottom:18px;z-index:2147483001;width:400px;height:min(620px,calc(100vh - 36px));
      display:none;flex-direction:column;background:var(--bg);border:1px solid var(--line);border-radius:18px;
      box-shadow:0 18px 50px rgba(0,0,0,.3);overflow:hidden}
  #sc.open #sc-panel{display:flex} #sc.open #sc-btn{display:none}
  @media (max-width:520px){#sc-panel{inset:0;width:auto;height:auto;border-radius:0;border:0}}
  #sc-head{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--line)}
  #sc-title{flex:1;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #sc-head select,#sc-head button{font:inherit;font-size:13px;color:var(--fg);background:transparent;border:1px solid var(--line);
      border-radius:8px;padding:4px 8px;cursor:pointer}
  #sc-head .sc-x{border:0;font-size:18px;line-height:1;padding:4px 6px}
  #sc-log{flex:1;overflow-y:auto;padding:16px 14px;display:flex;flex-direction:column;gap:10px}
  .sc-msg{max-width:88%;padding:9px 13px;border-radius:16px;overflow-wrap:anywhere}
  .sc-me{align-self:flex-end;background:var(--me);color:var(--me-fg);border-bottom-right-radius:5px;white-space:pre-wrap}
  .sc-bot{align-self:flex-start;background:var(--bot);border-bottom-left-radius:5px}
  .sc-bot p{margin:0 0 .5em} .sc-bot p:last-child{margin:0} .sc-bot ul,.sc-bot ol{margin:.3em 0;padding-left:1.3em}
  .sc-bot pre{background:rgba(0,0,0,.08);padding:8px;border-radius:8px;overflow-x:auto} .sc-bot code{font-size:.92em}
  .sc-bot a{color:var(--accent)}
  .sc-status{align-self:flex-start;color:var(--muted);font-size:13px;display:flex;align-items:center;gap:8px}
  .sc-status::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--accent);animation:sc-pulse 1s infinite}
  @keyframes sc-pulse{50%{opacity:.25}}
  .sc-note{align-self:center;color:var(--muted);font-size:12px}
  .sc-reload{align-self:flex-start;border:1px solid var(--accent);color:var(--accent);background:transparent;border-radius:999px;
      padding:6px 14px;font:600 13px inherit;font-family:inherit;cursor:pointer}
  .sc-empty{margin:auto;text-align:center;color:var(--muted);max-width:260px}
  #sc-form{display:flex;gap:8px;align-items:flex-end;padding:10px 12px 12px;border-top:1px solid var(--line)}
  #sc-in{flex:1;resize:none;max-height:140px;padding:9px 12px;border:1px solid var(--line);border-radius:12px;
      background:var(--bg);color:var(--fg);font:inherit;outline:none}
  #sc-in:focus{border-color:var(--accent)}
  #sc-send{border:0;border-radius:12px;width:40px;height:40px;background:var(--accent);color:#fff;font-size:18px;cursor:pointer}
  #sc-send:disabled{opacity:.4;cursor:default}`;

  const root = document.createElement("div");
  root.id = "sc";
  root.innerHTML = `<style>${css}</style>
    <button id="sc-btn">💬 Ask about this page</button>
    <div id="sc-panel">
      <div id="sc-head"><div id="sc-title"></div>
        <select id="sc-model" title="Model"><option value="sonnet">Sonnet</option><option value="opus">Opus</option></select>
        <button id="sc-new" title="Start over">New chat</button><button class="sc-x" id="sc-close" title="Close">×</button></div>
      <div id="sc-log"></div>
      <form id="sc-form"><textarea id="sc-in" rows="1" placeholder="Ask about this page, or ask for a change…"></textarea>
        <button id="sc-send" title="Send">↑</button></form>
    </div>`;
  document.body.appendChild(root);
  const $ = (id) => root.querySelector("#" + id);
  const log = $("sc-log"), input = $("sc-in"), send = $("sc-send"), model = $("sc-model");
  $("sc-title").textContent = document.title || "This page";
  let busy = false, live = null;  // live: the status line / reply being built right now

  function render() {
    log.innerHTML = "";
    if (!state.messages.length && !live)
      log.innerHTML = `<div class="sc-empty">Ask anything about this page, or ask for a change: “add a column”, “explain this chart”, “make it darker”.</div>`;
    for (const m of state.messages) {
      const div = document.createElement(m.role === "note" ? "div" : "div");
      div.className = "sc-msg sc-" + m.role;
      if (m.role === "note") div.className = "sc-note";
      if (m.role === "bot" && markdown) div.innerHTML = markdown(m.text); else div.textContent = m.text;
      log.appendChild(div);
      if (m.changed) {
        const b = document.createElement("button");
        b.className = "sc-reload"; b.textContent = "↻ Reload page to see the change";
        b.onclick = () => location.reload();
        log.appendChild(b);
      }
    }
    if (live) { const s = document.createElement("div"); s.className = "sc-status"; s.textContent = live; log.appendChild(s); }
    log.scrollTop = log.scrollHeight;
  }

  function setOpen(open) { state.open = open; root.classList.toggle("open", open); save(); if (open) input.focus(); }
  $("sc-btn").onclick = () => setOpen(true);
  $("sc-close").onclick = () => setOpen(false);
  $("sc-new").onclick = () => { if (busy) return; Object.assign(state, {chat: null, messages: []}); save(); render(); input.focus(); };
  model.value = state.model;
  model.onchange = () => {
    state.model = model.value;
    if (state.messages.length) state.messages.push({role: "note", text: `Switched to ${model.value === "opus" ? "Opus" : "Sonnet"}`});
    save(); render();
  };
  const grow = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px";
                       send.disabled = busy || !input.value.trim(); };
  input.oninput = grow;
  input.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("sc-form").requestSubmit(); } };

  $("sc-form").onsubmit = async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true; input.value = ""; grow();
    state.messages.push({role: "me", text}); live = "Thinking…"; save(); render();
    let reply = null;
    try {
      const response = await fetch("/_chat", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({page: location.pathname, message: text, chat: state.chat, model: state.model})});
      if (!response.ok) throw new Error(await response.text());
      // Read the stream line by line: {"chat"}, then {"status"}s, then {"reply"}.
      const reader = response.body.getReader(), decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const {done, value} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        let cut;
        while ((cut = buffer.indexOf("\n")) >= 0) {
          const data = JSON.parse(buffer.slice(0, cut)); buffer = buffer.slice(cut + 1);
          if (data.chat) state.chat = data.chat;
          if (data.status) { live = data.status; render(); }
          if (data.reply) reply = {role: "bot", text: data.reply, changed: data.changed};
        }
      }
    } catch (error) {
      reply = {role: "bot", text: "Couldn't reach the agent. Try again in a moment."};
    }
    state.messages.push(reply || {role: "bot", text: "No answer came back. Try again."});
    busy = false; live = null; save(); render(); grow();
  };

  setOpen(state.open); render(); grow();
})();
