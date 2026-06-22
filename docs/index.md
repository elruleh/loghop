---
layout: landing
title: loghop
description: Switch between Claude Code and Codex without losing context. loghop captures sessions, redacts secrets, and writes handoffs so the next AI assistant resumes cleanly.
---

<section class="shell hero">
  <div>
    <div class="eyebrow">Claude Code ↔ Codex handoffs</div>
    <h1>Switch AI coding assistants without starting over.</h1>
    <p class="lead">loghop captures local assistant sessions, redacts sensitive context, builds a shared project timeline, and writes handoff packets so the next run resumes cleanly.</p>
    <div class="actions">
      <a class="button primary" href="#install">Install loghop</a>
      <a class="button secondary" href="https://github.com/elruleh/loghop">View on GitHub</a>
    </div>
    <div class="badges" aria-label="Project status badges">
      <a href="https://github.com/elruleh/loghop" aria-label="Star loghop on GitHub"><img src="https://img.shields.io/github/stars/elruleh/loghop?style=social" alt="GitHub stars"></a>
      <img src="https://img.shields.io/pypi/v/loghop?color=%2334D058&label=pypi%20package" alt="PyPI package version">
      <img src="https://img.shields.io/pypi/pyversions/loghop.svg?color=%2334D058" alt="Supported Python versions">
      <img src="https://github.com/elruleh/loghop/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status">
      <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT license">
    </div>
  </div>
  <div class="terminal" aria-label="Example terminal flow">
    <div class="dots" aria-hidden="true"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
<pre><span class="prompt">$</span> loghop run --provider claude
<span class="dim">capturing session S-001...</span>
<span class="ok">✓</span> timeline updated
<span class="ok">✓</span> handoff H-001 created

<span class="prompt">$</span> loghop run --provider codex
<span class="dim">loading previous context...</span>
<span class="ok">✓</span> resumed from S-001</pre>
  </div>
</section>

<section class="shell section" aria-labelledby="why-loghop">
  <h2 id="why-loghop">Why loghop?</h2>
  <p class="section-intro">AI coding tools are useful in different moments. loghop keeps project context portable so changing assistants does not mean rebuilding the conversation from memory.</p>
  <div class="grid">
    <article class="card"><h3>Capture</h3><p>Reads native Claude Code and Codex transcripts and stores clean local session records.</p></article>
    <article class="card"><h3>Redact</h3><p>Removes sensitive context before session summaries, timelines, or handoffs are reused.</p></article>
    <article class="card"><h3>Resume</h3><p>Turns previous work into actionable context for the next assistant run.</p></article>
  </div>
</section>

<section id="workflow" class="shell section" aria-labelledby="workflow-title">
  <h2 id="workflow-title">The workflow</h2>
  <div class="workflow">
    <article class="step"><strong>Run an assistant</strong><p>Work normally with Claude Code or Codex inside your repository.</p></article>
    <article class="step"><strong>Capture the session</strong><p>loghop records status, summary, decisions, todos, changed files, and transcript context.</p></article>
    <article class="step"><strong>Build a handoff</strong><p>The project timeline becomes a compact packet for the next run.</p></article>
    <article class="step"><strong>Resume elsewhere</strong><p>Start another assistant with the relevant context already prepared.</p></article>
  </div>
</section>

<section id="install" class="shell section" aria-labelledby="install-title">
  <h2 id="install-title">Install and start</h2>
  <p class="section-intro">loghop is published on PyPI and works with Python 3.12 or newer.</p>
  <div class="terminal">
<pre><span class="prompt">$</span> pipx install loghop
<span class="prompt">$</span> cd your-repo
<span class="prompt">$</span> loghop init
<span class="prompt">$</span> loghop run</pre>
  </div>
</section>

<section class="shell section" aria-labelledby="designed-for">
  <h2 id="designed-for">Designed for real projects</h2>
  <div class="grid two">
    <article class="card"><h3>Local-first storage</h3><p>Project state lives in <code>.loghop/</code>. Handoffs, timelines, sessions, and redacted transcripts stay under your control.</p></article>
    <article class="card"><h3>CLI and TUI</h3><p>Use compact commands for automation or the Textual terminal UI for browsing sessions and handoffs.</p></article>
    <article class="card"><h3>Provider-aware</h3><p>Capture Claude Code and Codex sessions while keeping a shared project memory across both tools.</p></article>
    <article class="card"><h3>Release-ready</h3><p>CI, security checks, packaging smoke tests, and reproducible handoff files are built into the project workflow.</p></article>
  </div>
</section>

<section id="docs" class="shell section" aria-labelledby="docs-title">
  <h2 id="docs-title">Documentation</h2>
  <p class="section-intro">The docs follow the Diátaxis model: start with a tutorial, use how-to guides for tasks, reference for exact behavior, and explanations for design decisions.</p>
  <div class="doc-cards">
    <a class="doc-card" href="getting-started.html"><strong>Getting started</strong>Install loghop and initialize your first project.</a>
    <a class="doc-card" href="how-to/switch-providers.html"><strong>Switch providers</strong>Move between Claude Code and Codex without losing context.</a>
    <a class="doc-card" href="reference/commands.html"><strong>Command reference</strong>All CLI commands and options.</a>
    <a class="doc-card" href="reference/configuration.html"><strong>Configuration</strong>Project and global configuration fields.</a>
    <a class="doc-card" href="explanation/how-it-works.html"><strong>How it works</strong>The architecture behind capture, timelines, and handoffs.</a>
    <a class="doc-card" href="explanation/security-model.html"><strong>Security model</strong>How local storage, redaction, and file permissions work.</a>
  </div>
</section>
