#!/usr/bin/env python3
"""Central factory server: aggregates job state from multiple repositories.

Runs independently at a fixed location. Factories push job updates here when
state changes. Dashboard polls this server to display all in-progress and
archived jobs across repositories.

Server listens on 127.0.0.1:5173 (local-only). Job data stored in
~/.engineering-guard-factory/ as simple JSON files (no database required).
"""

import argparse
import http.server
import json
import mimetypes
import os
import re
import socketserver
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

# Configuration
SERVER_PORT = 5173
SERVER_HOST = "127.0.0.1"
DATA_DIR = Path.home() / ".engineering-guard-factory"
DATA_FILE = DATA_DIR / "data.json"
ARCHIVE_FILE = DATA_DIR / "archive.json"
# New dashboard data (tasks, notes, job events) lives in SQLite; jobs stay in the JSON files
# above (decisions/factory-workspace.md, D52).
DATABASE_FILE = DATA_DIR / "factory.db"
ARCHIVE_RETENTION_DAYS = 30
CLEANUP_INTERVAL_SECONDS = 3600  # Run archive cleanup every hour
MAX_SYNC_BODY_BYTES = 5 * 1024 * 1024  # Reject oversized /api/jobs/sync payloads
# The built Svelte app (decision D29-D32). It is built on install, not committed, so a missing
# directory is a normal state that the server explains rather than a failure.
UI_DIST_DIR = Path(__file__).resolve().parents[4] / "ui" / "dist"
UI_BUILD_HELP = "The factory UI is not built. Run: npm install --prefix ui && npm run build --prefix ui"


def _write_json_atomic(path, data):
    """Write JSON to path via temp file + rename so readers never see a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _job_key(job):
    """Composite key so identical per-repo job ids from different repositories never collide."""
    return (job.get("repo_path") or job.get("repository") or "", job["id"])


def _board_identity(job):
    """The real path of the job's board.json, or None when it cannot be resolved.

    A worktree can reach the main checkout's `.factory` through a symlink, so one board shows up
    under two repo_paths. Resolving the file tells such aliases apart from two genuinely
    different repositories, which keep distinct boards.
    """
    repo_path = job.get("repo_path")
    if not repo_path:
        return None
    board = os.path.join(repo_path, ".factory", "board.json")
    return os.path.realpath(board) if os.path.isfile(board) else None


def _same_job(job, other):
    """True when both entries are one board job: same id, and same (repo_path, id) or same board file."""
    if job["id"] != other["id"]:
        return False
    if _job_key(job) == _job_key(other):
        return True
    identity = _board_identity(job)
    return identity is not None and identity == _board_identity(other)


_FACTORY_BOARD = None


def _load_sibling_module(name):
    """Load a module that sits next to this script, by path.

    The server is run as a script and loaded by tests from a file path, so the script directory
    is not reliably on sys.path; loading by path works the same way in both.
    """
    import importlib.util

    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_factory_board():
    """Import the sibling factory_board.py module so the server stays a thin layer."""
    global _FACTORY_BOARD
    if _FACTORY_BOARD is None:
        _FACTORY_BOARD = _load_sibling_module("factory_board")
    return _FACTORY_BOARD


# The store module is loaded once so every handler shares the same exception classes.
factory_store = _load_sibling_module("factory_store")


class JobServer(http.server.SimpleHTTPRequestHandler):
    """HTTP handler for job sync and retrieval endpoints."""

    # The server handles one connection at a time, and it now also serves the browser app. A
    # browser opens speculative connections that send nothing; without a timeout one of those
    # would block every board push and poll behind it indefinitely. A few seconds is far longer
    # than a real request takes to arrive over loopback. Threading was not used because the
    # handlers read-modify-write the data files and would then need locking.
    timeout = 5

    # Set by start_server before serving. The handler class is instantiated per request, so the
    # one shared store lives on the class.
    store = None

    def do_GET(self):
        """GET /api/jobs - return all in-progress jobs."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/jobs":
            self._get_jobs()
        elif path == "/api/jobs/archive":
            self._get_archive()
        elif path == "/api/jobs/stats":
            self._get_job_stats(parse_qs(parsed_url.query))
        elif path == "/api/tasks":
            self._store_call(lambda: {"tasks": self.store.list_tasks(), "statuses": list(factory_store.TASK_STATUSES)})
        elif path == "/api/notes":
            self._get_notes(parse_qs(parsed_url.query))
        elif path == "/health":
            self._health_check()
        else:
            # Anything that is not an API route is the built UI. The inherited
            # SimpleHTTPRequestHandler file serving is never used: it would expose the working
            # directory, so every static read goes through _serve_static's allowlist.
            self._serve_static(path)

    def do_POST(self):
        """POST /api/jobs/sync - receive job update from a factory."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/jobs/sync":
            self._sync_job()
        elif path == "/api/jobs/archive":
            self._close_job("archive", default_reason="")
        elif path == "/api/jobs/abandon":
            self._close_job("abandon", default_reason="")
        elif path == "/api/tasks":
            self._with_json_object(lambda body: self._store_call(lambda: self.store.create_task(
                title=body.get("title"), prompt=body.get("prompt", ""),
                status=body.get("status", factory_store.DEFAULT_TASK_STATUS),
                repo_path=body.get("repo_path"), job_id=body.get("job_id"),
            ), success_status=201))
        elif path == "/api/notes":
            self._with_json_object(lambda body: self._store_call(lambda: self.store.add_note(
                body.get("body"), task_id=body.get("task_id"),
                repo_path=body.get("repo_path"), job_id=body.get("job_id"),
            ), success_status=201))
        elif (task_id := self._task_id_from(path, suffix="/move")) is not None:
            self._with_json_object(lambda body: self._store_call(lambda: self.store.move_task(
                task_id, status=body.get("status"), index=body.get("index"),
            )))
        else:
            self.send_error(404, "Not found")

    def do_PATCH(self):
        """PATCH /api/tasks/<id> - change the given fields of a task."""
        task_id = self._task_id_from(urlparse(self.path).path)
        if task_id is None:
            self.send_error(404, "Not found")
            return
        self._with_json_object(
            lambda body: self._store_call(lambda: self.store.update_task(task_id, **body))
        )

    def do_DELETE(self):
        """DELETE /api/tasks/<id> or /api/notes/<id>."""
        path = urlparse(self.path).path
        task_id = self._task_id_from(path)
        if task_id is not None:
            self._store_call(lambda: self.store.delete_task(task_id) or {"status": "ok"})
            return
        match = re.fullmatch(r"/api/notes/(\d+)", path)
        if match:
            note_id = int(match.group(1))
            self._store_call(lambda: self.store.delete_note(note_id) or {"status": "ok"})
            return
        self.send_error(404, "Not found")

    @staticmethod
    def _task_id_from(path, suffix=""):
        """The numeric task id in /api/tasks/<id><suffix>, or None when the path is not that route."""
        match = re.fullmatch(r"/api/tasks/(\d+)" + re.escape(suffix), path)
        return int(match.group(1)) if match else None

    def do_HEAD(self):
        """HEAD / - allow HEAD requests for liveness checks."""
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

    def _serve_static(self, request_path):
        """Serve one file from the built UI, refusing anything that resolves outside it.

        The path is decoded and resolved to a real path, and that real path must sit inside the
        UI directory. Resolving first is what defeats "..", percent-encoded "..", doubled slashes
        and symlinks that point out of the directory; string checks on the raw path do not.
        Only regular files are served, so a directory is never listed.
        """
        decoded = unquote(request_path)
        if "\x00" in decoded or "\\" in decoded:
            self.send_error(400, "Bad path")
            return
        relative = decoded.lstrip("/") or "index.html"
        ui_root = UI_DIST_DIR.resolve()
        try:
            target = (ui_root / relative).resolve()
        except (OSError, RuntimeError):
            self.send_error(400, "Bad path")
            return
        if target != ui_root and ui_root not in target.parents:
            self.send_error(404, "Not found")
            return
        if not target.is_file():
            # A missing index means the UI was never built; any other miss is an ordinary 404.
            # Falling back to index.html for unknown paths would hide a broken build.
            if relative == "index.html":
                self._send_text(503, UI_BUILD_HELP)
            else:
                self.send_error(404, "Not found")
            return
        try:
            content = target.read_bytes()
        except OSError as error:
            self.send_error(500, f"Cannot read file: {error}")
            return
        content_type, _ = mimetypes.guess_type(target.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_text(self, status, message):
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_jobs(self):
        """Return all in-progress jobs as JSON."""
        try:
            jobs = _load_jobs()
            response = {"jobs": jobs, "timestamp": datetime.now(timezone.utc).isoformat()}
            self._send_json(response)
        except Exception as e:
            self.send_error(500, f"Failed to load jobs: {str(e)}")

    def _get_archive(self):
        """Return archived jobs as JSON."""
        try:
            archive = _load_archive()
            response = {"jobs": archive, "timestamp": datetime.now(timezone.utc).isoformat()}
            self._send_json(response)
        except Exception as e:
            self.send_error(500, f"Failed to load archive: {str(e)}")

    def _health_check(self):
        """Return 200 OK for liveness probes."""
        response = {"status": "ok"}
        self._send_json(response)

    def _sync_job(self):
        """Receive job update from a factory and store it."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return

        if content_length == 0:
            self.send_error(400, "Empty request body")
            return
        if content_length > MAX_SYNC_BODY_BYTES:
            # Drain up to the limit so a well-behaved client (e.g. factory_board.py's
            # own sync push) that is still writing the body sees a clean 413 response
            # instead of an abrupt connection reset. Capped at MAX_SYNC_BODY_BYTES of
            # draining so this itself can't be used to tie up the server.
            try:
                self.rfile.read(MAX_SYNC_BODY_BYTES)
            except Exception:
                pass
            self.send_error(413, f"Request body exceeds {MAX_SYNC_BODY_BYTES} bytes")
            return

        try:
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            self.send_error(400, f"Invalid JSON: {str(e)}")
            return

        try:
            # Validate required fields
            if not all(k in payload for k in ["repository", "repo_path", "worktree_path", "job"]):
                self.send_error(400, "Missing required fields: repository, repo_path, worktree_path, job")
                return

            job = payload["job"]
            if not all(k in job for k in ["id", "title", "stage"]):
                self.send_error(400, "Missing required job fields: id, title, stage")
                return

            # Add repository context to job
            job["repository"] = payload["repository"]
            job["repo_path"] = payload["repo_path"]
            job["worktree_path"] = payload["worktree_path"]

            # Events live in SQLite, not in the JSON job mirror, whose shape stays unchanged.
            events = job.pop("events", [])

            # The JSON mirror is the established contract and is written first. Events are a
            # second, independent effect: if they cannot be stored the job update must still
            # land (the board is never blocked, D15), so the failure is reported in the
            # response instead of being hidden or turned into an error for the whole sync.
            _upsert_job(job)
            response = {"status": "ok", "job_id": job["id"]}
            response.update(self._store_job_events(job, events))
            self._send_json(response, status=200)
        except Exception as e:
            self.send_error(500, f"Failed to sync job: {str(e)}")

    def _close_job(self, action, default_reason):
        """Archive (approved, needs-human only) or abandon (any open stage) a job from the dashboard.

        The repo's board.json stays the source of truth, so this delegates to
        factory_board.py's own command rather than editing JSON here. The
        board script is imported (not spawned) and told not to push back: this
        server is single-threaded, so waiting for a sync round-trip would block.
        Abandon requires a reason, which the board enforces. Worktree changes are left alone.
        """
        payload = self._read_json_body()
        if payload is None:
            return

        job_id = payload.get("id")
        repo_path = payload.get("repo_path")
        reason = (payload.get("reason") or default_reason).strip()
        if not job_id or not repo_path:
            self._send_json({"error": "id and repo_path are required"}, status=400)
            return

        stored = next((job for job in _load_jobs() if _job_key(job) == (repo_path, job_id)), None)
        if stored is None:
            self._send_json({"error": "job not found"}, status=404)
            return

        try:
            factory_board = _load_factory_board()
        except Exception as error:
            self._send_json({"error": f"cannot load factory board: {error}"}, status=500)
            return

        try:
            factory = factory_board.Factory(Path(stored["repo_path"]))
            # The board is the source of truth. If it already closed this job (an archive from
            # another path to the same board, or a push the server missed), the dashboard entry
            # is stale: adopt the board's state instead of closing a second time.
            job = factory.find_job(factory.load_board(), job_id)
            if job["stage"] not in factory_board.TERMINAL_STAGES:
                job = getattr(factory, action)(job_id, reason, push=False)
        except factory_board.FactoryError as error:
            self._send_json({"error": str(error)}, status=400)
            return
        except Exception as error:
            self._send_json({"error": f"{action} failed: {error}"}, status=500)
            return

        # Keep the repository context and the mirrored file contents the dashboard
        # already has; the board script only knows about paths, not synced content.
        job["repository"] = stored.get("repository", "")
        job["repo_path"] = stored["repo_path"]
        job["worktree_path"] = stored.get("worktree_path", stored["repo_path"])
        job["files"] = stored.get("files", {})
        # Like a sync, keep events out of the JSON mirror and store them in SQLite. The close
        # event is often exactly what a missed push never delivered; record_events is
        # idempotent, so replaying the board's whole list is safe.
        events = job.pop("events", [])
        _upsert_job(job)
        response = {"status": "ok", "job": job}
        response.update(self._store_job_events(job, events))
        self._send_json(response)

    def _store_job_events(self, job, events):
        """Store a job's events; return the response fields that say whether that worked."""
        try:
            if not isinstance(events, list):
                raise factory_store.InvalidInput("events must be a list")
            self.store.record_events(job["repo_path"], job["id"], events)
            return {"events_stored": True}
        except factory_store.InvalidInput as error:
            return {"events_stored": False, "events_error": f"invalid events: {error}"}
        except Exception as error:
            print(f"[central-factory-server] cannot store events for {job['id']}: {error}", file=sys.stderr)
            return {"events_stored": False, "events_error": f"events unavailable: {error}"}

    def _with_json_object(self, action):
        """Read the request body as a JSON object and pass it to `action`."""
        body = self._read_json_body()
        if body is None:
            return
        if not isinstance(body, dict):
            self._send_json({"error": "request body must be a JSON object"}, status=400)
            return
        action(body)

    def _store_call(self, operation, success_status=200):
        """Run a store operation and map its outcome to HTTP.

        Bad input is the caller's fault (400) and a missing record is 404, but a store that
        cannot be used is a server failure (500): an outage is never presented as a client error.
        """
        try:
            self._send_json(operation(), status=success_status)
        except factory_store.InvalidInput as error:
            self._send_json({"error": str(error)}, status=400)
        except factory_store.NotFound as error:
            self._send_json({"error": str(error)}, status=404)
        except Exception as error:
            print(f"[central-factory-server] store failure: {error}", file=sys.stderr)
            self._send_json({"error": f"store unavailable: {error}"}, status=500)

    def _get_job_stats(self, query):
        repo_path = (query.get("repo_path") or [""])[0]
        job_id = (query.get("id") or [""])[0]
        if not repo_path or not job_id:
            self._send_json({"error": "repo_path and id are required"}, status=400)
            return
        self._store_call(lambda: {"stats": self.store.job_stats(repo_path, job_id)})

    def _get_notes(self, query):
        task_id = (query.get("task_id") or [""])[0]
        repo_path = (query.get("repo_path") or [""])[0]
        job_id = (query.get("job_id") or [""])[0]
        if task_id.isdigit():
            self._store_call(lambda: {"notes": self.store.list_notes(task_id=int(task_id))})
        elif repo_path and job_id:
            self._store_call(lambda: {"notes": self.store.list_notes(repo_path=repo_path, job_id=job_id)})
        else:
            self._send_json({"error": "task_id, or repo_path and job_id, is required"}, status=400)

    def _read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_json({"error": "Invalid Content-Length"}, status=400)
            return None

        if content_length <= 0:
            self._send_json({"error": "Empty request body"}, status=400)
            return None
        if content_length > MAX_SYNC_BODY_BYTES:
            self._send_json({"error": "Request body too large"}, status=413)
            return None

        try:
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
        except Exception as error:
            self._send_json({"error": f"Invalid JSON: {error}"}, status=400)
            return None

    def _send_json(self, data, status=200):
        """Send JSON response."""
        response = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        """Log HTTP requests with timestamps."""
        print(f"[{datetime.now(timezone.utc).isoformat()}] {format % args}", file=sys.stderr)


def _quarantine_corrupt_file(path, error):
    """Move an unreadable state file aside instead of silently discarding it."""
    quarantine = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
    try:
        os.replace(path, quarantine)
        print(
            f"[central-factory-server] {path} was unreadable ({error}); "
            f"quarantined as {quarantine}",
            file=sys.stderr,
        )
    except OSError as rename_error:
        print(
            f"[central-factory-server] {path} was unreadable ({error}) and could not "
            f"be quarantined ({rename_error})",
            file=sys.stderr,
        )


def _load_jobs():
    """Load all in-progress jobs from disk."""
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        return data.get("jobs", [])
    except (OSError, ValueError) as error:
        _quarantine_corrupt_file(DATA_FILE, error)
        return []


def _load_archive():
    """Load archived jobs from disk."""
    if not ARCHIVE_FILE.exists():
        return []
    try:
        with open(ARCHIVE_FILE, "r") as f:
            data = json.load(f)
        return data.get("jobs", [])
    except (OSError, ValueError) as error:
        _quarantine_corrupt_file(ARCHIVE_FILE, error)
        return []


ARCHIVED_STAGES = ("complete", "abandoned")


def _upsert_job(job):
    """Insert or update a job in in-progress storage.

    Jobs are keyed by (repo_path, id) rather than id alone: job ids are assigned
    by a per-repository counter in factory_board.py and restart at 001 in every
    repository, so matching on id alone would let unrelated repositories
    silently overwrite each other's job records.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    jobs = _load_jobs()
    key = _job_key(job)

    if job["stage"] in ARCHIVED_STAGES:
        # Move terminal jobs into the archive store instead of growing data.json forever. The
        # same job seen under another path to the same board leaves In Progress too.
        if "completed_at" not in job:
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(DATA_FILE, {"jobs": [j for j in jobs if not _same_job(j, job)]})
        _append_to_archive(job)
        return

    existing_index = None
    for i, j in enumerate(jobs):
        if _job_key(j) == key:
            existing_index = i
            break

    if existing_index is not None:
        jobs[existing_index] = job
    else:
        jobs.append(job)

    _write_json_atomic(DATA_FILE, {"jobs": jobs})


def _append_to_archive(job):
    """Insert or update a job in the archive store, replacing any entry for the same board job."""
    archive = _load_archive()
    merged = []
    replaced = False
    for existing in archive:
        if not _same_job(existing, job):
            merged.append(existing)
        elif not replaced:
            merged.append(job)
            replaced = True
    if not replaced:
        merged.append(job)
    _write_json_atomic(ARCHIVE_FILE, {"jobs": merged})


def _cleanup_archive():
    """Remove archived jobs older than ARCHIVE_RETENTION_DAYS."""
    if not ARCHIVE_FILE.exists():
        return

    try:
        jobs = _load_archive()
        cutoff = datetime.now(timezone.utc).timestamp() - (ARCHIVE_RETENTION_DAYS * 86400)

        # Keep only jobs completed (or created, as a fallback) after cutoff. The board names the
        # creation field `created`; reading any other name made a job without `completed_at` look
        # infinitely old and deleted it.
        kept = [j for j in jobs if _parse_timestamp(j.get("completed_at", j.get("created", ""))) > cutoff]

        if len(kept) < len(jobs):
            removed = len(jobs) - len(kept)
            print(f"Archived cleanup: removed {removed} jobs older than {ARCHIVE_RETENTION_DAYS} days", file=sys.stderr)
            _write_json_atomic(ARCHIVE_FILE, {"jobs": kept})
    except Exception as e:
        print(f"Archive cleanup failed: {e}", file=sys.stderr)


def _parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp to Unix timestamp. Returns 0 if invalid."""
    if not ts_str:
        return 0
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0


def _run_cleanup_loop():
    """Periodically clean up old archived jobs."""
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        _cleanup_archive()


def _already_running(host, port):
    """Probe /health to detect a live instance before attempting to bind."""
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{probe_host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def start_server(host=SERVER_HOST, port=SERVER_PORT):
    """Start the central factory server."""
    if _already_running(host, port):
        print(
            f"Central Factory Server already running on http://{host}:{port}/ — not starting a second instance.",
            file=sys.stderr,
        )
        return

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # The server owns the store: opened here, closed in the finally below. A store that cannot be
    # opened (for example a database from a newer version) stops startup with a clear message
    # rather than serving a dashboard whose tasks silently fail.
    try:
        JobServer.store = factory_store.FactoryStore(DATABASE_FILE)
    except (factory_store.StoreError, OSError) as error:
        print(f"Cannot open the factory database {DATABASE_FILE}: {error}", file=sys.stderr)
        sys.exit(1)

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=_run_cleanup_loop, daemon=True)
    cleanup_thread.start()

    # Create server with SO_REUSEADDR to avoid "Address already in use" on restart
    socketserver.TCPServer.allow_reuse_address = True

    try:
        httpd = socketserver.TCPServer((host, port), JobServer)
    except OSError as error:
        # The store is already open; release it before exiting on a bind failure.
        JobServer.store.close()
        print(
            f"Could not bind http://{host}:{port}/ ({error}). "
            "Another process may be using this port.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with httpd:
            print(f"Central Factory Server listening on http://{host}:{port}/", file=sys.stderr)
            print(f"Dashboard: http://{host}:{port}/", file=sys.stderr)
            print(f"Data directory: {DATA_DIR}", file=sys.stderr)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("Shutting down...", file=sys.stderr)
    finally:
        JobServer.store.close()


def main():
    parser = argparse.ArgumentParser(description="Central Factory Server")
    parser.add_argument(
        "--host",
        default=SERVER_HOST,
        help=f"Host to listen on (default: {SERVER_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=SERVER_PORT,
        help=f"Port to listen on (default: {SERVER_PORT})",
    )
    args = parser.parse_args()
    
    start_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
