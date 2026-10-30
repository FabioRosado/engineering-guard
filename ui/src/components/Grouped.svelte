<script>
  import JobCard from "./JobCard.svelte";
  import { groupByRepository } from "../lib/jobs.js";
  import { jobKey } from "../lib/store.svelte.js";

  let { jobs, onopen } = $props();
  let groups = $derived(groupByRepository(jobs));
</script>

{#if jobs.length === 0}
  <div class="empty-state">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M8.5 12h7"/></svg>
    <span>No jobs to show</span>
  </div>
{:else}
  {#each groups as [repository, repositoryJobs] (repository)}
    <section class="repo-group">
      <h2 class="repo-header">
        <svg class="icon" viewBox="0 0 24 24"><path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H16l4 4v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 20V4.5Z"/><path d="M16 3v4h4"/></svg>
        {repository}
      </h2>
      <div class="jobs-grid">
        {#each repositoryJobs as job (jobKey(job))}
          <JobCard {job} {onopen} />
        {/each}
      </div>
    </section>
  {/each}
{/if}
