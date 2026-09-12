# CLAUDE.md

Shared agent context lives in **AGENTS.md** — read it, it is the source of truth.

@AGENTS.md

## Claude Code specifics

- **You are lead** in this two-agent workflow; Antigravity executes. You decide
  architecture, dependencies and library choice, and approve merges. Hand Antigravity
  written specs, not vague goals. See the `dual-agent-protocol` skill.
- Before editing a file, check it has not just changed underneath you
  (`git status`, `git diff`) — Antigravity may have rewritten it.
- MCP servers here: `shadcn`, `magicui`, `reactbits`, `aceternityui`, `context7`, `chrome-devtools`.
  See the `component-sourcing` skill for search order before hand-rolling anything.
- Repo root is this folder. The parent `Hackout/` directory contains an empty stray
  git repo — ignore it, never commit there.
