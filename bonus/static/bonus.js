(function () {
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
  .docker-log { margin: 0; padding: 8px 0; max-height: 260px; overflow: auto; font: 12px/1.5 var(--mono);
                background: var(--code-bg); border-radius: var(--radius-sm); }
  .docker-log span { display: block; padding: 0 12px; white-space: pre-wrap; word-break: break-word; }
  .docker-log .tb { background: var(--fail-soft); color: var(--fail); }
  .docker-log .mark { color: var(--accent); font-weight: 600; padding-top: 4px; padding-bottom: 4px; }
  .docker-log .mark.ok { background: var(--ok-soft); color: var(--ok); }
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
  #bonus-pulls { display: grid; }
  #bonus-pulls .pr-group { padding: 10px 16px 6px; font: 600 11px var(--mono); letter-spacing: .06em; text-transform: uppercase;
                           color: var(--text-faint); border-top: 1px solid var(--border); }
  #bonus-pulls .pr-group:first-child { border-top: 0; }
  .pr-item { border-top: 1px solid var(--border); }
  .pr-item > summary { display: flex; align-items: center; gap: 10px; padding: 9px 16px; font-size: 13px; cursor: pointer; list-style: none; }
  .pr-item > summary::-webkit-details-marker { display: none; }
  .pr-item > summary::before { content: "▸"; color: var(--text-faint); transition: transform .15s; }
  .pr-item[open] > summary::before { transform: rotate(90deg); }
  .pr-item > summary:hover { background: var(--bg-sunken); }
  .pr-item .title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pr-item .stat-add { color: var(--ok); font: 12px var(--mono); } .pr-item .stat-del { color: var(--fail); font: 12px var(--mono); }
  .pr-item .when { color: var(--text-faint); font-size: 12px; white-space: nowrap; }
  .pr-item > .pr { margin: 0 16px 14px; }
  `;
  document.head.append(style);

  const nav = document.querySelector("nav[role=tablist]");
  const main = document.querySelector("main");
  if (!nav || !main || typeof showTab !== "function") return;

  const tabButton = document.createElement("button");
  tabButton.dataset.tab = "bonus";
  tabButton.setAttribute("role", "tab");
  tabButton.append(el("span", "★ "), "Bonus ", el("kbd", "7"));
  tabButton.onclick = () => showTab("bonus");
  nav.append(tabButton);
  TABS.push("bonus");

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

  const reindexButton = el("button", "Reindex now", "btn primary");
  reindexButton.id = "bonus-reindex";
  const reindexResult = el("span", "", "muted");
  const reindexCard = card("Reindex on demand", "POST /bonus/reindex",
    lead("Reads the whole Target Project again and makes the Index match it. Useful when the Watcher missed an event."),
    make("div", "bonus-row", reindexButton, reindexResult));

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

  const live = document.createElement("ol");
  live.id = "bonus-live";
  const liveEmpty = el("div", "Nothing yet. Run a bonus patch: every Attempt and its validation appear here live.", "empty");
  const liveCard = make("div", "panel bonus-card",
    make("div", "panel-head", el("h3", "Live validation"), el("span", "SSE · /bonus/events", "bonus-chip")), live, liveEmpty);

  const pullList = document.createElement("ul");
  pullList.id = "bonus-pulls";
  const pullEmpty = el("div", "No pull requests yet. Turn on \u201cpull request\u201d and run a bonus patch.", "empty");
  const pullsCard = make("div", "panel bonus-card",
    make("div", "panel-head", el("h3", "Pull requests"), el("span", "GET /bonus/pulls", "bonus-chip")), pullList, pullEmpty);
  const expandedPulls = new Set();
  const pullNotes = {};

  const service = Object.assign(document.createElement("input"), {type: "text", id: "bonus-service", placeholder: "container name",
    value: "calculator"});
  const dockerIntent = Object.assign(document.createElement("input"), {type: "text", id: "bonus-docker-intent",
    value: "fix the crash shown in the logs"});
  const watchButton = el("button", "Watch", "btn");
  const stopButton = el("button", "Stop", "btn ghost");
  const demoButton = el("button", "Start demo crash", "btn primary");
  const resetButton = el("button", "Reset demo", "btn ghost");
  resetButton.title = "Put target/ back as it was before the first demo run (undoes the fix)";
  demoButton.title = "Same as make crash: runs target/ as container \u201ccalculator\u201d; its last job crashes";
  const dockerStatus = badge("not watching");
  const dockerLog = make("pre", "docker-log");
  dockerLog.id = "bonus-docker-log";
  dockerLog.append(el("span", "No log yet. Run `make crash`, then Watch \u201ccalculator\u201d.", "muted"));
  let inTraceback = false;
  function logLine(text) {
    if (dockerLog.querySelector(".muted")) dockerLog.replaceChildren();
    if (text.includes("Traceback (most recent call last)")) inTraceback = true;
    const exceptionLine = inTraceback && !text.includes("Traceback") && !/^\s/.test(text);
    dockerLog.append(el("span", text || " ", inTraceback ? "tb" : ""));
    if (exceptionLine) inTraceback = false;
    if (dockerLog.children.length > 300) dockerLog.firstElementChild.remove();
    dockerLog.scrollTop = dockerLog.scrollHeight;
  }
  function logMark(text, tone = "") {
    if (dockerLog.querySelector(".muted")) dockerLog.replaceChildren();
    dockerLog.append(el("span", "\u2014 " + text + " \u2014", "mark " + tone));
    dockerLog.scrollTop = dockerLog.scrollHeight;
  }
  const dockerCard = card("Docker log watch", "POST /bonus/docker/watch",
    lead("Follows one container's logs. The first traceback runs the Patch Loop once (up to 3 attempts, no commit), " +
         "with the traceback added to the Intent so the model sees what crashed."),
    make("div", "bonus-row", service), make("div", "bonus-row", dockerIntent),
    make("div", "bonus-row", demoButton, watchButton, stopButton, resetButton, dockerStatus), dockerLog);

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
    make("div", "bonus-grid", make("div", "bonus-col", patchCard, pullsCard, compareCard),
      make("div", "bonus-col", liveCard, reindexCard, dockerCard)));
  section.id = "tab-bonus";
  section.setAttribute("role", "tabpanel");
  section.hidden = true;
  main.append(section);

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
    if (event.type === "docker_rerun") return ["fixed: running " + detail.service + " again on the patched code", "accent"];
    if (event.type === "docker_verified") return [detail.ok ? "verified · " + detail.service + " runs clean" :
      "still crashing · " + detail.service + " (exit " + detail.exit_code + ")", detail.ok ? "ok" : "fail"];
    if (event.type === "docker_crash") return ["docker crash · " + detail.service + " · " + (detail.line || ""), "fail"];
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
    if (event.type === "docker_log") { logLine(event.detail.line); return; }
    if (event.type === "docker_rerun") { logMark("rerun after the fix"); inTraceback = false; }
    if (event.type === "docker_verified") logMark(event.detail.ok ? "\u2713 verified: no crash" : "\u2717 still crashing", event.detail.ok ? "ok" : "tb");
    const [text, tone] = liveLine(event);
    const time = event.time ? new Date(event.time * 1000).toLocaleTimeString() : "";
    live.prepend(make("li", "", el("span", time, "time"), badge(event.type, tone), el("span", text)));
    liveEmpty.hidden = true;
    if (live.children.length > 60) live.lastElementChild.remove();
  };

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

  function pullBox(pull, note) {
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
      const when = pull.merge && pull.merge.at ? " · " + new Date(pull.merge.at * 1000).toLocaleString() : "";
      box.append(make("div", "pr-merge", el("span", (gitInfo ? (gitInfo.ok ? "Merged and committed: " + gitInfo.message :
        "Merged; commit skipped: " + gitInfo.error) : "Merged, not committed.") + when, "note")));
    } else {
      const when = pull.closed_at ? " · " + new Date(pull.closed_at * 1000).toLocaleString() : "";
      box.append(make("div", "pr-merge", el("span", "Closed. Nothing was written." + when, "note")));
    }
    return box;
  }

  function diffStat(files) {
    let added = 0, removed = 0;
    for (const file of files || []) {
      for (const line of (file.diff || "").split("\n")) {
        if (line.startsWith("+") && !line.startsWith("+++")) added++;
        else if (line.startsWith("-") && !line.startsWith("---")) removed++;
      }
    }
    return [added, removed];
  }

  function pullItem(pull) {
    const [added, removed] = diffStat(pull.files);
    const at = pull.state === "merged" && pull.merge && pull.merge.at ? pull.merge.at : pull.closed_at || pull.created;
    const verb = pull.state === "merged" ? "merged " : pull.state === "closed" ? "closed " : "opened ";
    const item = make("details", "pr-item", make("summary", "", badge(pull.state, PR_TONE[pull.state]),
      el("span", "#" + pull.number + " " + pull.title, "title"), el("span", "+" + added, "stat-add"),
      el("span", "\u2212" + removed, "stat-del"), el("span", verb + new Date(at * 1000).toLocaleTimeString(), "when")),
      pullBox(pull, pullNotes[pull.number]));
    item.open = expandedPulls.has(pull.number);
    item.ontoggle = () => { if (item.open) expandedPulls.add(pull.number); else expandedPulls.delete(pull.number); };
    return item;
  }

  async function mergePull(number, gitCommit, footer) {
    footer.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    showMessage("bonus-message", "Merging #" + number + "…", false, true);
    const started = Date.now();
    try {
      const data = await post("/bonus/pulls/" + number + "/merge", {git_commit: gitCommit});
      const seconds = Math.round((Date.now() - started) / 1000);
      if (data.status === "success") {
        pullNotes[number] = undefined;
        showMessage("bonus-message", "Merged #" + number + " · " + seconds + "s · it is now in the History");
        if (typeof dinoJump === "function") dinoJump();
      } else {
        pullNotes[number] = data.status === "conflict" ? "Conflict: " + data.error :
          data.status === "failed" ? "Merge failed validation and was rolled back. " + data.error : data.error;
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
      await post("/bonus/pulls/" + number + "/close", {});
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
      const open = pulls.filter((pull) => pull.state === "open");
      const history = pulls.filter((pull) => pull.state !== "open");
      const parts = [];
      if (open.length) parts.push(el("div", "Open · " + open.length, "pr-group"), ...open.map(pullItem));
      if (history.length) parts.push(el("div", "History · merged and closed · " + history.length, "pr-group"), ...history.map(pullItem));
      pullList.replaceChildren(...parts);
      pullEmpty.hidden = pulls.length > 0;
    } catch (error) {
      pullEmpty.hidden = false;
    }
  }

  function renderBonus(container, data, seconds) {
    if (data.status === "open" && data.pull) {
      expandedPulls.add(data.pull.number);
      container.replaceChildren(make("div", "banner ok", el("div", "\u2713", "icon"),
        make("div", "", el("strong", "Opened pull request #" + data.pull.number + ": " + data.pull.title),
          el("span", "Checks passed · nothing written yet · review the diff below, then Merge or Close · " + seconds + "s"))));
      loadPulls().then(() => pullsCard.scrollIntoView({behavior: "smooth", block: "start"}));
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
  demoButton.onclick = async () => {
    demoButton.disabled = true;
    try {
      const started = await post("/bonus/docker/demo", {});
      if (!started.ok) { showDocker({error: started.error}); return; }
      service.value = started.service;
      watchButton.onclick();
    } catch (error) {
      showDocker({error: error.message});
    } finally {
      demoButton.disabled = false;
    }
  };
  resetButton.onclick = async () => {
    resetButton.disabled = true;
    try {
      const body = await post("/bonus/docker/demo/reset", {});
      if (!body.ok) { showDocker({error: body.error}); return; }
      dockerLog.replaceChildren();
      logMark("reset: " + ([...body.restored, ...body.removed.map((p) => p + " (removed)")].join(", ") || "nothing changed"));
      if (typeof refreshOverview === "function") refreshOverview();
    } catch (error) {
      showDocker({error: error.message});
    } finally {
      resetButton.disabled = false;
    }
  };
  watchButton.onclick = async () => {
    if (!service.value.trim()) { showDocker({error: "type a container name"}); return; }
    dockerLog.replaceChildren();
    inTraceback = false;
    try { showDocker(await post("/bonus/docker/watch", {service: service.value.trim(), intent: dockerIntent.value.trim()})); }
    catch (error) { showDocker({error: error.message}); }
  };
  stopButton.onclick = async () => {
    try { showDocker(await post("/bonus/docker/stop", {})); } catch (error) { showDocker({error: error.message}); }
  };

  if (location.hash === "#bonus") showTab("bonus");
})();
