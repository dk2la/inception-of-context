# Simplicity first: code readable by anyone who has written basic Python

The project is defended in front of a peer who must understand it without effort, so the code is kept as short and plain as possible: flat functions over class hierarchies, the standard library over clever abstractions, few dependencies, and no build step for the dashboard. When two approaches both satisfy the subject, we pick the one with less code, even if it is less general or less efficient (for example, ranking the whole Index on every query, a synchronous `/patch`, and polling an in-memory list for SSE).
