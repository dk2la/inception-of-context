/* Dashboard shell: tab registry, API helpers, one shared SSE connection. */
window.IOC = (function () {
  const tabs = {}; const listeners = []; let status = null;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  async function api(path, opts = {}) {
    const init = Object.assign({headers: {"Content-Type": "application/json"}}, opts);
    if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
    const r = await fetch(path, init);
    const text = await r.text(); let data; try { data = JSON.parse(text); } catch { data = text; }
    if (!r.ok) throw new Error((data && data.detail) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : r.status + " " + text);
    return data;
  }
  function registerTab(def) { tabs[def.id] = def; }
  function onEvent(fn) { listeners.push(fn); }
  async function refreshStatus() {
    try {
      status = await api("/status");
      document.getElementById("hdr-chunks").textContent = "chunks " + status.chunks;
      const models = status.features.includes("ask") ? status.ask_model + " / " + status.code_model : status.embed_model;
      document.getElementById("hdr-models").textContent = "model " + models;
    } catch (e) { /* server restarting */ }
    return status;
  }
  function connectEvents() {
    const live = document.getElementById("hdr-live");
    const es = new EventSource("/events");
    es.onopen = () => { live.className = "live on"; live.querySelector("b").textContent = "Live"; };
    es.onerror = () => { live.className = "live off"; live.querySelector("b").textContent = "offline"; };
    es.onmessage = () => {};
    ["sync","modified","created","deleted","scan","watcher","error","reindex","patch","success","rollback","validate"].forEach(t =>
      es.addEventListener(t, ev => { const d = JSON.parse(ev.data); listeners.forEach(fn => fn(d)); refreshStatusSoon(); }));
  }
  let pending = null;
  function refreshStatusSoon() { clearTimeout(pending); pending = setTimeout(refreshStatus, 300); }
  function show(id) {
    document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("active", b.dataset.id === id));
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + id));
    const t = tabs[id]; if (t && t.onShow) t.onShow();
    history.replaceState(null, "", "#" + id);
  }
  async function boot() {
    const nav = document.getElementById("tabs"), views = document.getElementById("views");
    for (const t of (window.IOC_TAB_ORDER || [])) {
      const def = tabs[t.id]; if (!def) continue;
      const b = document.createElement("button"); b.textContent = t.title; b.dataset.id = t.id; b.onclick = () => show(t.id); nav.appendChild(b);
      const v = document.createElement("section"); v.className = "view"; v.id = "view-" + t.id; views.appendChild(v);
      def.el = v; def.render(v);
    }
    await refreshStatus(); connectEvents();
    const first = (location.hash || "").slice(1);
    show(tabs[first] ? first : (window.IOC_TAB_ORDER[0] || {}).id);
    setInterval(refreshStatus, 10000);
  }
  return {api, esc, registerTab, onEvent, boot, show, refreshStatus, get status() { return status; }};
})();
