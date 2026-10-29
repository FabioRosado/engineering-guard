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
from urllib.parse import urlparse, parse_qs

# Configuration
SERVER_PORT = 5173
SERVER_HOST = "127.0.0.1"
DATA_DIR = Path.home() / ".engineering-guard-factory"
DATA_FILE = DATA_DIR / "data.json"
ARCHIVE_FILE = DATA_DIR / "archive.json"
ARCHIVE_RETENTION_DAYS = 30
CLEANUP_INTERVAL_SECONDS = 3600  # Run archive cleanup every hour
MAX_SYNC_BODY_BYTES = 5 * 1024 * 1024  # Reject oversized /api/jobs/sync payloads


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


_FACTORY_BOARD = None


def _load_factory_board():
    """Import the sibling factory_board.py module so the server stays a thin layer."""
    global _FACTORY_BOARD
    if _FACTORY_BOARD is None:
        import importlib.util

        path = Path(__file__).with_name("factory_board.py")
        spec = importlib.util.spec_from_file_location("factory_board", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _FACTORY_BOARD = module
    return _FACTORY_BOARD


class JobServer(http.server.SimpleHTTPRequestHandler):
    """HTTP handler for job sync and retrieval endpoints."""

    def do_GET(self):
        """GET /api/jobs - return all in-progress jobs."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)

        if path == "/":
            self._serve_dashboard()
        elif path == "/api/jobs":
            self._get_jobs()
        elif path == "/api/jobs/archive":
            self._get_archive()
        elif path == "/health":
            self._health_check()
        else:
            self.send_error(404, "Not found")

    def do_POST(self):
        """POST /api/jobs/sync - receive job update from a factory."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/jobs/sync":
            self._sync_job()
        elif path == "/api/jobs/archive":
            self._archive_job()
        else:
            self.send_error(404, "Not found")

    def do_HEAD(self):
        """HEAD / - allow HEAD requests for liveness checks."""
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

    def _serve_dashboard(self):
        """Serve the dashboard HTML."""
        dashboard_path = Path(__file__).resolve().parents[1] / "assets" / "dashboard.html"

        if not dashboard_path.exists():
            self.send_error(404, "Dashboard not found")
            return

        try:
            with open(dashboard_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, str(e))

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

            # Update job in storage
            _upsert_job(job)
            
            response = {"status": "ok", "job_id": job["id"]}
            self._send_json(response, status=200)
        except Exception as e:
            self.send_error(500, f"Failed to sync job: {str(e)}")

    def _archive_job(self):
        """Archive a needs-human job triggered from the dashboard.

        The repo's board.json stays the source of truth, so this delegates to
        factory_board.py's archive command rather than editing JSON here. The
        board script is imported (not spawned) and told not to push back: this
        server is single-threaded, so waiting for a sync round-trip would block.
        """
        payload = self._read_json_body()
        if payload is None:
            return

        job_id = payload.get("id")
        repo_path = payload.get("repo_path")
        reason = (payload.get("reason") or "").strip()
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
            job = factory_board.Factory(Path(stored["repo_path"])).archive(
                job_id, reason, push=False
            )
        except factory_board.FactoryError as error:
            self._send_json({"error": str(error)}, status=400)
            return
        except Exception as error:
            self._send_json({"error": f"archive failed: {error}"}, status=500)
            return

        # Keep the repository context and the mirrored file contents the dashboard
        # already has; the board script only knows about paths, not synced content.
        job["repository"] = stored.get("repository", "")
        job["repo_path"] = stored["repo_path"]
        job["worktree_path"] = stored.get("worktree_path", stored["repo_path"])
        job["files"] = stored.get("files", {})
        _upsert_job(job)
        self._send_json({"status": "ok", "job": job})

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


ARCHIVED_STAGES = ("abandoned",)


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

    existing_index = None
    for i, j in enumerate(jobs):
        if _job_key(j) == key:
            existing_index = i
            break

    if job["stage"] == "abandoned" and "completed_at" not in job:
        job["completed_at"] = datetime.now(timezone.utc).isoformat()

    if job["stage"] in ARCHIVED_STAGES:
        # Move terminal jobs into the archive store instead of growing data.json forever.
        if existing_index is not None:
            jobs.pop(existing_index)
        _write_json_atomic(DATA_FILE, {"jobs": jobs})
        _append_to_archive(job)
        return

    if existing_index is not None:
        jobs[existing_index] = job
    else:
        jobs.append(job)

    _write_json_atomic(DATA_FILE, {"jobs": jobs})


def _append_to_archive(job):
    """Insert or update a job in the archive store, keyed the same way as in-progress jobs."""
    archive = _load_archive()
    key = _job_key(job)
    for i, j in enumerate(archive):
        if _job_key(j) == key:
            archive[i] = job
            break
    else:
        archive.append(job)
    _write_json_atomic(ARCHIVE_FILE, {"jobs": archive})


def _cleanup_archive():
    """Remove archived jobs older than ARCHIVE_RETENTION_DAYS."""
    if not ARCHIVE_FILE.exists():
        return

    try:
        jobs = _load_archive()
        cutoff = datetime.now(timezone.utc).timestamp() - (ARCHIVE_RETENTION_DAYS * 86400)

        # Keep only jobs completed (or created, as a fallback) after cutoff
        kept = [j for j in jobs if _parse_timestamp(j.get("completed_at", j.get("created_at", ""))) > cutoff]

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

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=_run_cleanup_loop, daemon=True)
    cleanup_thread.start()

    # Create server with SO_REUSEADDR to avoid "Address already in use" on restart
    socketserver.TCPServer.allow_reuse_address = True

    try:
        httpd = socketserver.TCPServer((host, port), JobServer)
    except OSError as error:
        print(
            f"Could not bind http://{host}:{port}/ ({error}). "
            "Another process may be using this port.",
            file=sys.stderr,
        )
        sys.exit(1)

    with httpd:
        print(f"Central Factory Server listening on http://{host}:{port}/", file=sys.stderr)
        print(f"Dashboard: http://{host}:{port}/", file=sys.stderr)
        print(f"Data directory: {DATA_DIR}", file=sys.stderr)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Shutting down...", file=sys.stderr)


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
