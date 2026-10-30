<script>
  import { archiveJob } from "../lib/api.js";

  let { job, onclose, ondone } = $props();

  let reason = $state("");
  let error = $state("");
  let submitting = $state(false);

  async function submit(event) {
    event.preventDefault();
    error = "";
    submitting = true;
    try {
      await archiveJob(job, reason.trim());
      ondone();
    } catch (failure) {
      error = `Could not archive: ${failure.message}`;
    } finally {
      submitting = false;
    }
  }
</script>

<form class="archive-prompt" onsubmit={submit}>
  <h2 class="archive-prompt-title">Archive <span>{job.id}</span></h2>
  <p class="archive-prompt-copy">
    Archiving closes an approved job and moves it to the Archive tab. The reason is recorded in the
    job history; code changes in the worktree are left untouched.
  </p>
  <label class="archive-prompt-label" for="archive-reason">Reason</label>
  <!-- svelte-ignore a11y_autofocus -->
  <textarea
    id="archive-reason"
    class="archive-prompt-input"
    rows="2"
    autofocus
    bind:value={reason}
    placeholder="e.g. approved: branch, commit message and PR description generated"
  ></textarea>
  <p class="archive-prompt-error" role="alert">{error}</p>
  <div class="archive-prompt-actions">
    <button type="button" class="archive-prompt-cancel" onclick={onclose}>Cancel</button>
    <button type="submit" class="archive-btn" disabled={submitting}>Archive job</button>
  </div>
</form>
