IOC.registerTab({
  id: "overview",
  render(el) {
    el.innerHTML = `
      <div class="card"><h3>Status</h3><div class="grid" id="ov-stats"></div></div>
      <div class="card"><h3>Indexed files</h3><div class="filelist" id="ov-files"></div></div>
      <div class="card"><h3>Live activity</h3><div class="feed" id="ov-feed"><div class="small">no file activity yet. edit a file in the target to see live updates.</div></div></div>`;
    this.feed = el.querySelector("#ov-feed"); this.empty = true;
    IOC.onEvent(ev => this.push(ev));
    IOC.api("/events/recent?n=30").then(evs => evs.forEach(ev => this.push(ev, true)));
  },
  push(ev, initial) {
    if (this.empty) { this.feed.innerHTML = ""; this.empty = false; }
    const time = new Date(ev.ts * 1000).toLocaleTimeString();
    const skip = new Set(["seq", "ts", "type"]);
    const detail = Object.entries(ev).filter(([k]) => !skip.has(k)).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join("  ");
    const d = document.createElement("div");
    d.innerHTML = `<span class="t">${time}</span> <span class="ty ${IOC.esc(ev.type)}">${IOC.esc(ev.type)}</span> ${IOC.esc(detail)}`;
    this.feed.prepend(d);
    if (!initial && this.el.classList.contains("active")) this.loadSoon();
  },
  loadSoon() { clearTimeout(this.t); this.t = setTimeout(() => this.load(), 400); },
  onShow() { this.load(); },
  async load() {
    const s = await IOC.refreshStatus(); if (!s) return;
    const cards = [["Chunks indexed", s.chunks, true], ["Target project", s.target], ["Chroma path", s.chroma_path],
      ["Embedding model", s.embed_model], ["Ask model", s.ask_model], ["Code model", s.code_model],
      ["Ollama backend", s.ollama_url], ["Watcher", s.watcher], ["Indexer", s.state]];
    this.el.querySelector("#ov-stats").innerHTML = cards.map(([k, v, hl]) =>
      `<div class="stat ${hl ? "hl" : ""}"><div class="k">${k}</div><div class="v">${IOC.esc(v)}</div></div>`).join("");
    const f = await IOC.api("/files");
    const max = Math.max(1, ...f.files.map(x => x.chunks));
    this.el.querySelector("#ov-files").innerHTML = f.files.map(x =>
      `<div class="row"><span class="p">${IOC.esc(x.path)}</span><span class="n">${x.chunks} chunk${x.chunks === 1 ? "" : "s"}</span>
       <span class="bar"><i style="width:${Math.round(100 * x.chunks / max)}%"></i></span></div>`).join("") || `<div class="small">nothing indexed yet</div>`;
  }
});
