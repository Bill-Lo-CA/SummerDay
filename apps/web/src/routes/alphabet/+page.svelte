<script lang="ts">
  import { onMount } from 'svelte';
  import AudioControl from '$lib/AudioControl.svelte';

  type Letter = [upper: string, lower: string, name: string];

  let alphabet: Letter[] = [];
  let error = '';

  onMount(async () => {
    try {
      const response = await fetch('/alphabet.json');
      if (!response.ok) throw new Error(`Alphabet data returned ${response.status}`);
      alphabet = await response.json();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load the alphabet.';
    }
  });
</script>

<svelte:head><title>French alphabet · SummerDay</title></svelte:head>

<main>
  <a href="/">← Today’s lesson</a>
  <p class="eyebrow">Pronunciation reference</p>
  <h1>L’alphabet français</h1>
  <p>Listen to each recorded French letter name.</p>

  {#if error}
    <p class="notice" role="alert">{error}</p>
  {:else if !alphabet.length}
    <p class="notice">Loading alphabet…</p>
  {:else}
    <section aria-label="French alphabet">
      {#each alphabet as [upper, lower, name]}
        <article>
          <span class="glyph">{upper} <small>{lower}</small></span>
          <span lang="fr">{name}</span>
          <AudioControl src={`/media/alphabet/${upper}.wav`} label={`Play ${upper}, ${name}`} />
        </article>
      {/each}
    </section>
  {/if}
</main>

<style>
  :global(*) { box-sizing: border-box; }
  :global(body) { margin: 0; color: #183028; background: #f5f0e6; font-family: system-ui, sans-serif; }
  main { width: min(68rem, calc(100% - 2rem)); margin: auto; padding: 4rem 0; }
  a { color: #8a3c2e; }
  h1 { margin: 0 0 1rem; font-size: clamp(3rem, 9vw, 6rem); line-height: 1; }
  .eyebrow { margin: 2rem 0 .5rem; color: #a34332; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
  section { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: .8rem; margin-top: 2rem; }
  article { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: .4rem 1rem; padding: 1rem; border: 1px solid #d9d0bf; border-radius: 1rem; background: #fffdf8; }
  .glyph { font-size: 2rem; font-weight: 750; }
  .glyph small { color: #65736d; font-size: 1rem; font-weight: 400; }
  article :global(.audio-control) { grid-column: 1 / -1; }
  .notice { padding: 1rem; border-radius: .8rem; background: #fffdf8; }
</style>
