# Inception-of-Context

A local, offline coding assistant that indexes a small codebase, answers questions about it, and applies validated patches to it with rollback on failure.

## Language

### Indexing

**Target Project**:
The small calculator application shipped in this repository that the system indexes, answers questions about, and patches.
_Avoid_: demo app, target directory, workspace

**Chunk**:
One logical block of a source file (a function, method, class, or configuration block) stored with its file path, line range, and content hash.
_Avoid_: snippet, block, document

**Index**:
The persisted collection of Chunks that mirrors the Target Project on disk.
_Avoid_: vector store, database, collection

**Watcher**:
The part of the system that observes the Target Project on disk and incrementally updates the Index for only the files that changed.
_Avoid_: sync, observer

### Asking

**Question**:
A natural-language query about the Target Project, answered from retrieved Chunks without modifying anything.
_Avoid_: intent, prompt, query

### Patching

**Intent**:
A natural-language request to change the Target Project, which starts a Patch Loop.
_Avoid_: question, task, command

**Patch**:
A structured change proposal listing a summary and, per file, its path, operation (create, modify, delete), and complete post-change content.
_Avoid_: diff, edit, change set

**Sanity Check**:
A hard pre-write rule that rejects a Patch outright before anything touches disk.
_Avoid_: lint, warning, validation

**Validation Command**:
The command configured by the Target Project that decides whether an applied Patch left the project working.
_Avoid_: test, check

**Attempt**:
One generate → sanity-check → apply → validate pass inside a Patch Loop.
_Avoid_: iteration, try, retry

**Patch Loop**:
The sequence of up to three Attempts started by one Intent, ending in either a validated Patch or a Rollback.
_Avoid_: pipeline, agent run

**Snapshot**:
The byte-for-byte copy of every file a Patch Loop may touch, taken before its first write.
_Avoid_: backup

**Rollback**:
Restoring the Target Project to its Snapshot after a Patch Loop fails.
_Avoid_: revert, undo
