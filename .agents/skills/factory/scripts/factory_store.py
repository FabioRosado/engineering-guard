#!/usr/bin/env python3
"""SQLite store for the central factory server: tasks, notes and job events.

Scope (decisions/factory-workspace.md, D52): only data that the dashboard itself creates or that
is derived from board events. Jobs, the archive and the job mirror stay in the JSON files the
server already owns; the repository's board.json remains the source of truth for job state.

The server handles one connection at a time, so this store has one writer and needs no locking
design of its own. SQL always uses bound parameters; no caller-supplied text is ever interpolated.
"""

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

# Columns of the task board, in display order. The server validates against this list, and the UI
# fetches it from the API instead of keeping a third copy next to the pipeline stage lists.
TASK_STATUSES = ("backlog", "ready", "in-progress", "done")
DEFAULT_TASK_STATUS = TASK_STATUSES[0]

# Stages in which the job waits for a person; everything else is the factory working.
HUMAN_STAGES = frozenset({"spec-review", "needs-human"})
TERMINAL_STAGES = frozenset({"abandoned"})

# Agents spawned by each stage entry. The quality gate is a script the board runs itself, not an
# agent, and the human stages spawn nothing. Reviewers: security, ux, ui, code, architecture.
# A UX/UI/architecture reviewer the board marks N/A is never spawned, so this is an upper bound for
# `review`; the stats are labelled "derived" for that reason.
AGENTS_PER_STAGE_ENTRY = {
    "spec": 1,
    "build": 1,
    "test-audit": 1,
    "review": 5,
    "stride-review": 1,
    "approver": 1,
}

_TIMESTAMP_FORMATS = ("%Y-%m-%dT%H:%M:%SZ",)


class StoreError(Exception):
    """The database cannot be used (for example it was written by a newer version)."""


class InvalidInput(ValueError):
    """The caller supplied data the store refuses; a client error."""


class NotFound(LookupError):
    """The referenced task or note does not exist."""


def parse_timestamp(value):
    """Parse the board's UTC timestamp, or an ISO 8601 one with an offset, into an aware datetime."""
    if not isinstance(value, str):
        raise InvalidInput(f"timestamp must be a string, got {type(value).__name__}")
    for timestamp_format in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, timestamp_format).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidInput(f"unparseable timestamp: {value!r}") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _clean_text(value, field, *, required):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InvalidInput(f"{field} must be text")
    value = value.strip() if field == "title" else value
    if required and not value.strip():
        raise InvalidInput(f"{field} is required")
    return value


def _check_status(status):
    if status not in TASK_STATUSES:
        raise InvalidInput(f"status must be one of {list(TASK_STATUSES)}")
    return status


class FactoryStore:
    """Owns one SQLite connection. Call close() when the server shuts down."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # The file holds specs' derived data and personal notes: keep it private to the user
        # like the JSON stores. Created before sqlite opens it so it is never briefly world-readable.
        if not self.path.exists():
            os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600))
        # The connection is opened by whichever thread starts the server and used by whichever
        # thread serves requests (the tests serve from a worker thread). That is safe only
        # because the server handles one request at a time, so access is already serialised; the
        # check would otherwise reject the same single-writer usage. If the server is ever made
        # concurrent, this store needs its own lock first.
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        try:
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self._migrate()
        except BaseException:
            # A failure after the connection opened must not leave the file held open.
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    # ----- schema --------------------------------------------------------

    def _migrate(self):
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise StoreError(
                f"{self.path} was written by a newer version (schema {version}, this code "
                f"understands {SCHEMA_VERSION}); refusing to open it"
            )
        if version < 1:
            self._create_schema_version_1()

    def _create_schema_version_1(self):
        # executescript would commit implicitly; the statements and the version bump run in one
        # explicit transaction so a half-built schema is never recorded as complete.
        statements = [
            """CREATE TABLE tasks (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   title TEXT NOT NULL,
                   prompt TEXT NOT NULL DEFAULT '',
                   status TEXT NOT NULL,
                   position INTEGER NOT NULL,
                   repo_path TEXT,
                   job_id TEXT,
                   created TEXT NOT NULL,
                   updated TEXT NOT NULL
               )""",
            """CREATE TABLE notes (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   body TEXT NOT NULL,
                   task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                   repo_path TEXT,
                   job_id TEXT,
                   created TEXT NOT NULL,
                   CHECK (
                       (task_id IS NOT NULL AND repo_path IS NULL AND job_id IS NULL)
                       OR (task_id IS NULL AND repo_path IS NOT NULL AND job_id IS NOT NULL)
                   )
               )""",
            "CREATE INDEX notes_by_task ON notes(task_id)",
            "CREATE INDEX notes_by_job ON notes(repo_path, job_id)",
            """CREATE TABLE job_events (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   repo_path TEXT NOT NULL,
                   job_id TEXT NOT NULL,
                   stage TEXT NOT NULL,
                   round INTEGER NOT NULL,
                   at TEXT NOT NULL,
                   UNIQUE (repo_path, job_id, stage, round, at)
               )""",
            "CREATE INDEX job_events_by_job ON job_events(repo_path, job_id, at)",
        ]
        with self.connection:
            for statement in statements:
                self.connection.execute(statement)
            self.connection.execute("PRAGMA user_version = 1")

    # ----- tasks ---------------------------------------------------------

    def list_tasks(self):
        rows = self.connection.execute(
            "SELECT * FROM tasks ORDER BY position, id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_task(self, task_id):
        row = self.connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise NotFound(f"task {task_id} not found")
        return dict(row)

    def _next_position(self):
        # One global sequence: a column's order is the order of its tasks' positions, so a task
        # appended to any column sorts after everything already there.
        return self.connection.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM tasks").fetchone()[0]

    def create_task(self, title, prompt="", status=DEFAULT_TASK_STATUS, repo_path=None, job_id=None):
        title = _clean_text(title, "title", required=True)
        prompt = _clean_text(prompt, "prompt", required=False)
        _check_status(status)
        now = _now_iso()
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO tasks (title, prompt, status, position, repo_path, job_id, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (title, prompt, status, self._next_position(), repo_path, job_id, now, now),
            )
        return self.get_task(cursor.lastrowid)

    _UPDATABLE_TASK_FIELDS = ("title", "prompt", "status", "repo_path", "job_id")

    def update_task(self, task_id, **fields):
        """Change only the fields given. Passing repo_path=None or job_id=None clears them."""
        self.get_task(task_id)
        unknown = set(fields) - set(self._UPDATABLE_TASK_FIELDS)
        if unknown:
            raise InvalidInput(f"cannot update {sorted(unknown)}")
        if "title" in fields:
            fields["title"] = _clean_text(fields["title"], "title", required=True)
        if "prompt" in fields:
            fields["prompt"] = _clean_text(fields["prompt"], "prompt", required=False)
        if "status" in fields:
            _check_status(fields["status"])
        if fields:
            assignments = ", ".join(f"{name} = ?" for name in fields)
            with self.connection:
                self.connection.execute(
                    f"UPDATE tasks SET {assignments}, updated = ? WHERE id = ?",
                    (*fields.values(), _now_iso(), task_id),
                )
        return self.get_task(task_id)

    def move_task(self, task_id, status, index=None):
        """Put a task in a column, at the end or at `index` within that column."""
        self.get_task(task_id)
        _check_status(status)
        column = [
            task["id"] for task in self.list_tasks()
            if task["status"] == status and task["id"] != task_id
        ]
        if index is None or index >= len(column):
            column.append(task_id)
        else:
            column.insert(max(index, 0), task_id)
        # Rewrite the whole column's positions so the new order is explicit and gap-free for it.
        base = self._next_position()
        with self.connection:
            for offset, member in enumerate(column):
                self.connection.execute(
                    "UPDATE tasks SET status = ?, position = ?, updated = ? WHERE id = ?",
                    (status, base + offset, _now_iso(), member),
                )
        return self.get_task(task_id)

    def delete_task(self, task_id):
        self.get_task(task_id)
        with self.connection:
            self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    # ----- notes ---------------------------------------------------------

    def add_note(self, body, task_id=None, repo_path=None, job_id=None):
        body = _clean_text(body, "body", required=True)
        has_task = task_id is not None
        has_job = repo_path is not None or job_id is not None
        if has_task == has_job:
            raise InvalidInput("a note belongs to exactly one task or one job")
        if has_job and (repo_path is None or job_id is None):
            raise InvalidInput("a job note needs both repo_path and job_id")
        if has_task:
            self.get_task(task_id)
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO notes (body, task_id, repo_path, job_id, created) VALUES (?, ?, ?, ?, ?)",
                (body, task_id, repo_path, job_id, _now_iso()),
            )
        return self._get_note(cursor.lastrowid)

    def _get_note(self, note_id):
        row = self.connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise NotFound(f"note {note_id} not found")
        return dict(row)

    def list_notes(self, task_id=None, repo_path=None, job_id=None):
        """Newest first. Ties on the timestamp resolve by id so the order is stable."""
        if task_id is not None:
            rows = self.connection.execute(
                "SELECT * FROM notes WHERE task_id = ? ORDER BY created DESC, id DESC", (task_id,)
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM notes WHERE repo_path = ? AND job_id = ? ORDER BY created DESC, id DESC",
                (repo_path, job_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_note(self, note_id):
        self._get_note(note_id)
        with self.connection:
            self.connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    # ----- events and stats ---------------------------------------------

    def record_events(self, repo_path, job_id, events):
        """Store the board's stage events idempotently.

        The board resends a job's whole event list on every sync, so a replay must add nothing.
        Every event is validated before any is written: a partial write would leave statistics
        that silently disagree with the board.
        """
        validated = []
        for event in events:
            stage, round_number, at = event.get("stage"), event.get("round"), event.get("at")
            if not isinstance(stage, str) or not stage:
                raise InvalidInput("event stage must be a non-empty string")
            if not isinstance(round_number, int) or isinstance(round_number, bool):
                raise InvalidInput("event round must be an integer")
            parse_timestamp(at)
            validated.append((repo_path, job_id, stage, round_number, at))
        with self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO job_events (repo_path, job_id, stage, round, at)"
                " VALUES (?, ?, ?, ?, ?)",
                validated,
            )

    def list_events(self, repo_path, job_id):
        rows = self.connection.execute(
            "SELECT stage, round, at FROM job_events WHERE repo_path = ? AND job_id = ?"
            " ORDER BY at, id",
            (repo_path, job_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def job_stats(self, repo_path, job_id, now=None):
        """Derive a job's run statistics from its events; None when it has none.

        Times are the gaps between the board's recorded transitions, so they measure when the
        board saw each stage change and not how long an agent computed (D54). A job that has not
        reached a terminal stage is measured up to `now`.
        """
        events = self.list_events(repo_path, job_id)
        if not events:
            return None
        now_time = parse_timestamp(now) if now else datetime.now(timezone.utc)

        seconds_by_stage = {}
        human_seconds = 0
        agent_seconds = 0
        for current, following in zip(events, events[1:] + [None]):
            if current["stage"] in TERMINAL_STAGES:
                break
            end = parse_timestamp(following["at"]) if following else now_time
            seconds = max(0, int((end - parse_timestamp(current["at"])).total_seconds()))
            seconds_by_stage[current["stage"]] = seconds_by_stage.get(current["stage"], 0) + seconds
            if current["stage"] in HUMAN_STAGES:
                human_seconds += seconds
            else:
                agent_seconds += seconds

        builds = [event for event in events if event["stage"] == "build"]
        last = events[-1]
        finished = last["stage"] in TERMINAL_STAGES
        end_of_job = parse_timestamp(last["at"]) if finished else now_time
        return {
            "total_seconds": max(0, int((end_of_job - parse_timestamp(events[0]["at"])).total_seconds())),
            "seconds_by_stage": seconds_by_stage,
            "human_seconds": human_seconds,
            "agent_seconds": agent_seconds,
            "rounds": len({event["round"] for event in builds}),
            "rebuilds": max(0, len({event["round"] for event in builds}) - 1),
            "agents": sum(AGENTS_PER_STAGE_ENTRY.get(event["stage"], 0) for event in events),
            "finished": finished,
        }
