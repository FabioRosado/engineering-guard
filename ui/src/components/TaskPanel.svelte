<script>
  import Notes from "./Notes.svelte";
  import { stageLabel } from "../lib/jobs.js";
  import { COLUMN_LABELS, jobForTask } from "../lib/tasks.js";
  import { deleteTask, moveTask, updateTask } from "../lib/workspace-api.js";
  import { app, refreshTasks } from "../lib/store.svelte.js";

  let { task, onclose, onopenjob } = $props();

  // The draft belongs to this panel. The board polls every two seconds, and a poll must not
  // overwrite text being typed, so the draft resets only when a different task is opened.
  let title = $state("");
  let prompt = $state("");
  let openedId = null;
  $effect(() => {
    if (task.id !== openedId) {
      openedId = task.id;
      title = task.title;
      prompt = task.prompt;
      error = null;
      copied = false;
      linking = false;
    }
  });

  let error = $state(null);
  let copied = $state(false);
  let linking = $state(false);
  let confirmingDelete = $state(false);

  let dirty = $derived(title.trim() !== task.title || prompt !== task.prompt);
  let linkedJob = $derived(jobForTask(task, [...app.inProgress, ...app.archived]));
  // Jobs a task could be linked to: any the dashboard knows about, newest repository grouping aside.
  let linkableJobs = $derived([...app.inProgress, ...app.archived]);

  async function run(action) {
    try {
      await action();
      error = null;
    } catch (failure) {
      error = failure.message;
    }
    await refreshTasks();
  }

  const save = () => run(() => updateTask(task.id, { title: title.trim(), prompt }));
  const moveTo = (status) => run(() => moveTask(task.id, status));
  const unlink = () => run(() => updateTask(task.id, { repo_path: null, job_id: null }));
  const link = (value) => {
    linking = false;
    if (!value) return;
    const [repoPath, jobId] = JSON.parse(value);
    return run(() => updateTask(task.id, { repo_path: repoPath, job_id: jobId }));
  };
  async function remove() {
    await run(() => deleteTask(task.id));
    if (!app.tasks.some((existing) => existing.id === task.id)) onclose();
  }

  // The clipboard needs a secure context; localhost qualifies. If it is refused, say so rather
  // than showing a "Copied" that did not happen.
  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(prompt);
      copied = true;
      error = null;
      setTimeout(() => (copied = false), 2000);
    } catch (failure) {
      copied = false;
      error = "The browser refused clipboard access. Select the prompt and copy it by hand.";
    }
  }
</script>

<div class="panel-head">
  <h2 class="panel-title">Task</h2>
  <button class="modal-close" type="button" onclick={onclose} aria-label="Close task">
    <svg class="icon" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>
  </button>
</div>

<div class="panel-body">
  <label class="field-label" for="task-title">Title</label>
  <input id="task-title" class="field" type="text" bind:value={title} autocomplete="off" />

  <div class="field-row">
    <label class="field-label" for="task-prompt">Prompt</label>
    <button class="copy-button" type="button" onclick={copyPrompt} disabled={!prompt.trim()}>
      <svg class="icon" viewBox="0 0 24 24"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>
      <span aria-live="polite">{copied ? "Copied" : "Copy prompt"}</span>
    </button>
  </div>
  <textarea id="task-prompt" class="field field-prompt" rows="10" bind:value={prompt} placeholder="Write the prompt you will give the factory. Copy it when you are ready to start a session."></textarea>

  {#if error}<p class="panel-error" role="alert">{error}</p>{/if}

  <div class="panel-actions">
    <button class="save-button" type="button" onclick={save} disabled={!dirty || !title.trim()}>Save changes</button>
    {#if dirty}<span class="unsaved">Unsaved changes</span>{/if}
  </div>

  <div class="field-row">
    <label class="field-label" for="task-status">Column</label>
  </div>
  <select id="task-status" class="field" value={task.status} onchange={(event) => moveTo(event.currentTarget.value)}>
    {#each app.taskStatuses as status (status)}
      <option value={status}>{COLUMN_LABELS[status] || status}</option>
    {/each}
  </select>

  <div class="field-row"><span class="field-label">Factory job</span></div>
  {#if linkedJob}
    <div class="linked">
      <button type="button" class="linked-open" onclick={() => onopenjob(linkedJob)}>
        <span class="linked-id">{linkedJob.id}</span>
        <span class="linked-stage">{stageLabel(linkedJob)}</span>
      </button>
      <button type="button" class="link-button" onclick={unlink}>Unlink</button>
    </div>
  {:else if task.job_id}
    <div class="linked">
      <span class="linked-missing">{task.job_id} is no longer on the dashboard</span>
      <button type="button" class="link-button" onclick={unlink}>Unlink</button>
    </div>
  {:else if linking}
    <select class="field" aria-label="Choose a job" onchange={(event) => link(event.currentTarget.value)}>
      <option value="">Choose a job…</option>
      {#each linkableJobs as job (`${job.repo_path}::${job.id}`)}
        <option value={JSON.stringify([job.repo_path, job.id])}>{job.id} · {job.repository}</option>
      {/each}
    </select>
  {:else}
    <button type="button" class="link-button" onclick={() => (linking = true)} disabled={linkableJobs.length === 0}>
      {linkableJobs.length === 0 ? "No jobs to link yet" : "Link a job"}
    </button>
  {/if}

  <Notes parent={{ taskId: task.id }} heading="Notes" />

  <div class="danger-zone">
    {#if confirmingDelete}
      <span class="danger-copy">Delete this task and its notes?</span>
      <button type="button" class="danger-button" onclick={remove}>Delete</button>
      <button type="button" class="link-button" onclick={() => (confirmingDelete = false)}>Keep</button>
    {:else}
      <button type="button" class="link-button" onclick={() => (confirmingDelete = true)}>Delete task</button>
    {/if}
  </div>
</div>

<style>
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px 10px 18px;
    border-bottom: 1px solid var(--line);
  }
  .panel-title { margin: 0; font-size: 12.5px; font-weight: 620; color: var(--ink-soft); }
  .panel-body { display: flex; flex-direction: column; gap: 6px; padding: 16px 18px 24px; overflow-y: auto; min-height: 0; }
  .field-label { font-size: 11px; font-weight: 650; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
  .field-row { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; }
  .field {
    width: 100%;
    padding: 8px 10px;
    font: inherit;
    font-size: 13px;
    color: var(--ink);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
  }
  .field:focus-visible { border-color: var(--focus); }
  .field-prompt { resize: vertical; min-height: 140px; line-height: 1.55; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12.5px; }
  .field-prompt::placeholder { color: var(--muted); font-family: inherit; }
  .copy-button, .save-button, .danger-button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 11px;
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    border-radius: 7px;
    cursor: pointer;
    transition: opacity 150ms ease, background 150ms ease, border-color 150ms ease;
  }
  .copy-button { color: var(--ink-soft); background: var(--surface); border: 1px solid var(--line-strong); }
  .copy-button:hover:not(:disabled) { background: var(--surface-hover); }
  .save-button { color: var(--surface); background: var(--ink); border: 1px solid var(--line-strong); }
  .save-button:hover:not(:disabled) { opacity: 0.85; }
  .danger-button { color: var(--danger); background: var(--danger-bg); border: 1px solid var(--danger-line); }
  .copy-button:disabled, .save-button:disabled { opacity: 0.4; cursor: not-allowed; }
  .panel-actions { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
  .unsaved { font-size: 12px; color: var(--changes); }
  .panel-error { margin: 4px 0 0; font-size: 12.5px; color: var(--danger); }
  .linked { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .linked-open {
    display: inline-flex;
    gap: 8px;
    align-items: baseline;
    padding: 0;
    font: inherit;
    color: var(--human);
    background: none;
    border: none;
    cursor: pointer;
    min-width: 0;
  }
  .linked-open:hover .linked-id { text-decoration: underline; }
  .linked-id { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
  .linked-stage, .linked-missing { font-size: 12px; color: var(--muted); }
  .link-button { padding: 0; font: inherit; font-size: 12px; font-weight: 600; color: var(--link); background: none; border: none; cursor: pointer; text-align: left; }
  .link-button:hover:not(:disabled) { text-decoration: underline; }
  .link-button:disabled { color: var(--muted); cursor: default; }
  .danger-zone { display: flex; align-items: center; gap: 12px; margin-top: 22px; padding-top: 14px; border-top: 1px solid var(--line); }
  .danger-copy { font-size: 12.5px; color: var(--ink-soft); }
</style>
