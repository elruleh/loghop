---
layout: default
title: Release process
description: How to cut a clean loghop release without post-hoc hygiene commits.
---

# Release process

This guide exists so every release is a single clean commit, not a wave of follow-up
"polish" PRs. Hygiene work that should have been done before tagging is the most
common reason a project's history starts to look patched-together; the discipline
below is the answer.

## Discipline rules

These are non-negotiable. Violating them is the single most common way an
open-source project's history degrades between 0.x releases.

1. **No standalone hygiene commits between releases.** If a typo, a stale workflow,
   an identity leak, an open CodeQL finding, or a missed smoke test shows up
   *after* a release, it is folded into the *next* feature/release commit —
   never as its own `chore(repo):` or `fix: meta` commit.
2. **The pre-release audit (below) runs before every tag.** No tag is pushed
   without passing it. The audit is the gate.
3. **One release = one commit on `main` per version.** A `chore(release): vX.Y.Z`
   commit followed by zero or more release-only follow-ups is the expected
   pattern. Multiple "polish before announce" commits is not.
4. **Anything that would otherwise become a hygiene commit is added to the
   `CHANGELOG.md` `## [Unreleased]` section as the work is done**, not retrofitted.

## Pre-release audit (mandatory before tagging)

Run through this list. If anything fails, fix it in the same release — do not
tag and "polish later".

### Identity and authorship

- [ ] No personal name or email appears in any tracked file. The public handle
      and the `proton.me` contact are the only ones that should be there.
      ```bash
      git ls-files | xargs grep -lE 'raul|raul90' \
        | grep -v -E '(\.mailmap|tests/test_release_hygiene\.py)$'
      ```
      (Substitute your own old email if different.)
- [ ] `.mailmap` canonical identity is the public handle and the only
      `git shortlog` line.
      ```bash
      git shortlog -sn
      ```
- [ ] Local `git config user.name` / `user.email` are the canonical identity.
- [ ] GitHub profile name (Settings → Profile) matches the public handle. The
      `PATCH /user` API requires the `user` OAuth scope which `gh` does not
      request by default; do this once in the web UI.

### CI / CodeQL / workflows

- [ ] CodeQL: zero open alerts.
      ```bash
      gh api /repos/<owner>/<repo>/code-scanning/alerts?state=open --jq 'length'
      ```
- [ ] No failed workflow runs in the last 24 hours that are not pre-merge noise.
- [ ] `actions/checkout` and other deprecated Node 20 actions are at the
      current major (`@v6` as of this writing).
- [ ] The `All Contributors` workflow either passes or no-ops cleanly when
      `.all-contributorsrc` is absent.
- [ ] The release-rehearsal workflow (`release-rehearsal.yml`) is green for the
      target version.

### Demo and documentation assets

- [ ] The two demo tapes render without leaking the maintainer's home path
      (`/home/<user>/`) or username.
- [ ] Tapes use a generic path or `$HOME` substitution, not a literal
      `/home/raul/...` style string.
- [ ] `docs/img/demo/loghop-quickstart.{mp4,gif}` and
      `docs/img/demo/loghop-tui-demo.{mp4,png}` exist and were generated from
      the current tapes against the about-to-be-released package version.
- [ ] `docs/index.md` and the GitHub Pages landing render the demo assets
      (the rendered HTML at `https://<owner>.github.io/<repo>/` references
      them).
- [ ] `CHANGELOG.md` has an entry for the new version, with Added / Changed /
      Fixed / Removed subsections, dated `YYYY-MM-DD`.
- [ ] `CHANGELOG.md` link footer references the new tag:
      `[X.Y.Z]: https://github.com/<owner>/<repo>/compare/vPREV...vX.Y.Z`.

### Repository metadata

- [ ] GitHub "About" description is current and matches `pyproject.toml`'s
      `description`.
- [ ] Topics are current (no stale single-keyword placeholders, no marketing
      terms that don't appear in the README).
- [ ] Social preview is uploaded (Settings → Social preview; this is the only
      repo setting that cannot be set via the API and must be done in the
      web UI; the file lives at `docs/img/social-preview.png`).
- [ ] No `marketing/` content is tracked. The folder is gitignored; only
      launch-time drafts live there locally.

## Pre-release verification

After the audit passes, run the local gates before pushing the tag:

```bash
# 1. Rehearse the release locally (the workflow's job, run by hand)
bash scripts/release_check.sh qa
bash scripts/release_check.sh artifacts

# 2. Smoke the wheel and sdist in a clean venv
bash scripts/smoke_published.sh --version X.Y.Z --repository pypi
#    (replace --repository pypi with testpypi if rehearsing there first)

# 3. Confirm the changelog diff is sensible
git log --oneline vPREV..HEAD
```

When all three pass, the release-rehearsal workflow is run from the Actions
tab (workflow_dispatch) with the target version. It runs the same gates on
`ubuntu-latest` and optionally publishes to TestPyPI. If TestPyPI is published,
`smoke_published.sh` runs against it before any PyPI publish.

## Release execution

The release is exactly four commands and one UI edit. No more.

```bash
# 1. Bump the version (single source of truth: src/loghop/__init__.py)
$EDITOR src/loghop/__init__.py          # __version__ = "X.Y.Z"
$EDITOR CHANGELOG.md                    # add ## [X.Y.Z] - DATE + link footer

# 2. Commit the release
git add -A
git commit -m "chore(release): vX.Y.Z"
#    No AI co-author trailers, no extra polish commits.

# 3. Tag and push
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

Pushing the tag triggers `.github/workflows/release.yml`, which builds, publishes
to PyPI (via the configured trusted publisher), runs `smoke_published.sh` from
PyPI, and then creates a draft GitHub Release populated by `release-drafter`.

## Post-release (within 5 minutes of the tag)

- [ ] PyPI shows the new version:
      ```bash
      python3 -m pip index versions loghop
      ```
- [ ] GitHub Release draft (auto-created by `release-drafter`) is reviewed,
      edited for accuracy, and **published** (not left as a draft).
- [ ] `uv tool install --refresh 'loghop[tui]==X.Y.Z' --force` succeeds and
      `loghop tui` loads the seeded projects.
- [ ] GitHub Pages rebuilt successfully (Actions tab → "pages build and
      deployment" is green).
- [ ] `git fetch --tags origin` confirms the tag is on the expected commit
      and the previous tag is still on its commit (no accidental tag move).

## What "no hygiene commits" looks like in practice

A correct release history between two feature commits:

```
<feature commit>            ← feature, fix, refactor, perf, test
<unrelated fix commit>      ← any user-facing fix is fine
chore(release): vX.Y.Z      ← ONLY this kind of chore commit
<next feature commit>       ← the cycle restarts
```

An incorrect history (the pattern this guide exists to prevent):

```
<feature commit>
<feature commit>
chore(repo): polish metadata              ← BANNED
fix: codeql findings                      ← BANNED
ci: fix all-contributors                  ← BANNED
chore(repo): anonymize identity           ← BANNED
chore(release): vX.Y.Z
```

If you find yourself writing a `chore(repo): polish …` or `fix: meta …` commit,
stop, fold the change into the next release's commit (or amend the release
commit before the tag is pushed), and update this guide if the missing audit
step is what let it slip.
