// Bonus controls. Loaded only by bonus.app, after the mandatory dashboard script.
(function () {
  // debug: runs after the mandatory dashboard script, and only when bonus.app injected this file.
  // overview gains a Reindex button. The patch form gains "dry run" and "git commit" (checked).
  // a Live validation list listens to GET /bonus/events. #patch-run calls runBonusPatch.
  const head = document.querySelector("#tab-overview .page-head");
  if (head) {
    const button = document.createElement("button");
    button.className = "btn";
    button.id = "bonus-reindex";
    button.textContent = "Reindex";
    button.onclick = reindexNow;
    head.append(button);
  }

  const bar = document.querySelector("#patch-form .composer-bar");
  if (bar) {
    const dry = document.createElement("label");
    dry.className = "field";
    dry.append(Object.assign(document.createElement("input"), {type: "checkbox", id: "bonus-dry"}));
    dry.append(" dry run");
    const git = document.createElement("label");
    git.className = "field";
    git.append(Object.assign(document.createElement("input"), {type: "checkbox", id: "bonus-git", checked: true}));
    git.append(" git commit");
    bar.prepend(git);
    bar.prepend(dry);
  }

  const patchForm = document.getElementById("patch-form");
  if (patchForm) {
    const live = document.createElement("div");
    live.className = "panel";
    live.id = "bonus-live-panel";
    const title = document.createElement("div");
    title.className = "panel-head";
    const heading = document.createElement("h3");
    heading.textContent = "Live validation";
    title.append(heading);
    const list = document.createElement("ol");
    list.id = "bonus-live";
    live.append(title, list);
    patchForm.append(live);
    listen();
  }

  const run = document.getElementById("patch-run");
  if (run) run.onclick = runBonusPatch;
  const intent = document.getElementById("intent");
  if (intent) {
    intent.onkeydown = (event) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) runBonusPatch();
    };
  }

  async function reindexNow() {
    // debug: POST /bonus/reindex {}. body.chunks is the Chunk count.
    // the button text becomes "Reindex (N)" and refreshOverview() reloads the overview.
    // a failed request sets the button text to "Reindex failed".
    const button = document.getElementById("bonus-reindex");
    button.disabled = true;
    try {
      const body = await post("/bonus/reindex", {});
      button.textContent = "Reindex (" + body.chunks + ")";
      if (typeof refreshOverview === "function") refreshOverview();
    } catch (error) {
      button.textContent = "Reindex failed";
    } finally {
      button.disabled = false;
    }
  }

  function listen() {
    // debug: EventSource("/bonus/events"). Each "data:" line is parsed and prepended to #bonus-live.
    // ": waiting" heartbeats are not onmessage events. The list keeps the newest 40 lines.
    const source = new EventSource("/bonus/events");
    const list = document.getElementById("bonus-live");
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      const item = document.createElement("li");
      item.textContent = liveLine(event);
      list.prepend(item);
      if (list.children.length > 40) list.lastElementChild.remove();
    };
  }

  function liveLine(event) {
    // debug: {type: "attempt", detail: {number: 1, ok: false, validation_ok: false}}
    //   return == "attempt 1 · failed · validation red"
    // {type: "git", detail: {ok: true, message: "Add a power method to Calculator"}}
    //   return == "committed: Add a power method to Calculator"
    // {type: "dry_run", detail: {files: ["calculator/core.py"]}} -> "dry run · calculator/core.py"
    // {type: "docker_crash", detail: {service: "calculator"}} -> "docker crash · calculator"
    // {type: "finished", detail: {status: "success"}} -> "finished · success"
    const detail = event.detail || {};
    if (event.type === "attempt") {
      const validation = detail.validation_ok === true ? "validation green" :
        detail.validation_ok === false ? "validation red" : "no validation";
      return "attempt " + detail.number + " · " + (detail.ok ? "passed" : "failed") + " · " + validation;
    }
    if (event.type === "git") return detail.ok ? "committed: " + detail.message : "git: " + detail.error;
    if (event.type === "dry_run") return "dry run · " + (detail.files || []).join(", ");
    if (event.type === "docker_crash") return "docker crash · " + detail.service;
    return event.type + (detail.status ? " · " + detail.status : "");
  }

  async function runBonusPatch() {
    // debug: intent "add a power function to Calculator", k 5, max attempts 3
    // dry checkbox off, git checkbox on.
    // POST /bonus/patch {intent, k: 5, max_attempts: 3, dry_run: false, git_commit: true}
    // empty intent: showMessage "Type an Intent first." and return before the request.
    // k and max_attempts are clamped to 1.. and 1..3.
    const intentBox = document.getElementById("intent");
    const intentText = intentBox.value.trim();
    if (intentText === "") {
      showMessage("patch-message", "Type an Intent first.", true);
      return;
    }
    const k = Math.max(1, Number(document.getElementById("patch-k").value) || 5);
    const maxAttempts = Math.min(3, Math.max(1, Number(document.getElementById("patch-attempts").value) || 3));
    const dry = document.getElementById("bonus-dry").checked;
    const git = document.getElementById("bonus-git").checked;
    const button = document.getElementById("patch-run");
    const result = document.getElementById("patch-result");
    button.disabled = true;
    const started = Date.now();
    showMessage("patch-message", dry ? "Dry run…" : "Running the loop…", false, true);
    try {
      const data = await post("/bonus/patch", {intent: intentText, k, max_attempts: maxAttempts, dry_run: dry, git_commit: git});
      const seconds = Math.round((Date.now() - started) / 1000);
      renderBonus(result, data, seconds);
      showMessage("patch-message", "");
    } catch (error) {
      result.replaceChildren();
      showMessage("patch-message", "Request failed: " + error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function renderBonus(container, data, seconds) {
    // debug: a real success uses renderPatchResult, then a "Git commit: ..." line and a <details> per diff.
    // data.dry_run true: banner "Dry run", "Nothing was written · 4s", then the diff of calculator/core.py.
    // data.status "refused": banner "Refused". data.git.ok false: "Git commit skipped: ...".
    if (!data.dry_run && typeof renderPatchResult === "function") {
      renderPatchResult(container, data, seconds);
    } else {
      container.replaceChildren();
      const banner = document.createElement("div");
      banner.className = "banner " + (data.status === "dry_run" ? "ok" : "fail");
      const strong = document.createElement("strong");
      strong.textContent = data.status === "dry_run" ? "Dry run" : "Refused";
      const note = document.createElement("span");
      note.textContent = "Nothing was written · " + seconds + "s";
      const text = document.createElement("div");
      text.append(strong, note);
      banner.append(text);
      container.append(banner);
      for (const attempt of data.attempts || []) {
        if (typeof attemptCard === "function") container.append(attemptCard(attempt));
      }
    }
    if (data.git) {
      const line = document.createElement("p");
      line.textContent = data.git.ok ? "Git commit: " + data.git.message : "Git commit skipped: " + data.git.error;
      container.append(line);
    }
    for (const file of data.diffs || []) {
      const block = document.createElement("details");
      block.className = "patch-file";
      const summary = document.createElement("summary");
      summary.textContent = "diff " + file.path;
      const pre = document.createElement("pre");
      pre.textContent = file.diff || "(no textual change)";
      block.append(summary, pre);
      container.append(block);
    }
  }
})();
