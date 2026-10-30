<script>
  import { onMount } from "svelte";
  import ArchiveDialog from "./components/ArchiveDialog.svelte";
  import Grouped from "./components/Grouped.svelte";
  import JobViewer from "./components/JobViewer.svelte";
  import Pipeline from "./components/Pipeline.svelte";
  import { app, jobKey, openJob, poll, startPolling, toggleTheme } from "./lib/store.svelte.js";

  let viewer = $state();
  let archiveDialog = $state();
  let archiving = $state(false);

  let job = $derived(openJob());
  let canArchive = $derived(job?.stage === "needs-human" && app.tab === "in-progress");
  let count = $derived(app.inProgress.length + app.archived.length);

  onMount(startPolling);

  // Dark mode keeps its body class so the ported stylesheet works unchanged.
  $effect(() => {
    document.body.classList.toggle("dark", app.theme === "dark");
  });

  // The native dialog owns focus handling and Escape; this keeps it in step with the state.
  $effect(() => {
    if (!viewer) return;
    if (job && !viewer.open) viewer.showModal();
    if (!job && viewer.open) viewer.close();
  });
  $effect(() => {
    if (!archiveDialog) return;
    if (archiving && !archiveDialog.open) archiveDialog.showModal();
    if (!archiving && archiveDialog.open) archiveDialog.close();
  });

  function open(selected) {
    app.openJobKey = jobKey(selected);
  }
  function close() {
    app.openJobKey = null;
    archiving = false;
  }
  async function archived() {
    close();
    await poll();
  }

  let statusText = $derived(
    app.connectionLost ? "Connection lost"
      : !app.loaded ? "Loading…"
      : count === 0 ? "No active jobs"
      : `${count} job${count === 1 ? "" : "s"} · ${app.lastUpdated?.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) ?? ""}`,
  );
</script>

<header>
  <div class="left">
    <div class="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M3 21V10l6-3 6 3 6-3v11l-6 3-6-3-6 3Z"/><path d="M9 7v11"/><path d="M15 10v11"/></svg>
    </div>
    <h1>Engineering&nbsp;Guard Factory</h1>
    <span class="status-pill" role="status">
      <span class="status-dot" class:error={app.connectionLost}></span>
      <span class="status-text">{statusText}</span>
    </span>
  </div>
  <div class="right">
    {#if app.tab === "in-progress"}
      <div class="segmented" role="group" aria-label="View">
        <button type="button" class:active={app.view === "pipeline"} aria-pressed={app.view === "pipeline"} onclick={() => (app.view = "pipeline")}>
          <svg class="icon" viewBox="0 0 24 24"><rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="10" rx="1"/><rect x="17" y="4" width="5" height="7" rx="1"/></svg>
          Pipeline
        </button>
        <button type="button" class:active={app.view === "grouped"} aria-pressed={app.view === "grouped"} onclick={() => (app.view = "grouped")}>
          <svg class="icon" viewBox="0 0 24 24"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/></svg>
          Grouped
        </button>
      </div>
    {/if}
    <button class="icon-btn" type="button" onclick={toggleTheme} aria-label="Toggle dark mode" title="Toggle dark mode">
      {#if app.theme === "dark"}
        <svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.4M12 19.1v2.4M4.6 4.6l1.7 1.7M17.7 17.7l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.6 19.4l1.7-1.7M17.7 6.3l1.7-1.7"/></svg>
      {:else}
        <svg class="icon" viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"/></svg>
      {/if}
    </button>
  </div>
</header>

<div class="tabs" role="tablist" aria-label="Jobs">
  <button type="button" role="tab" aria-selected={app.tab === "in-progress"} class="tab-button" class:active={app.tab === "in-progress"} onclick={() => (app.tab = "in-progress")}>
    In Progress<span class="tab-count">{app.inProgress.length}</span>
  </button>
  <button type="button" role="tab" aria-selected={app.tab === "archive"} class="tab-button" class:active={app.tab === "archive"} onclick={() => (app.tab = "archive")}>
    Archive<span class="tab-count">{app.archived.length}</span>
  </button>
</div>

<main>
  {#if app.connectionLost && app.loaded}
    <div class="card-warning connection-lost" role="alert">
      The factory server is not responding. Showing the last data received.
    </div>
  {/if}
  {#if app.tab === "in-progress"}
    {#if app.view === "pipeline"}
      <Pipeline jobs={app.inProgress} onopen={open} />
    {:else}
      <Grouped jobs={app.inProgress} onopen={open} />
    {/if}
  {:else}
    {#if app.archiveError}
      <div class="card-warning connection-lost" role="alert">The archive could not be loaded: {app.archiveError}</div>
    {/if}
    <Grouped jobs={app.archived} onopen={open} />
  {/if}
</main>

<dialog bind:this={viewer} onclose={() => { if (job) close(); }} onclick={(event) => { if (event.target === viewer) close(); }}>
  {#if job}
    <JobViewer {job} {canArchive} onclose={close} onarchive={() => (archiving = true)} />
  {/if}
</dialog>

<dialog bind:this={archiveDialog} class="archive-dialog" onclose={() => (archiving = false)} onclick={(event) => { if (event.target === archiveDialog) archiving = false; }}>
  {#if archiving && job}
    <ArchiveDialog {job} onclose={() => (archiving = false)} ondone={archived} />
  {/if}
</dialog>
