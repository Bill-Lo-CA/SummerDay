<svelte:head><title>SummerDay</title></svelte:head>

<main>
  <p class="eyebrow">French practise</p>
  <h1>SummerDay</h1>
  <p class="intro">Choose what to practise today.</p>

  <section class="calendar" aria-label="Learning calendar">
    <a class="today" href="/today">
      <span>Today</span>
      <strong>Today’s French lesson</strong>
      <small>Open today’s reading, vocabulary, and listening practise →</small>
    </a>
  </section>

  <section class="reference" aria-labelledby="reference-heading">
    <p class="eyebrow">Reference</p>
    <h2 id="reference-heading">French alphabet</h2>
    <p>Listen to each recorded French letter name.</p>
    <a href="/alphabet">Open alphabet pronunciation →</a>
  </section>
</main>

<style>
  :global(*) { box-sizing: border-box; }
  :global(body) { margin: 0; color: #183028; background: #f5f0e6; font-family: system-ui, sans-serif; }
  main { width: min(48rem, calc(100% - 2rem)); margin: auto; padding: 4rem 0; }
  h1 { margin: 0; font-size: clamp(3rem, 9vw, 6rem); line-height: 1; }
  h2 { margin: 0; font-size: 2rem; }
  a { color: #8a3c2e; }
  .intro { margin: 1rem 0 2rem; color: #586760; font-size: 1.2rem; }
  .eyebrow { margin: 0 0 .5rem; color: #a34332; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
  .calendar, .reference { margin-top: 2rem; padding: 1.2rem; border: 1px solid #d9d0bf; border-radius: 1rem; background: #fffdf8; }
  .today { display: grid; gap: .4rem; color: inherit; text-decoration: none; }
  .today:hover strong, .today:focus-visible strong { color: #8a3c2e; text-decoration: underline; }
  .today span { color: #a34332; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
  .today strong { font-size: 1.5rem; }
  .today small { color: #586760; }
  .reference p:not(.eyebrow) { color: #586760; }
</style>
