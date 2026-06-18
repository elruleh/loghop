---
layout: landing
title: loghop demo
description: Watch the loghop quickstart video demo.
---

<section class="shell hero">
  <div>
    <div class="eyebrow">Quickstart demo</div>
    <h1>Watch loghop in action.</h1>
    <p class="lead">This short demo shows the core flow: set the goal, check the timeline, review sessions, and hand off cleanly to the next run.</p>
    <div class="actions">
      <a class="button primary" href="{{ '/img/demo/loghop-quickstart.mp4' | relative_url }}">Open MP4</a>
      <a class="button secondary" href="{{ '/img/demo/loghop-quickstart.gif' | relative_url }}">Open GIF</a>
    </div>
  </div>
  <div class="terminal" aria-label="loghop quickstart video demo">
    <video controls autoplay muted loop playsinline preload="metadata" poster="{{ '/img/demo/loghop-quickstart.gif' | relative_url }}" style="width:100%;height:auto;display:block;border-radius:12px;">
      <source src="{{ '/img/demo/loghop-quickstart.mp4' | relative_url }}" type="video/mp4">
      <img src="{{ '/img/demo/loghop-quickstart.gif' | relative_url }}" alt="loghop quickstart demo">
    </video>
  </div>
</section>

<section class="shell section">
  <h2>What the demo shows</h2>
  <div class="grid two">
    <article class="card"><h3>Goal</h3><p>Set the project goal once and keep it attached to the repo.</p></article>
    <article class="card"><h3>Timeline</h3><p>Track the project state across sessions and providers.</p></article>
    <article class="card"><h3>Sessions</h3><p>Browse previous runs without digging through scattered transcripts.</p></article>
    <article class="card"><h3>Handoffs</h3><p>Export context so the next assistant can resume quickly.</p></article>
  </div>
</section>
