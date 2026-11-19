<script>
  import Chip from "./Chip.svelte";
  import IssueLink from "./IssueLink.svelte";
  import { gateVerdict, githubIssueLink, isWaitingOnHuman, repositoryName, reviewChips, stageLabel } from "../lib/jobs.js";

  // The grouped view already titles each section with the repository, so it hides the line.
  let { job, onopen, showRepository = true } = $props();

  let repository = $derived(showRepository ? repositoryName(job) : null);
  let hasIssue = $derived(githubIssueLink(job) !== null);

  let waiting = $derived(isWaitingOnHuman(job));
  let chips = $derived(reviewChips(job.reviews));
  let showRound = $derived(job.round && (job.test_audit || chips.length));
</script>

<!-- A real button, so the card is reachable and operable from the keyboard. The issue link is its
     sibling, not a child: a link inside a button is invalid and would also open the job. -->
<div class="card-wrap">
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
  {#if repository}
    <span class="card-path" title={job.repo_path || job.worktree_path || repository}>{repository}</span>
  {/if}
  <span class="card-stage">{stageLabel(job)}</span>

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
  {#if hasIssue}<span class="card-issue-space" aria-hidden="true"></span>{/if}
</button>
{#if hasIssue}
  <span class="card-issue"><IssueLink {job} /></span>
{/if}
</div>

<style>
  /* The wrapper is the grid/flex item, so it stretches; the card fills it so heights stay equal
     in a row and the link stays inside the card border. */
  .card-wrap { position: relative; display: flex; flex-direction: column; transition: transform 140ms ease; }
  .card-wrap > .card { flex: 1; }
  .card-wrap:hover { transform: translateY(-1px); }
  .card-wrap:active { transform: translateY(0); }
  /* The wrapper lifts as one piece so the link keeps its place on the card. */
  .card-wrap .card:hover, .card-wrap .card:active { transform: none; }
  /* The hover look follows the wrapper, so it does not drop while the pointer is over the link. */
  .card-wrap:hover > .card { border-color: var(--line-strong); box-shadow: var(--shadow-float); }
  .card-wrap:hover > .card.attention { border-color: var(--human-line); box-shadow: var(--shadow-float), 0 0 0 1px var(--human-line); }
  /* Room at the bottom of the card for the link, which sits over it rather than inside the button.
     The card's content box starts 13px from the left and ends 12px from the bottom (border + padding). */
  .card > .card-issue-space { height: 16px; margin-top: -2px; }
  .card-issue { position: absolute; left: 13px; bottom: 12px; height: 16px; max-width: calc(100% - 26px); display: flex; }
  /* The shared card look lives in global.css; a button needs its native chrome removed. */
  .card { font: inherit; color: inherit; text-align: left; width: 100%; }
  .card > :global(span) { display: block; }
  .card > .card-top, .card > .card-round, .card > .card-warning { display: flex; }
  .card > .card-stage { display: inline-flex; }
</style>
