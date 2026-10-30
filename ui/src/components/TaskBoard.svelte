<script>
  import LiveJobs from "./LiveJobs.svelte";
  import TaskCard from "./TaskCard.svelte";
  import { columnsFor, jobForTask } from "../lib/tasks.js";
  import { createTask, moveTask } from "../lib/workspace-api.js";
  import { app, refreshTasks } from "../lib/store.svelte.js";

  let { onopentask, onopenjob } = $props();

  let columns = $derived(columnsFor(app.tasks, app.taskStatuses));
  let allJobs = $derived([...app.inProgress, ...app.archived]);

  let newTitle = $state("");
  let error = $state(null);
  let dragged = null;
  let dropTarget = $state(null); // column key currently under the pointer

  async function add(event) {
    event.preventDefault();
    const title = newTitle.trim();
    if (!title) return;
    try {
      const task = await createTask({ title, prompt: "" });
      newTitle = "";
      error = null;
      await refreshTasks();
      onopentask(task); // The prompt is the point of a task, so go straight to writing it.
    } catch (failure) {
      error = failure.message;
    }
  }

  function startDrag(event, task) {
    dragged = task;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(task.id)); // Firefox needs data to start a drag.
  }

  async function drop(event, column) {
    event.preventDefault();
    dropTarget = null;
    if (!dragged) return;
    const task = dragged;
    dragged = null;
    if (task.status === column.key) return;
    try {
      await moveTask(task.id, column.key);
      error = null;
    } catch (failure) {
      error = failure.message;
    }
    await refreshTasks();
  }
</script>

<LiveJobs jobs={app.inProgress} onopen={onopenjob} />

<form class="task-add" onsubmit={add}>
  <label class="visually-hidden" for="new-task-title">New task title</label>
  <input id="new-task-title" class="task-add-input" type="text" placeholder="Add a task and press Enter" bind:value={newTitle} autocomplete="off" />
  <button class="task-add-button" type="submit" disabled={!newTitle.trim()}>Add task</button>
</form>

{#if error || app.tasksError}
  <div class="card-warning connection-lost" role="alert">{error || app.tasksError}</div>
{/if}

<div class="task-grid">
  {#each columns as column (column.key)}
    <!-- The column is the drop target; the cards inside stay real buttons. -->
    <section
      class="task-column"
      class:drop={dropTarget === column.key}
      aria-label={column.name}
      ondragover={(event) => { event.preventDefault(); dropTarget = column.key; }}
      ondragleave={() => { if (dropTarget === column.key) dropTarget = null; }}
      ondrop={(event) => drop(event, column)}
    >
      <div class="column-header">
        <span>{column.name}</span>
        <span class="column-count">{column.tasks.length}</span>
      </div>
      {#if column.tasks.length === 0}
        <div class="column-empty">{column.key === "backlog" ? "Add a task above" : "—"}</div>
      {:else}
        {#each column.tasks as task (task.id)}
          <TaskCard {task} linkedJob={jobForTask(task, allJobs)} onopen={onopentask} ondragstart={startDrag} />
        {/each}
      {/if}
    </section>
  {/each}
</div>

<style>
  .task-add { display: flex; gap: 8px; margin: 0 0 16px; max-width: 560px; }
  .task-add-input {
    flex: 1;
    min-width: 0;
    padding: 8px 11px;
    font: inherit;
    font-size: 13px;
    color: var(--ink);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
  }
  .task-add-input::placeholder { color: var(--muted); }
  .task-add-input:focus-visible { border-color: var(--focus); }
  .task-add-button {
    padding: 0 14px;
    font: inherit;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--surface);
    background: var(--ink);
    border: 1px solid var(--line-strong);
    border-radius: 8px;
    cursor: pointer;
    transition: opacity 150ms ease;
  }
  .task-add-button:hover:not(:disabled) { opacity: 0.85; }
  .task-add-button:disabled { opacity: 0.4; cursor: not-allowed; }

  .task-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px;
    align-items: start;
  }
  .task-column {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
    min-height: 120px;
    padding: 0 0 8px;
    border-radius: 9px;
    transition: background 150ms ease;
  }
  .task-column.drop { background: var(--surface-sunken); outline: 1px dashed var(--line-strong); outline-offset: 2px; }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
