<script>
  import Markdown from "./Markdown.svelte";
  import Overview from "./Overview.svelte";
  import { initialFile, orderFiles, OVERVIEW } from "../lib/jobs.js";
  import { splitVerdict } from "../lib/markdown.js";

  let { job, canArchive, onclose, onarchive } = $props();

  let files = $derived(job.files && !Array.isArray(job.files) ? job.files : {});
  let fileNames = $derived(orderFiles(Object.keys(files)));
  let hasOverview = $derived("handover.md" in files);

  // The selected tab belongs to this viewer. It resets when a different job is opened, but a poll
  // that refreshes the same job must not move the reader off the file they chose.
  let selected = $state(null);
  let openedJobId = null;
  $effect(() => {
    const key = `${job.repo_path}::${job.id}`;
    if (key !== openedJobId) {
      openedJobId = key;
      selected = initialFile(Object.keys(files));
    }
  });
  // If the selected file vanished (it should not), fall back instead of showing nothing.
  let current = $derived(
    selected === OVERVIEW ? (hasOverview ? OVERVIEW : fileNames[0] ?? null)
      : selected in files ? selected : (hasOverview ? OVERVIEW : fileNames[0] ?? null),
  );
  let parsed = $derived(current && current !== OVERVIEW ? splitVerdict(files[current]) : null);
</script>

<div class="modal-header">
  <span class="modal-title">{job.id} — {job.title}</span>
  <div class="modal-header-actions">
    {#if canArchive}
      <button class="archive-btn" type="button" onclick={onarchive}>
        <svg class="icon" viewBox="0 0 24 24"><path d="M4 7h16M6 7v12a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M10 11v5M14 11v5"/></svg>
        Archive job
      </button>
    {/if}
    <button class="modal-close" type="button" onclick={onclose} aria-label="Close">
      <svg class="icon" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>
    </button>
  </div>
</div>

<div class="modal-body">
  <nav class="file-tabs" aria-label="Job files">
    {#if hasOverview}
      <button type="button" class="file-tab" class:active={current === OVERVIEW} onclick={() => (selected = OVERVIEW)}>Overview</button>
    {/if}
    {#each fileNames as name (name)}
      <button type="button" class="file-tab" class:active={current === name} onclick={() => (selected = name)}>{name}</button>
    {/each}
  </nav>

  <div class="viewer-content">
    {#if current === null}
      <div class="markdown"><p>This job has no files yet.</p></div>
    {:else if current === OVERVIEW}
      <Overview {job} handover={files["handover.md"]} decision={files["decision.md"]} />
    {:else}
      {#if parsed.verdict}<span class="verdict {parsed.verdict}">{parsed.label}</span>{/if}
      <Markdown source={parsed.verdict ? parsed.body : files[current]} />
    {/if}
  </div>
</div>
