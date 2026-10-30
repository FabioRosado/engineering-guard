<script>
  import { fetchJobStats } from "../lib/workspace-api.js";
  import { statLines } from "../lib/tasks.js";

  let { job } = $props();

  // `undefined` while loading, `null` when the board has recorded no events for this job.
  let stats = $state(undefined);
  let error = $state(null);

  // Stats are derived from events the board sends on each stage change, so they are refreshed
  // when the job's stage or update time changes (the poll delivers those), not on a timer.
  let requestedFor = null;
  $effect(() => {
    const key = `${job.repo_path}::${job.id}::${job.stage}::${job.updated}`;
    if (key === requestedFor) return;
    requestedFor = key;
    fetchJobStats(job).then(
      (result) => { stats = result; error = null; },
      (failure) => { error = failure.message; },
    );
  });

  let lines = $derived(stats ? statLines(stats) : null);
</script>

<div class="stats">
  {#if error}
    <p class="stats-message stats-error" role="alert">{error}</p>
  {:else if stats === undefined}
    <p class="stats-message">Loading…</p>
  {:else if stats === null}
    <p class="stats-message">
      No timing was recorded for this job. Timing starts with jobs run after the board began
      recording stage changes, so older jobs have none.
    </p>
  {:else}
    <p class="stats-status">{lines.status}</p>
    <dl class="stats-summary">
      {#each lines.summary as { label, value } (label)}
        <div class="stat">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      {/each}
    </dl>

    <h3 class="stats-heading">Time in each stage</h3>
    <ul class="stage-list">
      {#each lines.stages as stage (stage.stage)}
        <li class="stage-row">
          <span class="stage-name">{stage.label}</span>
          <span class="stage-bar" aria-hidden="true"><span class="stage-fill" style:width="{Math.max(stage.share * 100, 1)}%"></span></span>
          <span class="stage-time">{stage.value}</span>
        </li>
      {/each}
    </ul>

    <p class="stats-note">
      Times are measured between the board's recorded stage changes, so they show when each stage
      began and ended, not how long an agent computed. Agents run is derived from the stages a job
      passed through, and counts all five reviewers each round even if one was marked N/A.
    </p>
  {/if}
</div>

<style>
  .stats { max-width: 640px; }
  @media (max-width: 560px) { .stats-summary { grid-template-columns: repeat(2, 1fr); } .stage-row { grid-template-columns: 88px 1fr 60px; gap: 8px; } }
  .stats-message { margin: 0; font-size: 14px; line-height: 1.6; color: var(--muted); max-width: 60ch; }
  .stats-error { color: var(--danger); }
  .stats-status { margin: 0 0 14px; font-size: 12px; font-weight: 650; color: var(--ink-soft); }
  .stats-summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1px;
    margin: 0 0 26px;
    background: var(--line);
    border: 1px solid var(--line);
    border-radius: 9px;
    overflow: hidden;
  }
  .stat { display: flex; flex-direction: column; gap: 3px; padding: 11px 13px; background: var(--surface); }
  .stat dt { font-size: 11px; font-weight: 600; color: var(--muted); }
  .stat dd { margin: 0; font-size: 17px; font-weight: 650; letter-spacing: -0.01em; color: var(--ink); font-variant-numeric: tabular-nums; }
  .stats-heading { margin: 0 0 10px; font-size: 13px; font-weight: 650; color: var(--ink); }
  .stage-list { display: flex; flex-direction: column; gap: 8px; margin: 0 0 22px; padding: 0; list-style: none; }
  .stage-row { display: grid; grid-template-columns: 110px 1fr 70px; align-items: center; gap: 12px; font-size: 13px; }
  .stage-name { color: var(--ink-soft); }
  .stage-bar { height: 6px; background: var(--surface-sunken); border-radius: 3px; overflow: hidden; }
  .stage-fill { display: block; height: 100%; background: var(--ink-soft); border-radius: 3px; }
  .stage-time { text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
  .stats-note { margin: 0; font-size: 12px; line-height: 1.55; color: var(--muted); max-width: 62ch; }
</style>
