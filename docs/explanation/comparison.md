---
layout: default
title: loghop vs other AI coding tools
description: How loghop compares to Aider, Cursor, Cline, Roo Code, Continue, Claude Code sessions, Copilot and manual copy-paste — and where each tool fits.
nav_order: 11
---

# loghop vs other AI coding tools

loghop is **not** a replacement for your AI coding assistant. It's the
**handoff layer** that sits *between* assistants, so context survives when
you switch tools. Most tools in this space are excellent at what they do —
the question is whether they solve the *switching* problem.

> If you only ever use one assistant, you don't need loghop. If you use two
> or more (Claude Code *and* Codex, or an IDE agent *and* a CLI agent), this
> page is for you.

## The core distinction

| Category | What it does | Examples |
|---|---|---|
| **AI coding assistants** | Do the actual coding | Claude Code, Codex, Cursor, Aider, Cline, Copilot |
| **Handoff layer** | Carries context *across* assistants | **loghop** |

loghop is the only category in the second row. It complements the first.

## Comparison table

| Tool | Cross-tool handoff | Multi-provider | Auto-capture | Secret redaction | Local-only | License |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **loghop** | ✅ Structured handoff packets | ✅ Claude + Codex (extensible) | ✅ Native transcripts | ✅ Built-in pipeline | ✅ Fully | MIT |
| Aider | ❌ Single session | ❌ Aider only | N/A | ✅ Good | ✅ | Apache-2.0 |
| Cursor | ❌ IDE session only | ❌ Cursor only | ✅ Within IDE | ⚠️ Cloud-assisted | ❌ Partial | Proprietary |
| Cline / Roo Code | ❌ Per-extension | ❌ VS Code only | ✅ Within IDE | ⚠️ Depends on model | ❌ Partial | Apache-2.0 |
| Continue | ❌ Per-IDE config | ⚠️ Model-agnostic, no handoff | ⚠️ Config-driven | ⚠️ Depends | ❌ Partial | Apache-2.0 |
| Claude Code sessions | ⚠️ Project files, Claude-only | ❌ Claude only | ✅ Native | ✅ Good | ✅ | Proprietary |
| GitHub Copilot | ❌ Inline only | ❌ GitHub only | ❌ No session concept | ⚠️ Cloud | ❌ | Proprietary |
| Gemini CLI | ❌ Single agent | ❌ Gemini only | ✅ Native | ⚠️ Varies | ✅ | Proprietary |
| Manual copy-paste | ⚠️ Fragile | ✅ Any | ❌ Manual | ❌ Leaks secrets | ✅ | — |

## When to use what

### Use loghop if…
- You switch between Claude Code and Codex (or plan to add Gemini CLI).
- You're tired of re-explaining the project every time you change tools.
- You want session logs in your repo **without** leaking API keys.
- You work locally-first and don't want telemetry or cloud sync.

### Use Aider if…
- You want a single, excellent git-native coding partner and never switch.
- Aider's edit-format and git workflow are enough for your loop.

### Use Cursor / Cline / Roo Code if…
- You live inside an IDE and want the AI integrated into the editor.
- You don't need to hand off to a *different* tool.

> loghop works **alongside** all of these. You can run Cursor in the IDE and
> still use loghop to capture CLI sessions for a teammate or a different
> assistant.

### Use Claude Code's native sessions if…
- You only ever use Claude Code, never anything else.

### Use plain copy-paste if…
- You switch tools once a month and don't mind the 20-minute tax each time.

## What makes loghop different

1. **Provider-agnostic by design.** The `BaseProvider` contract is four
   methods. Adding Gemini CLI is ~50 lines.
2. **Redaction is not optional.** AWS, GitHub, Slack, SendGrid tokens (and
   generic API keys) are stripped *before* anything is stored or handed off.
   You can add your own patterns in `config.toml`.
3. **Local-first, zero telemetry.** Everything lives in `.loghop/` inside
   your repo. No cloud, no analytics, no phone-home.
4. **Handoffs are markdown, not magic.** The next assistant reads a
   human-readable `.md` packet — no proprietary format lock-in.

## Honest limitations

loghop doesn't try to be everything:

- **Not an agent.** It doesn't write code. Your assistant does.
- **Not an IDE plugin.** The interface is a CLI and a TUI.
- **Not multi-user (yet).** It's a single-developer workflow tool. If you
  want to back up `.loghop/` to a git remote, that works.
- **Two providers today.** Claude Code and Codex ship now. Gemini CLI is the
  next target — contributions welcome.

## Migrating into loghop

If you have existing session history in `~/.claude/projects/` or
`~/.codex/sessions/`, loghop will pick up new sessions from the next
`loghop run`. We don't (yet) have a bulk-import tool for historical
transcripts — see [issue tracker](https://github.com/elruleh/loghop/issues)
for migration helpers.

---

*Is a tool missing from this table or described incorrectly? Open a PR —
comparisons only stay useful if they stay honest.*
