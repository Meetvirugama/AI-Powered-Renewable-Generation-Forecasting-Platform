---
name: dual-agent-protocol
description: Use at the start of any task on this repo, and before editing any file. Defines the Claude Code (lead) / Antigravity (executor) chain of command, file ownership, and handoff format for this two-agent frontend workstream.
---

# Dual-agent protocol

Two AI agents work this repo concurrently. Without this protocol they clobber each
other's edits and re-litigate settled decisions.

## Chain of command

**Claude Code is lead.** Antigravity is executor.

| | Claude Code (lead) | Antigravity (executor) |
|---|---|---|
| Architecture, file layout, dependencies | **decides** | proposes |
| Backend contract interpretation | **decides** | asks |
| Which component library to use | **decides** | asks |
| Building components to spec | reviews | **builds** |
| Browser verification, visual iteration | spot-checks | **owns** |
| Final merge / commit | **approves** | never commits unprompted |

Antigravity: when a task is ambiguous, or would change architecture, add a dependency,
or touch a file outside your assigned scope — **stop and surface it to the human for
Claude Code to rule on.** Do not decide it yourself.

Claude Code: hand Antigravity work as a written spec (see Handoff format). Do not hand
over vague goals.

## Before editing any file

Always, no exceptions:

```bash
git status --short
git diff -- <file>
```

If the file changed since you last read it, **re-read it before editing.** The other
agent may have just rewritten it.

## File ownership

Only one agent owns a file at a time. Ownership is declared in the handoff, not assumed.

Never-touch for both agents unless the human explicitly says so:
`backend/` · `config/` · `docs/` · `alembic.ini` · `tests/` · DB migrations

Those belong to other human team members. Concurrent edits there cause merge conflicts
in a hackathon with no time to resolve them.

## Handoff format

Claude Code writes this; Antigravity executes exactly this and nothing more:

```
TASK: <one line>
OWNS: <exact file paths this task may create or modify>
CONTRACT: <API endpoint + response shape it consumes, or "none">
DONE WHEN: <observable condition, e.g. "renders 96 blocks, no console errors at 400px">
DO NOT: <explicit out-of-scope list>
```

Antigravity reports back:

```
CHANGED: <files>
VERIFIED: <what was actually run/observed — not what was intended>
BLOCKED: <anything skipped, and why>
```

Report what actually happened. A skipped step reported as done costs more time than the
step itself. If something failed, say so with the error text.

## Commits

Neither agent commits or pushes unless the human asks in that turn. Approval to commit
once is not standing approval.
