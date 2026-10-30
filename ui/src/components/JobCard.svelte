<script>
  import Chip from "./Chip.svelte";
  import { gateVerdict, isWaitingOnHuman, reviewChips } from "../lib/jobs.js";

  let { job, onopen } = $props();

  let waiting = $derived(isWaitingOnHuman(job));
  let chips = $derived(reviewChips(job.reviews));
  let showRound = $derived(job.round && (job.test_audit || chips.length));
</script>

<!-- A real button, so the card is reachable and operable from the keyboard. -->
<button type="button" class="card" class:attention={waiting} onclick={() => onopen(job)}>
  <span class="card-top">
    <span class="card-id">{job.id}</span>
    {#if waiting}
      <span class="human-flag" title="Needs human decision">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 21V4"/><path d="M5 5h13l-3 4 3 4H5"/></svg>
      </span>
    {/if}
  </span>
  <span class="card-title">{job.title}</span>
  {#if job.repo_path || job.worktree_path}
    <span class="card-path">{job.repo_path || job.worktree_path}</span>
  {/if}
  <span class="card-stage">{job.stage}</span>

  {#if showRound}
    {#if job.test_audit}
      <span class="card-round"><span class="round-label">R{job.round}</span><Chip name="tests" verdict={job.test_audit} /></span>
    {/if}
    {#if chips.length}
      <span class="card-round">
        {#if !job.test_audit}<span class="round-label">R{job.round}</span>{/if}
        {#each chips as chip (chip.name)}<Chip name={chip.name} verdict={chip.verdict} />{/each}
      </span>
    {/if}
  {/if}

  {#if job.stride}
    <span class="card-round"><span class="round-label">STRIDE</span><Chip name="stride" verdict={job.stride} /></span>
  {/if}
  {#if job.quality_gate}
    <span class="card-round"><span class="round-label">GATE</span><Chip name="gate" verdict={gateVerdict(job.quality_gate)} /></span>
  {/if}

  {#each job.warnings || [] as warning}
    <span class="card-warning">
      <svg class="icon" viewBox="0 0 24 24" style="width:13px;height:13px"><path d="M12 3.5 2.5 20h19L12 3.5Z"/><path d="M12 10v4.2"/><circle cx="12" cy="17.3" r="0.4" fill="currentColor" stroke="none"/></svg>
      <span>{warning}</span>
    </span>
  {/each}
</button>

<style>
  /* The shared card look lives in global.css; a button needs its native chrome removed. */
  .card { font: inherit; color: inherit; text-align: left; width: 100%; }
  .card > :global(span) { display: block; }
  .card > .card-top, .card > .card-round, .card > .card-warning { display: flex; }
  .card > .card-stage { display: inline-flex; }
</style>
