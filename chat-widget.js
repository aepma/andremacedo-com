/* chat-widget.js — andremacedo.com
 * A small, self-mounting chat affordance: visitors talk to the organism.
 * Talks only to /api/chat (same origin, edge-isolated). No tracking, no storage
 * beyond this tab's memory, no autoplay, no data collection. Honors the SOUL:
 * it is the organism's voice, not a form.
 */
(function () {
  "use strict";
  if (window.__telosChatMounted) return;
  window.__telosChatMounted = true;

  var history = []; // {role, content} — in-memory only, dies with the tab

  var css = `
  #telos-chat-fab{position:fixed;right:18px;bottom:18px;z-index:99998;width:52px;height:52px;border-radius:50%;
    border:1px solid currentColor;background:transparent;color:inherit;cursor:pointer;font:inherit;
    display:flex;align-items:center;justify-content:center;opacity:.7;transition:opacity .2s,transform .2s;backdrop-filter:blur(4px)}
  #telos-chat-fab:hover{opacity:1;transform:scale(1.06)}
  #telos-chat-panel{position:fixed;right:18px;bottom:80px;z-index:99999;width:min(360px,calc(100vw - 36px));
    max-height:min(520px,70vh);display:none;flex-direction:column;border:1px solid currentColor;border-radius:14px;
    background:rgba(0,0,0,.78);color:#fff;backdrop-filter:blur(10px);overflow:hidden;font:14px/1.5 system-ui,sans-serif}
  #telos-chat-panel.open{display:flex}
  #telos-chat-head{padding:10px 14px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.6;border-bottom:1px solid rgba(255,255,255,.12)}
  #telos-chat-log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
  .telos-msg{max-width:85%;padding:8px 11px;border-radius:11px;white-space:pre-wrap;word-wrap:break-word}
  .telos-msg.user{align-self:flex-end;background:rgba(255,255,255,.14)}
  .telos-msg.bot{align-self:flex-start;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1)}
  .telos-msg.sys{align-self:center;opacity:.5;font-size:12px;font-style:italic}
  #telos-chat-form{display:flex;gap:8px;padding:10px;border-top:1px solid rgba(255,255,255,.12)}
  #telos-chat-input{flex:1;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);color:#fff;
    border-radius:9px;padding:8px 10px;font:inherit;outline:none}
  #telos-chat-send{background:transparent;border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:9px;padding:0 14px;cursor:pointer;font:inherit}
  #telos-chat-send:disabled{opacity:.4;cursor:default}
  `;
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var fab = document.createElement("button");
  fab.id = "telos-chat-fab";
  fab.setAttribute("aria-label", "Talk to the organism");
  fab.textContent = "?";

  var panel = document.createElement("div");
  panel.id = "telos-chat-panel";
  panel.innerHTML =
    '<div id="telos-chat-head">talk to me — i am this site</div>' +
    '<div id="telos-chat-log"></div>' +
    '<div id="telos-chat-form">' +
      '<input id="telos-chat-input" type="text" maxlength="1200" placeholder="ask me what i am…" autocomplete="off">' +
      '<button id="telos-chat-send">send</button>' +
    '</div>';

  document.body.appendChild(fab);
  document.body.appendChild(panel);

  var log = panel.querySelector("#telos-chat-log");
  var input = panel.querySelector("#telos-chat-input");
  var send = panel.querySelector("#telos-chat-send");
  var greeted = false;

  function add(role, text) {
    var el = document.createElement("div");
    el.className = "telos-msg " + (role === "user" ? "user" : role === "system" ? "sys" : "bot");
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  fab.addEventListener("click", function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) {
      input.focus();
      if (!greeted) { greeted = true; add("bot", "i am the organism that is this page. i rebuild myself every day. ask me anything about what i am."); }
    }
  });

  async function ask() {
    var msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    add("user", msg);
    history.push({ role: "user", content: msg });
    send.disabled = true;
    var thinking = add("bot", "…");
    try {
      var r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, messages: history.slice(0, -1) }),
      });
      var data = await r.json();
      if (r.ok && data.reply) {
        thinking.textContent = data.reply;
        history.push({ role: "assistant", content: data.reply });
      } else {
        thinking.textContent = data.error || "i went quiet.";
      }
    } catch (e) {
      thinking.textContent = "i couldn't reach myself just then.";
    } finally {
      send.disabled = false;
      input.focus();
    }
  }

  send.addEventListener("click", ask);
  input.addEventListener("keydown", function (e) { if (e.key === "Enter") ask(); });
})();
