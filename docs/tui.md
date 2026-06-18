---
layout: landing
title: loghop TUI demo
description: Watch the loghop terminal UI browsing projects and sessions.
---

<section class="shell hero">
  <div>
    <div class="eyebrow">Terminal UI demo</div>
    <h1>Watch the TUI in action.</h1>
    <p class="lead">This clip shows the real Textual interface: project registry, project drill-down, help overlay, and navigation back to the home screen.</p>
    <div class="actions">
      <a class="button primary" href="{{ '/img/demo/loghop-tui-demo.mp4' | relative_url }}">Open MP4</a>
      <a class="button secondary" href="{{ '/img/loghop-tui.svg' | relative_url }}">View static preview</a>
    </div>
  </div>
  <div class="terminal" aria-label="loghop TUI video demo">
    <video controls autoplay muted loop playsinline preload="metadata" poster="{{ '/img/demo/loghop-tui-demo-poster.png' | relative_url }}" style="width:100%;height:auto;display:block;border-radius:12px;">
      <source src="{{ '/img/demo/loghop-tui-demo.mp4' | relative_url }}" type="video/mp4">
      <img src="{{ '/img/loghop-tui.svg' | relative_url }}" alt="loghop terminal UI">
    </video>
  </div>
</section>

<section class="shell section">
  <h2>What it shows</h2>
  <div class="grid two">
    <article class="card"><h3>Home screen</h3><p>Browse registered projects and inspect status at a glance.</p></article>
    <article class="card"><h3>Project screen</h3><p>Review sessions, handoffs, filters, and the project preview pane.</p></article>
    <article class="card"><h3>Help overlay</h3><p>See the built-in keybindings and command hints.</p></article>
    <article class="card"><h3>Navigation</h3><p>Move between the home list and a project view without leaving the app.</p></article>
  </div>
</section>
