IOC.registerTab({
  id: "bonus",
  render(el) {
    el.innerHTML = `
      <div class="card"><h3>Dry run · visual diff</h3>
        <div class="small" style="margin-bottom:8px">Generates and sanity-checks a patch, then shows it as a diff. Nothing is written to disk.</div>
        <textarea id="bn-intent" placeholder="add a method count() to NoteService that returns the number of stored notes"></textarea>
        <div class="row-ctl"><label class="small">k</label><input id="bn-k" type="number" min="1" max="50" value="5" style="width:64px">
          <button class="btn primary" id="bn-dry">Dry run</button><span id="bn-st"></span></div>
        <div id="bn-out"></div></div>
      <div class="card"><h3>Last committed patch</h3><div id="bn-last" class="small">no successful patch yet</div></div>
      <div class="card"><h3>Index maintenance</h3>
        <div class="row-ctl"><button class="btn" id="bn-re">Reindex (incremental)</button><button class="btn" id="bn-reset">Drop collection + full reindex</button><span id="bn-re-out" class="small"></span></div></div>
      <div class="card"><h3>Git</h3><div id="bn-git" class="small"></div></div>`;
    el.querySelector("#bn-dry").onclick = () => this.dry();
    el.querySelector("#bn-re").onclick = () => this.reindex(false);
    el.querySelector("#bn-reset").onclick = () => this.reindex(true);
    IOC.onEvent(ev => { if (["success", "rollback", "git"].includes(ev.type) && this.el.classList.contains("active")) this.onShow(); });
  },
  diffHtml(files) {
    return files.map(f => {
      const lines = (f.diff || "(no textual change)").split("\n").map(l => {
        const c = l.startsWith("+++") || l.startsWith("---") ? "" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : "";
        return `<span class="${c}">${IOC.esc(l)}</span>`;
      }).join("\n");
      return `<details class="src" open><summary><span class="tag">${IOC.esc(f.op)}</span> ${IOC.esc(f.path)} <span class="small">+${f.added} −${f.removed}</span></summary><pre class="json diff">${lines}</pre></details>`;
    }).join("");
  },
  async dry() {
    const intent = this.el.querySelector("#bn-intent").value.trim(); if (!intent) return;
    const out = this.el.querySelector("#bn-out"), st = this.el.querySelector("#bn-st"), b = this.el.querySelector("#bn-dry");
    b.disabled = true; st.innerHTML = `<span class="small">asking the coder model…</span>`; out.innerHTML = "";
    try {
      const d = await IOC.api("/patch/dry-run", {method: "POST", body: {intent, k: +this.el.querySelector("#bn-k").value || 5}});
      st.innerHTML = `<span class="tag ${d.ok ? "ok" : "err"}">${d.ok ? "would pass the sanity checks" : "would be refused"}</span>`;
      out.innerHTML = (d.violations && d.violations.length ? `<pre class="json">${IOC.esc(d.violations.join("\n"))}</pre>` : "") +
        (d.error ? `<pre class="json">${IOC.esc(d.error)}</pre>` : "") + (d.diff ? this.diffHtml(d.diff) : "");
    } catch (e) { st.innerHTML = `<span class="tag err">${IOC.esc(e.message)}</span>`; }
    finally { b.disabled = false; }
  },
  async reindex(reset) {
    const o = this.el.querySelector("#bn-re-out"); o.textContent = "reindexing…";
    const d = await IOC.api("/reindex?reset=" + reset, {method: "POST"});
    o.textContent = `${d.files} files → ${d.chunks} chunks (+${d.added} ~${d.updated} −${d.removed}) in ${d.seconds}s`;
  },
  async onShow() {
    const h = await IOC.api("/patch/history"); const last = h.runs.find(r => r.status === "success" && r.diff);
    const el = this.el.querySelector("#bn-last");
    if (last) el.innerHTML = `<div class="row-ctl"><span class="tag ok">${IOC.esc(last.intent)}</span>` +
      (last.git ? (last.git.ok ? `<span class="tag">commit ${IOC.esc(last.git.sha)}: ${IOC.esc(last.git.message)}</span>` : `<span class="tag warn">git: ${IOC.esc(last.git.reason)}</span>`) : "") +
      `</div>` + this.diffHtml(last.diff);
    const g = await IOC.api("/git");
    this.el.querySelector("#bn-git").innerHTML = !g.repo ? "target is not the root of a git repository (auto-commit disabled for it)" :
      `auto-commit: <b>${g.autocommit ? "on" : "off (set IOC_AUTOCOMMIT=1)"}</b><table class="t">` + g.log.map(c => `<tr><td>${IOC.esc(c.sha)}</td><td>${IOC.esc(c.date)}</td><td>${IOC.esc(c.subject)}</td></tr>`).join("") + `</table>`;
  }
});
