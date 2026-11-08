IOC.registerTab({
  id: "explorer",
  render(el) {
    el.innerHTML = `<div class="card"><h3>ChromaDB explorer</h3>
      <div class="row-ctl"><select id="ex-path"><option value="">all files</option></select>
      <select id="ex-kind"><option value="">all kinds</option>${["module","class","function","method","config","section","block"].map(k => `<option>${k}</option>`).join("")}</select>
      <button class="btn" id="ex-prev">◀</button><span class="small" id="ex-page"></span><button class="btn" id="ex-next">▶</button></div>
      <div id="ex-rows"></div></div>`;
    this.offset = 0; this.limit = 15;
    el.querySelector("#ex-prev").onclick = () => { this.offset = Math.max(0, this.offset - this.limit); this.load(); };
    el.querySelector("#ex-next").onclick = () => { if (this.offset + this.limit < this.total) { this.offset += this.limit; this.load(); } };
    el.querySelector("#ex-path").onchange = el.querySelector("#ex-kind").onchange = () => { this.offset = 0; this.load(); };
  },
  async onShow() {
    const f = await IOC.api("/files"); const sel = this.el.querySelector("#ex-path"); const cur = sel.value;
    sel.innerHTML = `<option value="">all files</option>` + f.files.map(x => `<option ${x.path === cur ? "selected" : ""}>${IOC.esc(x.path)}</option>`).join("");
    this.load();
  },
  async load() {
    const p = new URLSearchParams({offset: this.offset, limit: this.limit});
    const path = this.el.querySelector("#ex-path").value, kind = this.el.querySelector("#ex-kind").value;
    if (path) p.set("path", path); if (kind) p.set("kind", kind);
    const d = await IOC.api("/chunks?" + p); this.total = d.total;
    this.el.querySelector("#ex-page").textContent = d.total ? `${d.offset + 1}–${Math.min(d.offset + d.limit, d.total)} of ${d.total}` : "0 chunks";
    this.el.querySelector("#ex-rows").innerHTML = d.items.map(r => `<details class="src"><summary>
      <span class="tag">${IOC.esc(r.metadata.path)}:${r.metadata.start_line}-${r.metadata.end_line}</span> ${IOC.esc(r.metadata.kind)} <b>${IOC.esc(r.metadata.symbol)}</b>
      <span class="small"> id=${IOC.esc(r.id)} hash=${IOC.esc(r.metadata.hash.slice(0, 10))}</span></summary><pre>${IOC.esc(r.document)}</pre></details>`).join("");
  }
});
