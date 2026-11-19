<script>
  import { abandonJob, archiveJob } from "../lib/api.js";

  // One dialog for both ways of closing a job. Archive records an approval (reason optional);
  // abandon discards unfinished work, so its reason is required.
  let { job, mode = "archive", onclose, ondone } = $props();

  const COPY = {
    archive: {
      title: "Archive",
      body: "Archiving closes an approved job as Complete and moves it to the Archive tab. The reason is recorded in the job history; code changes in the worktree are left untouched.",
      placeholder: "e.g. approved: branch, commit message and PR description generated",
      action: "Archive job",
      failure: "Could not archive",
    },
    abandon: {
      title: "Abandon",
      body: "Abandoning stops this job at its current stage and moves it to the Archive tab. It cannot be resumed. The reason is recorded in the job history; code changes in the worktree are left untouched, so you decide whether to keep them.",
      placeholder: "e.g. wrong approach, superseded by 004, session crashed",
      action: "Abandon job",
      failure: "Could not abandon",
    },
  };
  let copy = $derived(COPY[mode]);

  let reason = $state("");
  let error = $state("");
  let submitting = $state(false);

  async function submit(event) {
    event.preventDefault();
    error = "";
    if (mode === "abandon" && !reason.trim()) {
      error = "Give a reason so the job history explains why it was stopped.";
      return;
    }
    submitting = true;
    try {
      await (mode === "abandon" ? abandonJob : archiveJob)(job, reason.trim());
      ondone();
    } catch (failure) {
      error = `${copy.failure}: ${failure.message}`;
    } finally {
      submitting = false;
    }
  }
</script>

<form class="archive-prompt" onsubmit={submit}>
  <h2 class="archive-prompt-title">{copy.title} <span>{job.id}</span></h2>
  <p class="archive-prompt-copy">{copy.body}</p>
  <label class="archive-prompt-label" for="archive-reason">Reason{mode === "abandon" ? "" : " (optional)"}</label>
  <!-- svelte-ignore a11y_autofocus -->
  <textarea
    id="archive-reason"
    class="archive-prompt-input"
    rows="2"
    autofocus
    bind:value={reason}
    placeholder={copy.placeholder}
    aria-required={mode === "abandon"}
  ></textarea>
  <p class="archive-prompt-error" role="alert">{error}</p>
  <div class="archive-prompt-actions">
    <button type="button" class="archive-prompt-cancel" onclick={onclose}>Cancel</button>
    <button type="submit" class="archive-btn" class:danger={mode === "abandon"} disabled={submitting}>{copy.action}</button>
  </div>
</form>
