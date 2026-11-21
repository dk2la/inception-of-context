// The Bonus tab. Loaded only by bonus.app, after the mandatory dashboard script, whose helpers it reuses
// (el, make, badge, post, showMessage, showTab, TABS, attemptCard, renderPatchResult, refreshOverview).
// It adds one tab and leaves the mandatory tabs exactly as they are, so the mandatory part is shown untouched.
(function () {
  // ---------- styles of this tab ----------
  const style = document.createElement("style");
  style.textContent = `
  .bonus-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: 16px; margin-top: 16px; align-items: start; }
  .bonus-col { display: grid; gap: 16px; min-width: 0; }
  @media (max-width: 980px) { .bonus-grid { grid-template-columns: 1fr; } }
  .bonus-card .panel-body { padding: 14px 16px; display: grid; gap: 12px; }
  .bonus-card p.lead { margin: 0; color: var(--text-dim); font-size: 13px; line-height: 1.55; }
  .bonus-chip { font: 600 10.5px var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--warn);
                background: var(--warn-soft); padding: 2px 8px; border-radius: 999px; }
  .bonus-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .bonus-row input[type=text] { flex: 1; min-width: 140px; height: 32px; padding: 0 10px; border-radius: var(--radius-sm);
                                border: 1px solid var(--border); background: var(--bg-sunken); }
  .toggle { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid var(--border);
            border-radius: var(--radius-sm); font-size: 12.5px; color: var(--text-dim); cursor: pointer; user-select: none; }
  .toggle:has(input:checked) { color: var(--text); border-color: var(--accent); background: var(--accent-soft); }
  .diff { margin: 0; padding: 10px 0; font: 12px/1.55 var(--mono); background: var(--code-bg); border-radius: var(--radius-sm); overflow: auto; }
  .diff span { display: block; padding: 0 12px; white-space: pre; }
  .diff .add { background: var(--ok-soft); color: var(--ok); }
  .diff .del { background: var(--fail-soft); color: var(--fail); }
  .diff .hunk { color: var(--accent); }
  .diff .meta { color: var(--text-faint); }
  #bonus-live { list-style: none; margin: 0; padding: 0; max-height: 360px; overflow-y: auto; }
  #bonus-live li { display: grid; grid-template-columns: auto auto 1fr; gap: 10px; align-items: center; padding: 7px 16px; font-size: 13px; }
  #bonus-live li + li { border-top: 1px solid var(--border); }
  #bonus-live .time { font: 12px var(--mono); color: var(--text-faint); }
  .compare { width: 100%; border-collapse: collapse; font-size: 13px; }
  .compare th, .compare td { text-align: left; padding: 8px 10px; border-top: 1px solid var(--border); vertical-align: top; }
  .compare th { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--text-faint); border-top: 0; }
  .compare td:first-child { color: var(--text-dim); white-space: nowrap; }
  .compare .yes { color: var(--ok); }
  .compare .no { color: var(--text-faint); }
  .pr { border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
  .pr-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 14px; background: var(--bg-sunken); border-bottom: 1px solid var(--border); }
  .pr-head h4 { margin: 0; font-size: 15px; flex: 1; min-width: 160px; }
  .pr-head .num { color: var(--text-faint); font-weight: 400; }
  .pr-body { padding: 12px 14px; display: grid; gap: 12px; }
  .pr-body .intent { margin: 0; font-size: 13px; color: var(--text-dim); }
  .pr-checks { display: grid; gap: 6px; font-size: 13px; }
  .pr-checks .check { display: flex; align-items: center; gap: 8px; }
  .pr-checks .ok { color: var(--ok); } .pr-checks .fail { color: var(--fail); }
  .pr-checks pre { margin: 0; padding: 8px 10px; font: 11.5px/1.5 var(--mono); background: var(--code-bg); border-radius: var(--radius-sm); overflow: auto; max-height: 180px; }
  .pr-section { font: 600 11px var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--text-faint); }
  .pr-merge { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 14px; border-top: 1px solid var(--border); }
  .pr-merge .note { flex: 1; min-width: 160px; font-size: 12.5px; color: var(--text-dim); }
  #bonus-pulls { list-style: none; margin: 0; padding: 0; }
  #bonus-pulls li { display: flex; align-items: center; gap: 10px; padding: 8px 16px; font-size: 13px; cursor: pointer; }
  #bonus-pulls li + li { border-top: 1px solid var(--border); }
  #bonus-pulls li:hover { background: var(--bg-sunken); }
  #bonus-pulls .title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  `;
  document.head.append(style);

  // ---------- the tab and its button ----------
  const nav = document.querySelector("nav[role=tablist]");
  const main = document.querySelector("main");
  if (!nav || !main || typeof showTab !== "function") return;

  const tabButton = document.createElement("button");
  tabButton.dataset.tab = "bonus";
  tabButton.setAttribute("role", "tab");
  tabButton.append(el("span", "★ "), "Bonus ", el("kbd", "7"));
  tabButton.onclick = () => showTab("bonus");
  nav.append(tabButton);
  TABS.push("bonus"); // key 7 now opens it, through the mandatory key handler

  function card(title, chip, ...body) {
    const head = make("div", "panel-head", el("h3", title));
    if (chip) head.append(el("span", chip, "bonus-chip"));
    return make("div", "panel bonus-card", head, make("div", "panel-body", ...body));
  }

  function lead(text) {
    return el("p", text, "lead");
  }

  function toggle(id, label, checked) {
    const input = Object.assign(document.createElement("input"), {type: "checkbox", id, checked});
    const box = make("label", "toggle", input);
    box.append(label);
    return box;
  }

  // Reindex
  const reindexButton = el("button", "Reindex now", "btn primary");
  reindexButton.id = "bonus-reindex";
  const reindexResult = el("span", "", "muted");
  const reindexCard = card("Reindex on demand", "POST /bonus/reindex",
    lead("Reads the whole Target Project again and makes the Index match it. Useful when the Watcher missed an event."),
    make("div", "bonus-row", reindexButton, reindexResult));

  // Bonus patch
  const intent = document.createElement("textarea");
  intent.id = "bonus-intent";
  intent.rows = 3;
  intent.placeholder = "Describe the change, e.g. add a power function to Calculator";
  const k = Object.assign(document.createElement("input"), {type: "number", id: "bonus-k", min: 1, value: 5});
  const attempts = Object.assign(document.createElement("input"), {type: "number", id: "bonus-attempts", min: 1, max: 3, value: 3});
  const runButton = el("button", "Run bonus patch", "btn primary");
  runButton.id = "bonus-run";
  const composerBar = make("div", "composer-bar",
    make("label", "field", el("span", "k"), k), make("label", "field", el("span", "max attempts"), attempts),
    toggle("bonus-dry", "dry run (diff only)", false), toggle("bonus-pr", "pull request (review, then merge)", false),
    toggle("bonus-git", "git commit", true),
    make("div", "spacer"), runButton);
  composerBar.querySelector(".spacer").style.flex = "1";
  const patchMessage = el("div", "", "message");
  patchMessage.id = "bonus-message";
  const patchResult = make("div", "");
  patchResult.id = "bonus-result";
  const patchCard = card("Patch with dry run, pull request, diff and git commit", "POST /bonus/patch",
    lead("The same Patch Loop as Part 3, plus: a dry run that only shows the diff, a pull request mode where a green " +
         "Patch waits for you to merge it, a visual diff of what was applied, and a git commit whose message the model writes."),
    make("div", "panel composer", intent, composerBar), patchMessage, patchResult);

  // Live validation
  const live = document.createElement("ol");
  live.id = "bonus-live";
  const liveEmpty = el("div", "Nothing yet. Run a bonus patch: every Attempt and its validation appear here live.", "empty");
  const liveCard = make("div", "panel bonus-card",
    make("div", "panel-head", el("h3", "Live validation"), el("span", "SSE · /bonus/events", "bonus-chip")), live, liveEmpty);

  // Pull requests
  const pullList = document.createElement("ul");
  pullList.id = "bonus-pulls";
  const pullEmpty = el("div", "No pull requests yet. Turn on \u201cpull request\u201d and run a bonus patch.", "empty");
  const pullsCard = make("div", "panel bonus-card",
    make("div", "panel-head", el("h3", "Pull requests"), el("span", "GET /bonus/pulls", "bonus-chip")), pullList, pullEmpty);

  // Docker watch
  const service = Object.assign(document.createElement("input"), {type: "text", id: "bonus-service", placeholder: "container name"});
  const dockerIntent = Object.assign(document.createElement("input"), {type: "text", id: "bonus-docker-intent",
    value: "fix the crash shown in the logs"});
  const watchButton = el("button", "Watch", "btn");
  const stopButton = el("button", "Stop", "btn ghost");
  const dockerStatus = badge("not watching");
  const dockerCard = card("Docker log watch", "POST /bonus/docker/watch",
    lead("Follows one container's logs; the first traceback runs the Patch Loop once (one attempt, no commit)."),
    make("div", "bonus-row", service), make("div", "bonus-row", dockerIntent),
    make("div", "bonus-row", watchButton, stopButton, dockerStatus));

  // Patch vs bonus patch
  const rows = [
    ["Route", "POST /patch", "POST /bonus/patch"],
    ["Loop", "up to 3 attempts, rollback", "the same loop, the same lock"],
    ["Sanity checks", "yes", "yes, in the dry run too"],
    ["Dry run", "no", "yes: diff only, disk untouched"],
    ["Visual diff", "no (full new file)", "yes, unified diff per file"],
    ["Live status", "no (one answer at the end)", "yes, each attempt over SSE"],
    ["Pull request", "no (a green Patch is applied)", "yes: checks run, then you merge or close"],
    ["Git commit", "no", "yes, message written by the model"],
  ];
  const table = make("table", "compare", make("thead", "", make("tr", "", el("th", ""), el("th", "Part 3 patch"), el("th", "Bonus patch"))));
  const tbody = make("tbody", "");
  for (const [name, a, b] of rows) {
    tbody.append(make("tr", "", el("td", name), el("td", a, a.startsWith("no") ? "no" : ""), el("td", b, "yes")));
  }
  table.append(tbody);
  const compareCard = card("Part 3 patch vs bonus patch", "", table);

  const section = make("section", "tab",
    make("div", "page-head", make("div", "", el("h2", "Bonus"),
      el("p", "Chapter VII extras, served only by bonus.app. The mandatory tabs are unchanged."))),
    make("div", "bonus-grid", make("div", "bonus-col", patchCard, compareCard),
      make("div", "bonus-col", pullsCard, liveCard, reindexCard, dockerCard)));
  section.id = "tab-bonus";
  section.setAttribute("role", "tabpanel");
  section.hidden = true;
  main.append(section);

  // ---------- behaviour ----------

  reindexButton.onclick = async () => {
    reindexButton.disabled = true;
    reindexResult.textContent = "reindexing…";
    const started = Date.now();
    try {
      const body = await post("/bonus/reindex", {});
      reindexResult.textContent = `${body.chunks} chunks · ${((Date.now() - started) / 1000).toFixed(1)}s`;
      if (typeof refreshOverview === "function") refreshOverview();
    } catch (error) {
      reindexResult.textContent = "Reindex failed: " + error.message;
    } finally {
      reindexButton.disabled = false;
    }
  };

  function liveLine(event) {
    const detail = event.detail || {};
    if (event.type === "attempt") {
      const validation = detail.validation_ok === true ? "validation green" :
        detail.validation_ok === false ? "validation red" : "no validation";
      return ["attempt " + detail.number + " · " + (detail.ok ? "passed" : "failed") + " · " + validation, detail.ok ? "ok" : "fail"];
    }
    if (event.type === "attempt_started") return ["attempt " + detail.number + " started · " + detail.step, "accent"];
    if (event.type === "git") return [detail.ok ? "committed: " + detail.message : "git: " + detail.error, detail.ok ? "ok" : "warn"];
    if (event.type === "dry_run") return ["dry run · " + (detail.files || []).join(", "), "accent"];
    if (event.type === "docker_crash") return ["docker crash · " + detail.service, "fail"];
    if (event.type === "docker_watch") return ["watching docker logs · " + detail.service, "accent"];
    if (event.type === "started") return ["started · " + detail.intent + (detail.dry_run ? " (dry run)" : detail.pull_request ? " (pull request)" : ""), "accent"];
    if (event.type === "pull_opened") return ["opened #" + detail.number + " · " + detail.title, "accent"];
    if (event.type === "pull_merged") return ["merged #" + detail.number + " · " + detail.title, "ok"];
    if (event.type === "pull_closed") return ["closed #" + detail.number + " · " + detail.title, ""];
    if (event.type === "pull_conflict") return ["conflict #" + detail.number + " · " + (detail.files || []).join(", "), "warn"];
    if (event.type === "pull_failed") return ["merge of #" + detail.number + " failed validation, rolled back", "fail"];
    if (event.type === "finished") return ["finished · " + detail.status, ["success", "dry_run", "open"].includes(detail.status) ? "ok" : "fail"];
    return [event.type, ""];
  }

  const source = new EventSource("/bonus/events");
  source.onmessage = (message) => {
    const event = JSON.parse(message.data);
    const [text, tone] = liveLine(event);
    const time = event.time ? new Date(event.time * 1000).toLocaleTimeString() : "";
    live.prepend(make("li", "", el("span", time, "time"), badge(event.type, tone), el("span", text)));
    liveEmpty.hidden = true;
    if (live.children.length > 60) live.lastElementChild.remove();
  };

  // A unified diff with added lines green, removed lines red, hunk headers in the accent colour.
  function diffView(text) {
    const pre = make("pre", "diff");
    for (const line of (text || "(no textual change)").split("\n")) {
      const kind = line.startsWith("+++") || line.startsWith("---") ? "meta" : line.startsWith("@@") ? "hunk" :
        line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "";
      pre.append(el("span", line || " ", kind));
    }
    return pre;
  }

  function fileBlocks(container, files) {
    for (const file of files || []) {
      const block = make("details", "patch-file", make("summary", "", el("span", file.op + " "), el("code", file.path)), diffView(file.diff));
      block.open = true;
      container.append(block);
    }
  }

  const PR_TONE = {open: "accent", merged: "ok", closed: ""};

  // One pull request, drawn like a code-review page: title, checks, files changed, then Merge / Close.
  function renderPull(container, pull, note) {
    const head = make("div", "pr-head", badge(pull.state, PR_TONE[pull.state]),
      make("h4", "", el("span", "#" + pull.number + " ", "num"), pull.title));
    const checks = make("div", "pr-checks",
      make("div", "check", el("span", pull.checks.sanity ? "✓" : "✗", pull.checks.sanity ? "ok" : "fail"), "Sanity checks"),
      make("div", "check", el("span", pull.checks.validation ? "✓" : "✗", pull.checks.validation ? "ok" : "fail"),
        "Validation Command · passed on attempt " + pull.attempts));
    if (pull.checks.log) {
      const log = make("details", "", el("summary", "validation log"), el("pre", pull.checks.log));
      checks.append(log);
    }
    const files = make("div", "");
    fileBlocks(files, pull.files);
    const body = make("div", "pr-body", el("p", "Intent: " + pull.intent, "intent"),
      el("div", "Checks", "pr-section"), checks,
      el("div", "Files changed · " + (pull.files || []).length, "pr-section"), files);
    const box = make("div", "pr", head, body);
    if (pull.state === "open") {
      const mergeButton = el("button", "Merge", "btn primary");
      const closeButton = el("button", "Close", "btn ghost");
      const git = toggle("bonus-pr-git-" + pull.number, "git commit", document.getElementById("bonus-git").checked);
      const footer = make("div", "pr-merge",
        el("span", note || "Nothing is written yet. Merge applies exactly this Patch and runs the Validation Command again.", "note"),
        git, closeButton, mergeButton);
      mergeButton.onclick = () => mergePull(pull.number, git.querySelector("input").checked, footer);
      closeButton.onclick = () => closePull(pull.number, footer);
      box.append(footer);
    } else if (pull.state === "merged") {
      const gitInfo = pull.merge && pull.merge.git;
      box.append(make("div", "pr-merge", el("span", gitInfo ? (gitInfo.ok ? "Merged and committed: " + gitInfo.message :
        "Merged; commit skipped: " + gitInfo.error) : "Merged, not committed.", "note")));
    } else {
      box.append(make("div", "pr-merge", el("span", "Closed. Nothing was written.", "note")));
    }
    container.replaceChildren(box);
  }

  async function mergePull(number, gitCommit, footer) {
    footer.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    showMessage("bonus-message", "Merging #" + number + "…", false, true);
    const started = Date.now();
    try {
      const data = await post("/bonus/pulls/" + number + "/merge", {git_commit: gitCommit});
      const seconds = Math.round((Date.now() - started) / 1000);
      if (data.status === "success") {
        renderPull(patchResult, data.pull);
        showMessage("bonus-message", "Merged #" + number + " · " + seconds + "s");
        if (typeof dinoJump === "function") dinoJump();
      } else {
        renderPull(patchResult, data.pull, data.status === "conflict" ? "Conflict: " + data.error :
          data.status === "failed" ? "Merge failed validation and was rolled back. " + data.error : data.error);
        showMessage("bonus-message", data.error, true);
      }
      if (typeof refreshOverview === "function") refreshOverview();
    } catch (error) {
      showMessage("bonus-message", "Merge failed: " + error.message, true);
      footer.querySelectorAll("button").forEach((button) => { button.disabled = false; });
    }
    loadPulls();
  }

  async function closePull(number, footer) {
    footer.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    try {
      renderPull(patchResult, await post("/bonus/pulls/" + number + "/close", {}));
      showMessage("bonus-message", "Closed #" + number + ". Nothing was written.");
    } catch (error) {
      showMessage("bonus-message", "Close failed: " + error.message, true);
    }
    loadPulls();
  }

  async function loadPulls() {
    try {
      const response = await fetch("/bonus/pulls");
      const pulls = await response.json();
      pullList.replaceChildren(...pulls.map((pull) => {
        const item = make("li", "", badge(pull.state, PR_TONE[pull.state]), el("span", "#" + pull.number + " " + pull.title, "title"),
          el("span", (pull.files || []).length + " files", "muted"));
        item.onclick = () => { renderPull(patchResult, pull); showMessage("bonus-message", ""); };
        return item;
      }));
      pullEmpty.hidden = pulls.length > 0;
    } catch (error) {
      pullEmpty.hidden = false;
    }
  }

  function renderBonus(container, data, seconds) {
    if (data.status === "open" && data.pull) {
      renderPull(container, data.pull);
      return;
    }
    if (!data.dry_run && typeof renderPatchResult === "function") {
      renderPatchResult(container, data, seconds);
    } else {
      const ok = data.status === "dry_run";
      container.replaceChildren(make("div", "banner " + (ok ? "ok" : "fail"), el("div", ok ? "✓" : "!", "icon"),
        make("div", "", el("strong", ok ? "Dry run: this is what would change" : "Refused"),
          el("span", "Nothing was written · " + seconds + "s"))));
      for (const attempt of data.attempts || []) {
        if (typeof attemptCard === "function") container.append(attemptCard(attempt));
      }
    }
    if (data.git) {
      container.append(make("div", "bonus-row", badge("git", data.git.ok ? "ok" : "warn"),
        el("span", data.git.ok ? "committed: " + data.git.message : "commit skipped: " + data.git.error)));
    }
    fileBlocks(container, data.diffs);
  }

  async function runBonusPatch() {
    const text = intent.value.trim();
    if (text === "") {
      showMessage("bonus-message", "Type an Intent first.", true);
      return;
    }
    const dry = document.getElementById("bonus-dry").checked;
    const git = document.getElementById("bonus-git").checked;
    const pr = document.getElementById("bonus-pr").checked;
    const body = {intent: text, k: Math.max(1, Number(k.value) || 5),
                  max_attempts: Math.min(3, Math.max(1, Number(attempts.value) || 3)), dry_run: dry, git_commit: git,
                  pull_request: pr};
    runButton.disabled = true;
    const started = Date.now();
    const tick = () => showMessage("bonus-message", `${dry ? "Dry run" : pr ? "Running the checks for a pull request" : "Running the loop"}… ${Math.round((Date.now() - started) / 1000)}s`, false, true);
    tick();
    const timer = setInterval(tick, 1000);
    try {
      const data = await post("/bonus/patch", body);
      renderBonus(patchResult, data, Math.round((Date.now() - started) / 1000));
      showMessage("bonus-message", "");
      if (data.status === "success" && typeof dinoJump === "function") dinoJump();
      if (data.pull) loadPulls();
    } catch (error) {
      patchResult.replaceChildren();
      showMessage("bonus-message", "Request failed: " + error.message, true);
    } finally {
      clearInterval(timer);
      runButton.disabled = false;
    }
  }

  runButton.onclick = runBonusPatch;
  // A dry run writes nothing and a pull request waits for Merge, so only one of them can be on.
  const dryBox = document.getElementById("bonus-dry");
  const prBox = document.getElementById("bonus-pr");
  dryBox.onchange = () => { if (dryBox.checked) prBox.checked = false; };
  prBox.onchange = () => { if (prBox.checked) dryBox.checked = false; };
  loadPulls();
  intent.onkeydown = (event) => { if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) runBonusPatch(); };

  function showDocker(status) {
    dockerStatus.textContent = status.error ? status.error : status.running ? "watching " + status.service : "not watching";
    dockerStatus.className = "badge " + (status.error ? "fail" : status.running ? "ok" : "");
  }
  watchButton.onclick = async () => {
    if (!service.value.trim()) { showDocker({error: "type a container name"}); return; }
    try { showDocker(await post("/bonus/docker/watch", {service: service.value.trim(), intent: dockerIntent.value.trim()})); }
    catch (error) { showDocker({error: error.message}); }
  };
  stopButton.onclick = async () => {
    try { showDocker(await post("/bonus/docker/stop", {})); } catch (error) { showDocker({error: error.message}); }
  };

  if (location.hash === "#bonus") showTab("bonus");
})();
