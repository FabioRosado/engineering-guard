<script>
  import JobStats from "./JobStats.svelte";
  import Markdown from "./Markdown.svelte";
  import Notes from "./Notes.svelte";
  import Overview from "./Overview.svelte";
  import { canAbandon, groupScopes, initialFile, scopeOf, OVERVIEW, STATS, NOTES } from "../lib/jobs.js";
  import { splitVerdict } from "../lib/markdown.js";

  let { job, canArchive, onclose, onarchive, onabandon } = $props();

  let files = $derived(job.files && !Array.isArray(job.files) ? job.files : {});
  let fileNames = $derived(Object.keys(files));
  let hasOverview = $derived("handover.md" in files);
  let scopes = $derived(groupScopes(fileNames));

  // The selected file belongs to this viewer. It resets when a different job is opened, but a poll
  // that refreshes the same job must not move the reader off the file they chose.
  let selected = $state(null);
  let openedJobId = null;
  $effect(() => {
    const key = `${job.repo_path}::${job.id}`;
    if (key !== openedJobId) {
      openedJobId = key;
      selected = initialFile(fileNames);
    }
  });

  const isPanel = (name) => name === STATS || name === NOTES;
  const firstFile = () => scopes[0]?.files[0]?.name ?? null;
  // If the selected file vanished (it should not), fall back instead of showing nothing.
  let current = $derived(
    isPanel(selected) ? selected
      : selected === OVERVIEW ? (hasOverview ? OVERVIEW : firstFile())
      : selected in files ? selected : (hasOverview ? OVERVIEW : firstFile()),
  );
  // The top bar shows which scope `current` lives in; the sidebar lists only that scope's files.
  let activeScope = $derived(
    current === OVERVIEW || isPanel(current) || current === null ? current
      : scopeOf(current),
  );
  let scopeFiles = $derived(scopes.find((scope) => scope.key === activeScope)?.files ?? []);
  let parsed = $derived(current && current !== OVERVIEW && !isPanel(current) ? splitVerdict(files[current]) : null);

  // On a narrow screen the bar scrolls; keep the active tab visible so the reader knows where they are.
  let scopeBar = $state();
  $effect(() => {
    activeScope;
    scopeBar?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  });

  // Switching scope remembers nothing: it opens that scope's first file.
  function openScope(scope) {
    selected = scope.files[0].name;
  }
</script>

<div class="modal-header">
  <span class="modal-title">{job.id} — {job.title}</span>
  <div class="modal-header-actions">
    {#if canAbandon(job)}
      <button class="abandon-btn" type="button" onclick={onabandon}>
        <svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/></svg>
        Abandon
      </button>
    {/if}
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

<nav class="scope-bar" aria-label="Job sections" bind:this={scopeBar}>
  {#if hasOverview}
    <button type="button" class="scope-tab" class:active={current === OVERVIEW} aria-current={current === OVERVIEW ? "page" : undefined} onclick={() => (selected = OVERVIEW)}>Overview</button>
  {/if}
  <button type="button" class="scope-tab" class:active={current === STATS} aria-current={current === STATS ? "page" : undefined} onclick={() => (selected = STATS)}>Stats</button>
  <button type="button" class="scope-tab" class:active={current === NOTES} aria-current={current === NOTES ? "page" : undefined} onclick={() => (selected = NOTES)}>Notes</button>
  {#if scopes.length}<span class="scope-divider" aria-hidden="true"></span>{/if}
  {#each scopes as scope (scope.key)}
    <button type="button" class="scope-tab" class:active={activeScope === scope.key} aria-current={activeScope === scope.key ? "page" : undefined} onclick={() => openScope(scope)}>
      {scope.label}
      <span class="scope-count">{scope.files.length}</span>
    </button>
  {/each}
</nav>

<div class="modal-body" class:has-sidebar={scopeFiles.length > 0}>
  {#if scopeFiles.length}
    <nav class="file-tabs" aria-label="{scopes.find((s) => s.key === activeScope)?.label} files">
      {#each scopeFiles as file (file.name)}
        <button type="button" class="file-tab" class:active={current === file.name} aria-current={current === file.name ? "page" : undefined} onclick={() => (selected = file.name)}>{file.label}</button>
      {/each}
    </nav>
  {/if}

  <div class="viewer-content">
    {#if current === STATS}
      <JobStats {job} />
    {:else if current === NOTES}
      <Notes parent={{ job }} heading="Job notes" />
    {:else if current === null}
      <div class="markdown"><p>This job has no files yet.</p></div>
    {:else if current === OVERVIEW}
      <Overview {job} handover={files["handover.md"]} decision={files["decision.md"]} />
    {:else}
      {#if parsed.verdict}<span class="verdict {parsed.verdict}">{parsed.label}</span>{/if}
      <Markdown source={parsed.verdict ? parsed.body : files[current]} />
    {/if}
  </div>
</div>
