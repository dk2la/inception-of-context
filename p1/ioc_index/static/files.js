IOC.registerTab({
  id: "files",
  render(el) {
    el.innerHTML = `<div class="card"><h3>Files in target</h3>
      <div class="small" style="margin-bottom:8px">Real content from disk, with the index's chunk boundaries marked as ▸. Click a marker to select the chunk that begins there.</div>
      <div class="split"><div class="side" id="fl-list"></div><div><div class="small" id="fl-meta"></div><div class="code" id="fl-code"></div></div></div></div>`;
    IOC.onEvent(ev => { if (this.el.classList.contains("active") && ev.path && ev.path === this.current) this.open(ev.path); });
  },
  async onShow() {
    const f = await IOC.api("/files");
    const list = this.el.querySelector("#fl-list");
    list.innerHTML = f.files.map(x => `<div class="item" data-p="${IOC.esc(x.path)}"><span>${IOC.esc(x.path)}</span><span class="small">${x.chunks}</span></div>`).join("");
    list.querySelectorAll(".item").forEach(i => i.onclick = () => this.open(i.dataset.p));
    if (!this.current && f.files.length) this.current = f.files[0].path;
    if (this.current) this.open(this.current);
  },
  async open(path) {
    this.current = path;
    this.el.querySelectorAll("#fl-list .item").forEach(i => i.classList.toggle("active", i.dataset.p === path));
    let f; try { f = await IOC.api("/file?path=" + encodeURIComponent(path)); } catch (e) { this.el.querySelector("#fl-code").textContent = e.message; return; }
    this.el.querySelector("#fl-meta").textContent = `${f.path} · ${f.lines} lines · ${f.bytes} bytes · ${f.chunks.length} chunks`;
    const starts = {}; f.chunks.forEach((c, i) => starts[c.start_line] = {...c, n: i + 1});
    const lines = f.content.split("\n"); if (lines.length && lines[lines.length - 1] === "") lines.pop();
    const out = [];
    lines.forEach((l, i) => {
      const no = i + 1, c = starts[no];
      if (c) out.push(`<div class="cb">chunk #${c.n} · ${IOC.esc(c.kind)} ${IOC.esc(c.symbol)} · starts at line ${no} (to ${c.end_line})</div>`);
      out.push(`<div class="ln" data-l="${no}"><span class="mk" data-s="${c ? no : ""}">${c ? "▸" : ""}</span><span class="no">${no}</span><span>${IOC.esc(l) || " "}</span></div>`);
    });
    const code = this.el.querySelector("#fl-code"); code.innerHTML = out.join("");
    code.querySelectorAll(".mk[data-s]").forEach(m => m.onclick = () => {
      const c = starts[+m.dataset.s]; if (!c) return;
      code.querySelectorAll(".ln").forEach(r => { const l = +r.dataset.l; r.classList.toggle("sel", l >= c.start_line && l <= c.end_line); });
    });
  }
});
