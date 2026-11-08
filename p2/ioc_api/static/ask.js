IOC.registerTab({
  id: "ask",
  render(el) {
    el.innerHTML = `<div class="card"><h3>Retrieve / Ask</h3>
      <textarea id="ak-q" placeholder="explain how NoteService.search works"></textarea>
      <div class="row-ctl"><label class="small">k</label><input id="ak-k" type="number" min="1" max="50" value="5" style="width:64px">
      <button class="btn" id="ak-ret">Retrieve</button><button class="btn primary" id="ak-ask">Ask LLM</button>
      <button class="btn" id="ak-new">New conversation</button><span class="small" id="ak-sess"></span></div>
      <div id="ak-out"></div></div>`;
    this.session = null;
    el.querySelector("#ak-ret").onclick = () => this.run(false);
    el.querySelector("#ak-ask").onclick = () => this.run(true);
    el.querySelector("#ak-new").onclick = () => { if (this.session) IOC.api("/ask/session/" + this.session, {method: "DELETE"}); this.session = null; this.el.querySelector("#ak-sess").textContent = ""; this.el.querySelector("#ak-out").innerHTML = ""; };
    el.querySelector("#ak-q").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) this.run(true); });
  },
  sources(chunks) {
    return `<h3 style="margin-top:14px">Sources</h3><div class="small">${chunks.length} chunks, ranked by blended score (vector + BM25)</div>` +
      chunks.map(c => `<details class="src"><summary><span class="tag">${IOC.esc(c.path)}:${c.start_line}</span> ${IOC.esc(c.symbol)}
        &nbsp;score ${c.score.toFixed(2)} <span class="small">(vec ${c.vector_score.toFixed(2)} · bm25 ${c.bm25_score.toFixed(2)})</span></summary><pre>${IOC.esc(c.text)}</pre></details>`).join("");
  },
  async run(ask) {
    const q = this.el.querySelector("#ak-q").value.trim(), k = +this.el.querySelector("#ak-k").value || 5, out = this.el.querySelector("#ak-out");
    if (!q) return;
    const btns = this.el.querySelectorAll("button"); btns.forEach(b => b.disabled = true);
    out.innerHTML = `<div class="small">${ask ? "retrieving + asking the local model…" : "retrieving…"}</div>`;
    try {
      if (!ask) { const d = await IOC.api("/context", {method: "POST", body: {query: q, k}}); out.innerHTML = this.sources(d.chunks); return; }
      const d = await IOC.api("/ask", {method: "POST", body: {question: q, k, session_id: this.session}});
      this.session = d.session_id; this.el.querySelector("#ak-sess").textContent = "session " + d.session_id;
      const modeTag = d.mode.startsWith("symbol") ? `<span class="tag ok">${IOC.esc(d.mode)} · answered from the index</span>` : `<span class="tag">${IOC.esc(d.mode)} · ${IOC.esc(d.model || "")}</span>`;
      out.innerHTML = `<h3>Answer ${modeTag} <span class="small">${d.seconds}s</span></h3><div class="answer">${IOC.esc(d.answer)}</div>` +
        (d.facts && d.facts.lines && d.facts.lines.length ? `<details class="src"><summary>symbol facts given to the model</summary><pre>${IOC.esc(d.facts.lines.join("\n"))}</pre></details>` : "") +
        this.sources(d.sources);
    } catch (e) { out.innerHTML = `<div class="answer" style="border-color:var(--err)">${IOC.esc(e.message)}</div>`; }
    finally { btns.forEach(b => b.disabled = false); }
  }
});
