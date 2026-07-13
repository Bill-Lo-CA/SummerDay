<script lang="ts">
  import { onDestroy } from 'svelte';
  import { claim, release } from './audio-controller';

  export let src: string | null = null;
  export let label: string;

  let audio: HTMLAudioElement;
  let state: 'idle' | 'playing' | 'error' = 'idle';

  function toggle() {
    if (!audio || !src) return;
    if (audio.paused) {
      claim(audio);
      audio.play().catch(() => (state = 'error'));
    } else {
      audio.pause();
    }
  }

  function handlePlay() {
    claim(audio);
    state = 'playing';
  }

  function handlePause() {
    release(audio);
    state = 'idle';
  }

  function handleError() {
    release(audio);
    state = 'error';
  }

  onDestroy(() => release(audio));
</script>

<span class="audio-control">
  {#if src}
    <audio bind:this={audio} {src} preload="none" on:play={handlePlay} on:pause={handlePause} on:ended={handlePause} on:error={handleError}></audio>
  {/if}
  <button type="button" disabled={!src || state === 'error'} aria-label={label} on:click={toggle}>
    {state === 'playing' ? 'Pause' : 'Play'}
  </button>
  {#if !src}
    <small>Audio unavailable</small>
  {:else if state === 'error'}
    <small role="alert">Playback error</small>
  {/if}
</span>

<style>
  .audio-control { display: inline-flex; align-items: center; gap: .5rem; }
  button { padding: .35rem .7rem; border: 1px solid #8a3c2e; border-radius: 999px; color: #8a3c2e; background: #fffdf8; cursor: pointer; }
  button:disabled { cursor: not-allowed; opacity: .55; }
  small { color: #65736d; }
</style>
