<script>
  import { githubIssueLink } from "../lib/jobs.js";

  let { job } = $props();
  let link = $derived(githubIssueLink(job));
</script>

{#if link}
  <a class="issue-link" href={link.href} target="_blank" rel="noopener noreferrer" title={link.label} aria-label="Open issue {link.label} on GitHub (opens in a new tab)">
    <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/></svg>
    <span class="issue-repo">{link.repo}</span><span class="issue-num">{link.number}</span>
  </a>
{/if}
