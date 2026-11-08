IOC.registerTab({
  id: "patch",
  render(el) {
    el.innerHTML = `<div class="card"><h3>Patch loop</h3>
      <div class="small" style="margin-bottom:8px">The coder model produces a JSON patch, IoC sanity-checks it, applies it atomically, runs the validation command from ioc.config.yml, and rolls back on failure.</div>
      <textarea id="pl-intent" placeholder="add a function whisper(name) in main.py that returns the greeting in lowercase"></textarea>
      <div class="row-ctl"><label class="small">k</label><input id="pl-k" type="number" min="1" max="50" value="5" style="width:64px">
        <label class="small">max attempts</label><input id="pl-max" type="number" min="1" max="3" value="3" style="width:56px">
        <button class="btn primary" id="pl-run">Run loop</button><button class="btn" id="pl-gen">Generate only</button><span id="pl-status"></span></div>
      <div id="pl-final"></div><div id="pl-steps"></div></div>
      <div class="card"><h3>History</h3><div id="pl-hist" class="small">no runs yet</div></div>`;
    el.querySelector("#pl-run").onclick = () => this.run();
    el.querySelector("#pl-gen").onclick = () => this.generate();
  },
  onShow() { this.history(); },
  esc: s => IOC.esc(s),
  stepHtml(s) {
    const tag = s.ok ? `<span class="tag ok">ok</span>` : `<span class="tag err">failed</span>`;
    let body = "";
    if (s.stage === "generate") body = s.ok ? `${this.esc(s.summary)} · ${this.esc((s.files || []).join(", "))} · ${s.seconds}s` : this.esc(s.error);
    if (s.stage === "sanity") body = s.ok ? "all checks passed" : `<pre class="json">${this.esc((s.errors || []).join("\n"))}</pre>`;
    if (s.stage === "apply") body = s.ok ? "written atomically: " + this.esc((s.touched || []).join(", ")) : this.esc(s.error);
    if (s.stage === "validate") body = `${this.esc((s.commands || []).join(" ; "))} · exit ${s.exit_code} · ${s.seconds}s` + (s.ok ? "" : `<pre class="json">${this.esc(s.output)}</pre>`);
    if (s.stage === "rollback") body = `restored ${this.esc((s.restored || []).join(", ") || "nothing")} · verified=${s.verified}`;
    return `<div style="margin:4px 0"><span class="tag">attempt ${s.attempt}</span> <b>${s.stage}</b> ${tag} ${body}</div>`;
  },
  finalHtml(r) {
    const cls = r.status === "success" ? "ok" : r.status === "error" ? "err" : "warn";
    const label = r.status === "success" ? `SUCCESS in ${r.attempt_count} attempt(s)` : r.status === "rolled_back" ? `ROLLED BACK after ${r.attempt_count} attempt(s) · project restored byte-for-byte: ${r.rollback_verified}` : `ERROR: ${r.error || ""}`;
    let html = `<div class="row-ctl"><span class="tag ${cls}">${this.esc(label)}</span><span class="small">${r.seconds}s</span></div>`;
    const patch = r.patch || (r.attempts.length && r.attempts[r.attempts.length - 1].patch);
    if (patch) html += `<details class="src" open><summary>${r.patch ? "Final patch" : "Last proposed patch (not applied)"}</summary><pre class="json">${this.esc(JSON.stringify(patch, null, 2))}</pre></details>`;
    return html;
  },
  async run() {
    const intent = this.el.querySelector("#pl-intent").value.trim(); if (!intent) return;
    const k = +this.el.querySelector("#pl-k").value || 5, max = +this.el.querySelector("#pl-max").value || 3;
    const steps = this.el.querySelector("#pl-steps"), fin = this.el.querySelector("#pl-final"), st = this.el.querySelector("#pl-status");
    steps.innerHTML = ""; fin.innerHTML = ""; st.innerHTML = `<span class="small">running…</span>`;
    const btns = this.el.querySelectorAll("button"); btns.forEach(b => b.disabled = true);
    try {
      const resp = await fetch("/patch/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({intent, k, max_attempts: max, stream: true})});
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.status);
      const reader = resp.body.getReader(), dec = new TextDecoder(); let buf = "";
      for (;;) {
        const {value, done} = await reader.read(); if (done) break;
        buf += dec.decode(value, {stream: true}); let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i); buf = buf.slice(i + 1); if (!line.trim()) continue;
          const ev = JSON.parse(line);
          if (ev.event === "attempt") st.innerHTML = `<span class="small">attempt ${ev.attempt}: asking the coder model…</span>`;
          if (ev.event === "step") steps.insertAdjacentHTML("beforeend", this.stepHtml(ev));
          if (ev.event === "done") { fin.innerHTML = this.finalHtml(ev.result); st.innerHTML = ""; }
          if (ev.event === "error") { fin.innerHTML = `<span class="tag err">${this.esc(ev.error)}</span>`; st.innerHTML = ""; }
        }
      }
    } catch (e) { fin.innerHTML = `<span class="tag err">${this.esc(e.message)}</span>`; st.innerHTML = ""; }
    finally { btns.forEach(b => b.disabled = false); this.history(); }
  },
  async generate() {
    const intent = this.el.querySelector("#pl-intent").value.trim(); if (!intent) return;
    const fin = this.el.querySelector("#pl-final"); fin.innerHTML = `<span class="small">generating (nothing will be written)…</span>`;
    try {
      const d = await IOC.api("/patch/generate", {method: "POST", body: {intent, k: +this.el.querySelector("#pl-k").value || 5}});
      fin.innerHTML = `<div class="row-ctl"><span class="tag ${d.ok ? "ok" : "err"}">${d.ok ? "sanity checks passed (dry, not applied)" : "refused at " + this.esc(d.stage)}</span></div>` +
        (d.violations && d.violations.length ? `<pre class="json">${this.esc(d.violations.join("\n"))}</pre>` : "") + (d.error ? `<pre class="json">${this.esc(d.error)}</pre>` : "") +
        (d.patch ? `<pre class="json">${this.esc(JSON.stringify(d.patch, null, 2))}</pre>` : "");
    } catch (e) { fin.innerHTML = `<span class="tag err">${this.esc(e.message)}</span>`; }
  },
  async history() {
    const h = await IOC.api("/patch/history"); const el = this.el.querySelector("#pl-hist");
    if (!h.runs.length) { el.textContent = "no runs yet"; return; }
    el.innerHTML = `<table class="t"><tr><th>status</th><th>intent</th><th>attempts</th><th>time</th></tr>` + h.runs.map(r =>
      `<tr><td><span class="tag ${r.status === "success" ? "ok" : "err"}">${this.esc(r.status)}</span></td><td>${this.esc(r.intent)}</td><td>${r.attempt_count}</td><td>${r.seconds}s</td></tr>`).join("") + `</table>`;
  }
});
