<script>
  import { addNote, deleteNote, fetchNotes } from "../lib/workspace-api.js";

  // `parent` is { taskId } or { job }. Notes are loaded for whichever parent is current and
  // reloaded after each change; they are not polled, since only this person edits them.
  let { parent, heading = "Notes" } = $props();

  let notes = $state([]);
  let draft = $state("");
  let error = $state(null);
  let loading = $state(true);

  let parentKey = $derived(parent.taskId !== undefined ? `task:${parent.taskId}` : `job:${parent.job.repo_path}::${parent.job.id}`);

  async function load() {
    try {
      notes = await fetchNotes(parent);
      error = null;
    } catch (failure) {
      error = failure.message;
    } finally {
      loading = false;
    }
  }

  // Reload when the panel is pointed at a different task or job. The draft clears with it.
  let loadedKey = null;
  $effect(() => {
    if (parentKey !== loadedKey) {
      loadedKey = parentKey;
      notes = [];
      draft = "";
      loading = true;
      load();
    }
  });

  async function add(event) {
    event.preventDefault();
    if (!draft.trim()) return;
    try {
      await addNote(draft, parent);
      draft = "";
      await load();
    } catch (failure) {
      error = failure.message;
    }
  }

  async function remove(note) {
    try {
      await deleteNote(note.id);
      await load();
    } catch (failure) {
      error = failure.message;
    }
  }

  const when = (iso) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
</script>

<section class="notes" aria-label={heading}>
  <h3 class="notes-title">{heading}</h3>
  <form class="notes-form" onsubmit={add}>
    <label class="visually-hidden" for={`note-${parentKey}`}>Add a note</label>
    <textarea id={`note-${parentKey}`} class="notes-input" rows="2" placeholder="Add a note" bind:value={draft}></textarea>
    <button class="notes-add" type="submit" disabled={!draft.trim()}>Add note</button>
  </form>
  {#if error}<p class="notes-error" role="alert">{error}</p>{/if}
  {#if loading}
    <p class="notes-empty">Loading notes…</p>
  {:else if notes.length === 0}
    <p class="notes-empty">No notes yet.</p>
  {:else}
    <ul class="notes-list">
      {#each notes as note (note.id)}
        <li class="note">
          <!-- Plain text with preserved line breaks: a note is never interpreted as markup. -->
          <p class="note-body">{note.body}</p>
          <div class="note-meta">
            <time datetime={note.created}>{when(note.created)}</time>
            <button type="button" class="note-delete" onclick={() => remove(note)} aria-label="Delete note">Delete</button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .notes { margin-top: 20px; }
  .notes-title { margin: 0 0 8px; font-size: 11px; font-weight: 650; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
  .notes-form { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
  .notes-input {
    width: 100%;
    padding: 8px 10px;
    font: inherit;
    font-size: 13px;
    line-height: 1.5;
    color: var(--ink);
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 8px;
    resize: vertical;
  }
  .notes-input::placeholder { color: var(--muted); }
  .notes-input:focus-visible { border-color: var(--focus); }
  .notes-add {
    height: 28px;
    padding: 0 12px;
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    color: var(--ink-soft);
    background: var(--surface);
    border: 1px solid var(--line-strong);
    border-radius: 7px;
    cursor: pointer;
  }
  .notes-add:hover:not(:disabled) { background: var(--surface-hover); }
  .notes-add:disabled { opacity: 0.4; cursor: not-allowed; }
  .notes-error { margin: 6px 0 0; font-size: 12.5px; color: var(--danger); }
  .notes-empty { margin: 10px 0 0; font-size: 12.5px; color: var(--muted); }
  .notes-list { display: flex; flex-direction: column; margin: 10px 0 0; padding: 0; list-style: none; }
  .note { padding: 10px 0; border-top: 1px solid var(--line); }
  .note:first-child { border-top: none; }
  .note-body { margin: 0; font-size: 13px; line-height: 1.55; color: var(--ink-soft); white-space: pre-wrap; overflow-wrap: anywhere; }
  .note-meta { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; font-size: 11px; color: var(--muted); }
  .note-delete { padding: 0; font: inherit; font-size: 11px; color: var(--muted); background: none; border: none; cursor: pointer; }
  .note-delete:hover { color: var(--danger); text-decoration: underline; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
