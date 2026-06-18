<p align="center">
  <a href="https://github.com/elruleh/loghop">
    <img src="docs/img/logo-banner-a.svg" alt="loghop" width="500">
  </a>
</p>

<p align="center">
  <strong>Stop losing context when switching AI coding assistants</strong>
</p>

<p align="center">
<a href="https://pypi.org/project/loghop">
  <img src="https://img.shields.io/pypi/v/loghop?color=%2334D058&label=pypi%20package" alt="Package version">
</a>
<a href="https://pypi.org/project/loghop">
  <img src="https://img.shields.io/pypi/pyversions/loghop.svg?color=%2334D058" alt="Supported Python versions">
</a>
<a href="https://github.com/elruleh/loghop/actions/workflows/ci.yml?query=branch%3amain">
  <img src="https://github.com/elruleh/loghop/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI">
</a>
<a href="https://static.pepy.tech/badge/loghop">
  <img src="https://static.pepy.tech/badge/loghop" alt="Downloads">
</a>
<a href="https://codecov.io/gh/elruleh/loghop">
  <img src="https://codecov.io/gh/elruleh/loghop/branch/main/graph/badge.svg" alt="Coverage">
</a>
<a href="https://opensource.org/licenses/MIT">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
</a>
<a href="https://elruleh.github.io/loghop/">
  <img src="https://img.shields.io/badge/docs-elruleh.github.io%2Floghop-blue" alt="Documentation">
</a>
</p>

<p align="center">
<a href="#why-loghop">Why?</a> ·
<a href="#quick-start">Quick start</a> ·
<a href="#how-it-works">How it works</a> ·
<a href="#vs-alternatives">vs Alternatives</a> ·
<a href="https://elruleh.github.io/loghop/">Docs</a> ·
<a href="#contributing">Contributing</a>
</p>

---

**loghop** lets you switch between AI coding assistants (Claude Code, Codex) without losing context. It captures every session, builds a shared timeline, and generates handoff documents so the next agent—even a different one—can pick up exactly where you left off.

<p align="center">
  <img src="docs/img/demo/loghop-quickstart.gif" alt="loghop quickstart demo" width="800">
</p>

<p align="center">
  <a href="https://star-history.com/#elruleh/loghop&Date">
    <img src="https://api.star-history.com/svg?repos=elruleh/loghop&type=Date" alt="Star History Chart" width="500">
  </a>
</p>

## Why loghop?

- **You lose context every time you switch assistants.** Claude Code runs out of thinking budget. Codex gives better answers for your stack. But starting over means re-explaining decisions, copy-pasting summaries, or losing the thread entirely.
- **AI assistants don't know what the last one did.** Each session is isolated. No shared memory. You waste time catching them up instead of moving forward.
- **Manual handoffs are fragile.** Copying session logs between terminals breaks. Forgetting a key decision costs hours. You shouldn't need to be the glue.
- **You want to use the right tool for each task.** Some problems need deep reasoning. Others need fast iteration. loghop lets you switch freely without starting over.

## Quick start

**Install** (requires Python 3.12+):

```bash
pipx install loghop
# or
uv tool install loghop
```

**Initialize** in any Git repository:

```bash
loghop init              # one-time setup
loghop run               # start your first session
loghop goal "Ship auth"  # set a goal so next run stays focused
```

That's it. Every `loghop run` from now on:
1. Builds a handoff from your project's timeline
2. Launches your AI assistant (Claude Code or Codex)
3. Captures the transcript when it finishes
4. Appends the session to the shared timeline

Switch providers anytime:

```bash
loghop run --provider codex   # switch to Codex
loghop run --provider claude  # back to Claude Code
```

The next assistant gets the full context automatically.

## Example workflow

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   🤖 Session 1: Claude Code                                                 │
│   $ loghop run                                                              │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │ Working on task: "Setup Database schema"                     │          │
│   │ [Session complete - Autocapturing...]                        │          │
│   └──────────────────────────────┬───────────────────────────────┘          │
│                                  │                                          │
│                                  ▼                                          │
│                    📦 Unified Timeline (.loghop/)                           │
│     S-001.md: Claude Code session (Setup DB)                                │
│     H-001.md: Next steps (Add migrations & seeding)                          │
│                                  │                                          │
│                                  ▼                                          │
│   🧠 Session 2: Codex (OpenAI)                                              │
│   $ loghop run --provider codex                                             │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │ Handoff loaded: Resuming from Session 1 (Setup DB)           │          │
│   │ Current Goal: "Add migrations & seeding"                     │          │
│   └──────────────────────────────────────────────────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```


## vs Alternatives

| Approach | Context Transfer | Multi-Provider | Automatic | Security |
|----------|------------------|----------------|-----------|----------|
| **loghop** | ✅ Structured handoffs | ✅ Claude + Codex | ✅ Auto-capture | ✅ Secret redaction, 0600 perms |
| Aider | ❌ None (single-session tool) | ❌ Aider only | N/A | ✅ Good |
| Claude Code sessions | ⚠️ Project files only | ❌ Claude only | ✅ Native | ✅ Good |
| Manual copy-paste | ⚠️ Fragile, error-prone | ✅ Any | ❌ Manual work | ❌ Risk of leaking secrets |
| swe-agent | ❌ No handoff support | ❌ Single agent | ❌ No | ⚠️ Depends on implementation |

**Why not just use Claude's session history?** Claude Code keeps project context between runs, but only for Claude. If you switch to Codex (or any other assistant), you start from zero. loghop gives you shared memory across providers.

**Why not Aider?** Aider is excellent for interactive coding with Git integration, but it's a single tool, not a handoff system. If you want to switch from Aider to Claude Code mid-task, you're back to copy-pasting.

## How it works

1. **Run your AI assistant through loghop:**
   ```bash
   loghop run --provider claude
   ```
   loghop builds a handoff document from your timeline and launches Claude Code.

2. **Work normally.** Claude Code (or Codex) runs as usual. You don't change your workflow.

3. **loghop captures everything automatically.** When the session ends, loghop:
   - Reads the provider's native transcript (`~/.claude/projects/...` or `~/.codex/sessions/...`)
   - Redacts secrets (API keys, tokens, JWTs)
   - Stores session metadata in `.loghop/sessions/S-001.md`
   - Appends to the shared timeline (`.loghop/timeline.jsonl`)
   - Generates a handoff document (`.loghop/handoffs/H-001.md`) for the next run

4. **Switch providers seamlessly:**
   ```bash
   loghop run --provider codex
   ```
   Codex starts with the full context from your Claude session. No manual copy-paste.

**Architecture:**

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  loghop run  │────▶│   Provider   │────▶│   Capture   │
│  build handoff│    │ Claude/Codex │    │  transcript  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                │
                          ┌─────────────────────▼─────────────────────┐
                          │              .loghop/                       │
                          │  timeline.jsonl  ← shared across providers │
                          │  sessions/S-*.md ← redacted metadata       │
                          │  handoffs/H-*.md ← context for next run    │
                          └────────────────────────────────────────────┘
```

### Integration layers

`loghop init` orchestrates optional integrations. Each answer is stored in
`~/.loghop/config.toml`. Re-running `init` is safe; installers are idempotent.

1. **Claude hooks** — merges `SessionStart` and `SessionEnd` commands into
   `~/.claude/settings.json`, preserving existing settings.
2. **Codex shim** — writes a managed executable in `~/.local/bin/codex` that
   delegates to `loghop wrap codex`. Refuses to overwrite non-loghop files.
3. **Prompt block** — writes `~/.loghop/loghop-prompt.md` and includes it from
   Codex `AGENTS.md` and Claude `CLAUDE.md`. Asks providers to emit a structured
   `loghop` block with summary, decisions, and todos.
4. **Fast-path parser** — when a captured transcript contains the fenced `loghop`
   block, autocapture trusts it for metadata before falling back to heuristics.

### Transparent capture

Add a shell alias so direct `claude`/`codex` calls go through loghop in
initialized repos. Outside a repo, the wrapper passes through to the real binary.

You can automatically install or remove these aliases in your shell profile configuration files (`~/.bashrc`, `~/.zshrc`, `~/.config/fish/config.fish`) using:

```bash
loghop install-aliases       # install the alias block
loghop uninstall-aliases     # remove the alias block
```

Or configure it manually:

```bash
alias claude='loghop wrap claude'
alias codex='loghop wrap codex'
```

## Supported Providers

- **Claude Code** (Anthropic) — Auto-detected from `PATH`
- **Codex** (OpenAI) — Auto-detected from `PATH`

Run `loghop providers` to see what's available on your system. Both providers work without configuration; loghop finds them automatically.

## Terminal UI

Optional interactive TUI for browsing projects, sessions, and handoffs:

```bash
pipx install 'loghop[tui]'  # install with Textual
loghop tui                   # launch the TUI
```

<p align="center">
  <img src="docs/img/loghop-tui.svg" alt="loghop TUI with Harbor dark theme" width="100%">
</p>

- **Home screen** — global project list and status
- **Project screen** — sessions, handoffs, and timeline for one repo
- **Command palette** — press `m` to search and run commands
- **4 themes** — Classic dark/light, Harbor dark/light

## Commands

**Core workflow:**
```
loghop init                      set up in current repo
loghop run [--provider <name>]   start or resume a session
loghop goal "<text>"             set a project goal
loghop status                    project overview
```

**Browse and inspect:**
```
loghop sessions                  list all sessions
loghop timeline                  view shared timeline
loghop handoff list              show handoff history
loghop tui                       open terminal UI
```

**Advanced:**
```
loghop topics                    group related sessions
loghop projects                  manage project registry
loghop health                    run health checks
loghop backup create|restore     backup/restore data
loghop install-aliases           auto-capture on direct provider calls
```

Full command reference: `loghop --help` or see the [docs](https://elruleh.github.io/loghop/).

## Status

- **Current version:** 0.2.0 ([changelog](CHANGELOG.md))
- **Python requirement:** 3.12+
- **Platforms:** Linux, macOS (primary); Windows (best-effort — core CLI works, some POSIX-specific features degrade gracefully)
- **Test coverage:** 80%+ with CI on Python 3.12 and 3.13
- **License:** MIT
- **Providers:** Claude Code, Codex (auto-detected from `PATH`)


## Security & Privacy

**loghop keeps everything local.** No cloud sync, no external services. All data stays on your machine.

- **Secret redaction:** API keys, tokens, JWTs, and credential URLs are automatically stripped from transcripts
- **File permissions:** All `.loghop/` files are written `0600` (owner-only read/write)
- **Atomic writes:** `tempfile.mkstemp` + `os.replace` + `fsync` prevents corruption
- **HMAC integrity:** Session and handoff artifacts include cryptographic signatures
- **Symlink protection:** File reads reject symlinks; paths are validated before use
- **Graceful interruption:** `Ctrl+C` and timeouts trigger cleanup; partial transcripts are recovered automatically

## Links

- **PyPI:** [pypi.org/project/loghop](https://pypi.org/project/loghop)
- **Documentation:** [elruleh.github.io/loghop](https://elruleh.github.io/loghop/)
- **Issues:** [github.com/elruleh/loghop/issues](https://github.com/elruleh/loghop/issues)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md)

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

**Quick start:**
```bash
git clone https://github.com/elruleh/loghop.git
cd loghop
uv sync --all-extras --dev
bash scripts/release_check.sh qa
```

## License

MIT — see [LICENSE](LICENSE).

Loghop is not affiliated with, endorsed by, or connected to Anthropic or OpenAI.

## Used by

Projects and teams using loghop in production or for personal workflows:

<!-- Add your project here via a PR to README.md -->
<!-- Format: [name](url) — short description -->
- _Add your project here_

Want to be listed? Open a PR adding your project, or share it in [Show and tell](https://github.com/elruleh/loghop/discussions/categories/show-and-tell).

---

<p align="center">
  Made with ♥️ by developers tired of copy-pasting context between AI assistants.
</p>

<p align="center">
  <a href="https://github.com/elruleh/loghop/issues/new/choose">Report a bug</a> ·
  <a href="https://github.com/elruleh/loghop/issues/new/choose">Request a feature</a> ·
  <a href="https://github.com/elruleh/loghop/discussions">Discussions</a>
</p>
