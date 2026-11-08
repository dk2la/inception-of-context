## Project

Inception-of-Context (42 subject): a local, offline indexer + RAG + patch loop over a small calculator Target Project. The agreed design and build order are in `docs/plan.md`; read it before writing code.

Keep code as short and plain as possible, readable by anyone who has written basic Python (see `docs/adr/0001-simplicity-first.md`).

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (`dk2la/inception-of-context`) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
