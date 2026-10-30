<script>
  import { promptPreview } from "../lib/tasks.js";

  let { task, linkedJob, onopen, ondragstart } = $props();

  let preview = $derived(promptPreview(task.prompt, 110));
</script>

<!-- A real button so the card can be reached and opened from the keyboard. Dragging is a
     convenience for the mouse; every move is also available from the task panel. -->
<button
  type="button"
  class="task-card"
  draggable="true"
  onclick={() => onopen(task)}
  ondragstart={(event) => ondragstart(event, task)}
>
  <span class="task-title">{task.title}</span>
  {#if preview}
    <span class="task-preview">{preview}</span>
  {:else}
    <span class="task-preview task-preview-empty">No prompt yet</span>
  {/if}
  {#if linkedJob}
    <span class="task-link" title="Linked factory job">
      <svg class="icon" viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1"/></svg>
      <span class="task-link-id">{linkedJob.id}</span>
      <span class="task-link-stage">{linkedJob.stage}</span>
    </span>
  {/if}
</button>

<style>
  .task-card {
    display: flex;
    flex-direction: column;
    gap: 5px;
    width: 100%;
    padding: 10px 11px;
    text-align: left;
    font: inherit;
    color: inherit;
    cursor: pointer;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 9px;
    transition: border-color 150ms ease, background 150ms ease;
  }
  .task-card:hover { border-color: var(--line-strong); background: var(--surface-hover); }
  .task-card:active { background: var(--surface-sunken); }
  .task-title { font-size: 13px; font-weight: 620; line-height: 1.35; color: var(--ink); }
  .task-preview {
    font-size: 12px;
    line-height: 1.45;
    color: var(--muted);
    overflow-wrap: anywhere;
  }
  .task-preview-empty { font-style: italic; }
  .task-link {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 2px;
    font-size: 11px;
    color: var(--human);
    min-width: 0;
  }
  .task-link-id {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 10.5px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .task-link-stage { color: var(--muted); }
</style>
