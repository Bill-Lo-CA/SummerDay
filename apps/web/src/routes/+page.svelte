<script lang="ts">
  import { onMount } from 'svelte';

  type Focus = { title: string; explanation: string; evidence: string };
  type VocabularyItem = {
    lexical_item: string;
    surface_form: string;
    part_of_speech: string;
    french_definition: string;
    english_hint: string;
    source_sentence: string;
  };
  type Lesson = {
    title: string;
    level: string;
    source_title: string;
    source_url: string;
    article_text: string;
    core_vocabulary: VocabularyItem[];
    morphology_focus: Focus;
    pronunciation_focus: Focus;
  };

  let lesson: Lesson | null = null;
  let error = '';

  onMount(async () => {
    try {
      const response = await fetch('/api/lessons/today');
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      lesson = await response.json();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load today’s lesson.';
    }
  });
</script>

<svelte:head><title>Today’s French · SomeADay</title></svelte:head>

<main>
  {#if error}
    <p class="notice" role="alert">{error}</p>
  {:else if !lesson}
    <p class="notice">Loading today’s lesson…</p>
  {:else}
    <header>
      <p class="eyebrow">Today’s French · {lesson.level}</p>
      <h1>{lesson.title}</h1>
      <a href={lesson.source_url}>Source: {lesson.source_title} on Vikidia</a>
    </header>

    <article lang="fr">{lesson.article_text}</article>

    <section>
      <h2>Core vocabulary</h2>
      <div class="vocabulary">
        {#each lesson.core_vocabulary as item}
          <details>
            <summary><strong lang="fr">{item.lexical_item}</strong> <span>{item.part_of_speech}</span></summary>
            <p lang="fr">{item.french_definition}</p>
            <p class="context" lang="fr">{item.source_sentence}</p>
            <p>English hint: {item.english_hint}</p>
          </details>
        {/each}
      </div>
    </section>

    <section class="focuses">
      <div>
        <p class="eyebrow">Morphology</p>
        <h2 lang="fr">{lesson.morphology_focus.title}</h2>
        <p lang="fr">{lesson.morphology_focus.explanation}</p>
      </div>
      <div>
        <p class="eyebrow">Pronunciation</p>
        <h2 lang="fr">{lesson.pronunciation_focus.title}</h2>
        <p lang="fr">{lesson.pronunciation_focus.explanation}</p>
      </div>
    </section>
  {/if}
</main>

<style>
  :global(*) { box-sizing: border-box; }
  :global(body) { margin: 0; color: #183028; background: #f5f0e6; font-family: system-ui, sans-serif; }
  main { width: min(68rem, calc(100% - 2rem)); margin: auto; padding: 4rem 0; }
  header { margin-bottom: 2rem; }
  h1 { margin: 0; font-size: clamp(3rem, 9vw, 6rem); line-height: 1; }
  h2 { margin-top: 0; }
  a { color: #8a3c2e; }
  article { padding: 2rem; border-radius: 1.2rem; background: #fffdf8; font: 1.35rem/1.8 Georgia, serif; }
  section { margin-top: 3rem; }
  .eyebrow { margin-bottom: .5rem; color: #a34332; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
  .vocabulary { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: .8rem; }
  details, .focuses > div { padding: 1.2rem; border: 1px solid #d9d0bf; border-radius: 1rem; background: #fffdf8; }
  summary { cursor: pointer; }
  summary span { float: right; color: #65736d; font-size: .85rem; }
  .context { color: #586760; font-style: italic; }
  .focuses { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 1rem; }
  .notice { padding: 1rem; border-radius: .8rem; background: #fffdf8; }
</style>

