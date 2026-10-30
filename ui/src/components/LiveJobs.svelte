<script>
  import { isWaitingOnHuman } from "../lib/jobs.js";
  import { jobKey } from "../lib/store.svelte.js";

  let { jobs, onopen } = $props();

  // Archived jobs are not live; the strip shows what the factory is doing right now.
  let running = $derived(jobs.filter((job) => job.stage !== "abandoned"));
</script>

<section class="live" aria-label="Running factory jobs">
  <h2 class="live-title">Running now <span class="live-count">{running.length}</span></h2>
  {#if running.length === 0}
    <p class="live-empty">No jobs are running. Copy a task's prompt into a factory session to start one.</p>
  {:else}
    <ul class="live-list">
      {#each running as job (jobKey(job))}
        <li>
          <button type="button" class="live-job" class:attention={isWaitingOnHuman(job)} onclick={() => onopen(job)}>
            <span class="live-job-title">{job.title}</span>
            <span class="live-job-meta">
              <span class="live-job-id">{job.id}</span>
              {#if isWaitingOnHuman(job)}
                <span class="live-job-wait">needs you</span>
              {:else}
                <span class="live-job-stage">{job.stage}</span>
              {/if}
            </span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .live { margin: 0 0 22px; }
  .live-title {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 9px;
    font-size: 12px;
    font-weight: 650;
    color: var(--ink-soft);
  }
  .live-count {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    background: var(--surface-sunken);
    border-radius: 100px;
    padding: 1px 7px;
  }
  .live-empty { margin: 0; font-size: 12.5px; color: var(--muted); }
  .live-list {
    display: flex;
    gap: 8px;
    margin: 0;
    padding: 0 0 4px;
    list-style: none;
    overflow-x: auto;
  }
  .live-list li { flex: none; }
  .live-job {
    display: flex;
    flex-direction: column;
    gap: 3px;
    width: 232px;
    padding: 8px 11px;
    text-align: left;
    font: inherit;
    color: inherit;
    cursor: pointer;
    background: var(--surface-sunken);
    border: 1px solid var(--line);
    border-radius: 8px;
    transition: border-color 150ms ease, background 150ms ease;
  }
  .live-job:hover { border-color: var(--line-strong); background: var(--surface-hover); }
  .live-job.attention { background: var(--human-bg); border-color: var(--human-line); }
  .live-job-title {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .live-job-meta { display: flex; align-items: center; gap: 7px; font-size: 11px; color: var(--muted); min-width: 0; }
  .live-job-id {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 10.5px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .live-job-wait { color: var(--human); font-weight: 650; white-space: nowrap; }
  .live-job-stage { white-space: nowrap; }
</style>
