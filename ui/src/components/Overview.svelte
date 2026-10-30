<script>
  import Chip from "./Chip.svelte";
  import Markdown from "./Markdown.svelte";
  import { gateVerdict, reviewChips } from "../lib/jobs.js";
  import { splitVerdict } from "../lib/markdown.js";

  let { job, handover, decision } = $props();

  let chips = $derived(reviewChips(job.reviews));
  // decision.md is a pointer now, so only its recommendation line belongs on the Overview.
  let recommendation = $derived(extractRecommendation(decision));

  function extractRecommendation(text) {
    if (!text) return null;
    const { body } = splitVerdict(text);
    const match = body.match(/^##\s*Recommendation\s*\n+([^\n]+)/m);
    return match ? match[1].trim() : null;
  }
</script>

<div class="overview-status" aria-label="Job status">
  <span class="round-label">{job.stage}{job.round ? ` · round ${job.round}` : ""}</span>
  {#if job.test_audit}<Chip name="tests" verdict={job.test_audit} />{/if}
  {#each chips as chip (chip.name)}<Chip name={chip.name} verdict={chip.verdict} />{/each}
  {#if job.stride}<Chip name="stride" verdict={job.stride} />{/if}
  {#if job.quality_gate}<Chip name="gate" verdict={gateVerdict(job.quality_gate)} />{/if}
</div>

{#if job.warnings?.length}
  <div class="overview-warnings">
    {#each job.warnings as warning}
      <span class="card-warning">
        <svg class="icon" viewBox="0 0 24 24" style="width:13px;height:13px"><path d="M12 3.5 2.5 20h19L12 3.5Z"/><path d="M12 10v4.2"/><circle cx="12" cy="17.3" r="0.4" fill="currentColor" stroke="none"/></svg>
        <span>{warning}</span>
      </span>
    {/each}
  </div>
{/if}

{#if recommendation}
  <p class="overview-recommendation"><strong>Recommendation:</strong> {recommendation}</p>
{/if}

<div class="overview-document"><Markdown source={handover} /></div>
