<script>
  import JobCard from "./JobCard.svelte";
  import { groupByStage, isHumanStage } from "../lib/jobs.js";
  import { jobKey } from "../lib/store.svelte.js";

  let { jobs, onopen } = $props();
  let columns = $derived(groupByStage(jobs));
</script>

<div class="pipeline-grid">
  {#each columns as column (column.key)}
    <div class="pipeline-column">
      <div class="column-header" class:attention={isHumanStage(column.key) && column.jobs.length > 0}>
        <span>{column.name}</span>
        <span class="column-count">{column.jobs.length}</span>
      </div>
      {#if column.jobs.length === 0}
        <div class="column-empty">—</div>
      {:else}
        <!-- Keyed, so a poll updates cards in place instead of rebuilding the column. -->
        {#each column.jobs as job (jobKey(job))}
          <JobCard {job} {onopen} />
        {/each}
      {/if}
    </div>
  {/each}
</div>
