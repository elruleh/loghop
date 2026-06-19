---
layout: landing
title: loghop dashboard demo
description: Watch the loghop CLI dashboard show repo state, goal and last session.
---

<section class="shell hero">
  <div>
    <div class="eyebrow">Dashboard demo</div>
    <h1>The first thing you see when you run <code>loghop</code>.</h1>
    <p class="lead">Plain output: the project goal, the last session, the default provider. The full Textual TUI is available via <code>loghop tui</code>; a static preview lives below.</p>
    <div class="actions">
      <a class="button primary" href="{{ '/img/demo/loghop-dashboard-demo.mp4' | relative_url }}">Open MP4</a>
      <a class="button secondary" href="{{ '/img/loghop-tui.svg' | relative_url }}">View TUI preview</a>
    </div>
  </div>
  <div class="terminal" aria-label="loghop dashboard video demo">
    <video controls autoplay muted loop playsinline preload="metadata" poster="{{ '/img/demo/loghop-dashboard-demo-poster.png' | relative_url }}" style="width:100%;height:auto;display:block;border-radius:12px;">
      <source src="{{ '/img/demo/loghop-dashboard-demo.mp4' | relative_url }}" type="video/mp4">
    </video>
  </div>
</section>

<section class="shell section">
  <h2>What the TUI looks like</h2>
  <p class="section-intro">For interactive browsing of sessions, handoffs and timelines, run <code>loghop tui</code>. Below is a static preview of the home and project screens.</p>
  <div class="grid two">
    <img src="{{ '/img/loghop-tui.svg' | relative_url }}" alt="loghop TUI preview" style="width:100%;height:auto;border-radius:14px;border:1px solid rgba(125,211,252,.18);">
  </div>
</section>

<section class="shell section">
  <h2>Two ways to view loghop</h2>
  <div class="grid">
    <article class="card">
      <h3>Plain dashboard</h3>
      <p>Single-screen summary rendered by Rich. Reads like a report. Works everywhere — pipes, logs, CI.</p>
      <p><code>loghop</code> &middot; <code>loghop --plain</code></p>
    </article>
    <article class="card">
      <h3>Textual TUI</h3>
      <p>Interactive app for browsing projects, sessions, handoffs and timelines. Keybindings shown in the help overlay (<code>?</code>).</p>
      <p><code>pipx install 'loghop[tui]'</code> &middot; <code>loghop tui</code></p>
    </article>
  </div>
</section>
