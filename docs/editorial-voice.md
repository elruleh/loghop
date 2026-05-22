# loghop Editorial Voice

`loghop` should read like an operational tool for developers managing continuity across agent sessions.

## Voice

- Brief
- Technical
- Calm
- Direct
- Reliable

## What the product voice should optimize for

- Fast comprehension
- Low cognitive load
- Clear next actions
- Trust in system state

## Writing rules

1. Prefer short labels over explanatory prose.
2. Use concrete verbs: `Resume`, `Open`, `Retry`, `Delete`, `Register`.
3. Describe state as it is. Do not soften failures or pad success messages.
4. Keep empty states actionable.
5. Avoid marketing phrasing, encouragement, and ornamental copy.
6. Prefer product nouns already used in the app: `project`, `session`, `handoff`, `provider`, `timeline`.
7. When space is tight, drop articles first.
8. For warnings and errors, state the condition first, then the next action if needed.

## Tone by surface

### TUI

- Compact and scannable
- Labels should be noun-first
- Hints should be one step, not mini-docs

Examples:

- `No projects yet`
- `Resume with Codex`
- `No providers on PATH`

### CLI

- Slightly more explicit than the TUI
- Success messages should confirm the artifact created or state changed
- Follow-up hints should appear only when they unblock the next step

Examples:

- `Initialized project`
- `Built handoff H-001`
- `Run \`loghop doctor --fix\` to repair detected issues`

## Avoid

- `It looks like...`
- `You can now...`
- `Successfully completed...`
- `We couldn't...`
- Long tutorial text in the main flow

## Preferred patterns

- Empty: `No sessions yet`
- Success: `Recorded session S-003`
- Warning: `Provider unavailable`
- Action hint: `Run \`loghop run\``
