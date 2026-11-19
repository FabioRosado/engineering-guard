"""Job sync, archive and listing endpoints of the central factory server.

These endpoints had no tests before the SQLite workspace work (decisions/factory-workspace.md, R3),
so they are pinned here first against the JSON store. A real server runs on an ephemeral loopback
port with its data directory redirected to a temporary folder, so the real
~/.engineering-guard-factory is never touched.
"""

import http.client
import importlib.util
import json
import os
import socketserver
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_factory_board import FactoryBoardHarness as BoardHarness  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "factory" / "scripts" / "central_factory_server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("central_factory_server_api_under_test", SERVER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CentralServerHarness:
    """Starts the real server against temporary storage. A mixin so other modules can reuse it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="factory-server-")
        root = Path(self.temp.name)
        self.module = load_server_module()
        self.module.DATA_DIR = root / "data"
        self.module.DATA_FILE = self.module.DATA_DIR / "data.json"
        self.module.ARCHIVE_FILE = self.module.DATA_DIR / "archive.json"
        self.module.DATABASE_FILE = self.module.DATA_DIR / "factory.db"
        self.module.UI_DIST_DIR = root / "ui" / "dist"
        self.module.DATA_DIR.mkdir(parents=True)
        self.store = self.module.factory_store.FactoryStore(self.module.DATABASE_FILE)
        self.module.JobServer.store = self.store

        socketserver.TCPServer.allow_reuse_address = True
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), self.module.JobServer)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.store.close()
        self.temp.cleanup()

    def request(self, method, path, payload=None, raw_body=None, headers=None):
        """Return (status, parsed JSON or None). Sends the body exactly as given."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            body = raw_body if raw_body is not None else (
                json.dumps(payload).encode("utf-8") if payload is not None else None
            )
            request_headers = {"Content-Type": "application/json", **(headers or {})}
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            data = response.read()
            try:
                return response.status, json.loads(data.decode("utf-8"))
            except ValueError:
                return response.status, None
        finally:
            connection.close()

    def sync(self, job_id="001-first", repo="/work/alpha", stage="build", **job_fields):
        job = {"id": job_id, "title": f"Job {job_id}", "stage": stage, **job_fields}
        return self.request("POST", "/api/jobs/sync", {
            "repository": Path(repo).name,
            "repo_path": repo,
            "worktree_path": repo,
            "job": job,
        })

    def in_progress(self):
        return self.request("GET", "/api/jobs")[1]["jobs"]

    def archived(self):
        return self.request("GET", "/api/jobs/archive")[1]["jobs"]


class JobSyncTests(CentralServerHarness, unittest.TestCase):
    def test_a_synced_job_is_listed_with_its_repository_context(self):
        status, body = self.sync(job_id="001-first", repo="/work/alpha", files={"spec.md": "# Spec"})
        self.assertEqual((status, body["status"]), (200, "ok"))

        [job] = self.in_progress()
        self.assertEqual(job["id"], "001-first")
        self.assertEqual(job["repository"], "alpha")
        self.assertEqual(job["repo_path"], "/work/alpha")
        self.assertEqual(job["files"], {"spec.md": "# Spec"})

    def test_syncing_the_same_job_again_updates_it_instead_of_duplicating_it(self):
        self.sync(stage="build")
        self.sync(stage="review")
        [job] = self.in_progress()
        self.assertEqual(job["stage"], "review")

    def test_ids_that_collide_across_repositories_stay_separate_jobs(self):
        # Per-repository counters restart at 001, so the id alone cannot identify a job.
        self.sync(job_id="001-first", repo="/work/alpha")
        self.sync(job_id="001-first", repo="/work/beta")
        self.assertEqual(sorted(job["repo_path"] for job in self.in_progress()), ["/work/alpha", "/work/beta"])

    def test_a_terminal_job_moves_to_the_archive_with_a_completion_time(self):
        self.sync(stage="build")
        self.sync(stage="abandoned")

        self.assertEqual(self.in_progress(), [])
        [job] = self.archived()
        self.assertEqual(job["id"], "001-first")
        self.assertIn("completed_at", job)

    def test_a_complete_job_moves_to_the_archive_with_a_completion_time(self):
        self.sync(stage="needs-human")
        self.sync(stage="complete")

        self.assertEqual(self.in_progress(), [])
        [job] = self.archived()
        self.assertEqual(job["stage"], "complete")
        self.assertIn("completed_at", job)

    def test_an_archived_job_is_not_duplicated_by_a_later_sync(self):
        self.sync(stage="abandoned")
        self.sync(stage="abandoned")
        self.assertEqual(len(self.archived()), 1)

    def test_a_payload_missing_required_fields_is_rejected_as_a_client_error(self):
        status, _ = self.request("POST", "/api/jobs/sync", {"repository": "alpha"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/jobs/sync", {
            "repository": "alpha", "repo_path": "/work/alpha", "worktree_path": "/work/alpha",
            "job": {"id": "001-first"},
        })
        self.assertEqual(status, 400)
        self.assertEqual(self.in_progress(), [])

    def test_malformed_json_and_empty_bodies_are_rejected(self):
        self.assertEqual(self.request("POST", "/api/jobs/sync", raw_body=b"{not json")[0], 400)
        self.assertEqual(self.request("POST", "/api/jobs/sync", raw_body=b"")[0], 400)

    def test_an_oversized_body_is_rejected_without_being_stored(self):
        self.module.MAX_SYNC_BODY_BYTES = 1024
        status, _ = self.request("POST", "/api/jobs/sync", raw_body=b"x" * 4096)
        self.assertEqual(status, 413)
        self.assertEqual(self.in_progress(), [])

    def test_an_unreadable_store_is_quarantined_not_silently_discarded(self):
        self.sync()
        self.module.DATA_FILE.write_text("{corrupt", encoding="utf-8")

        self.assertEqual(self.in_progress(), [])
        quarantined = list(self.module.DATA_DIR.glob("data.json.corrupt-*"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_text(encoding="utf-8"), "{corrupt")


class ArchiveCleanupTests(CentralServerHarness, unittest.TestCase):
    def archive_job_completed(self, job_id, days_ago):
        completed = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        self.sync(job_id=job_id, stage="abandoned", completed_at=completed)

    def test_jobs_older_than_the_retention_period_are_removed(self):
        self.archive_job_completed("001-old", days_ago=self.module.ARCHIVE_RETENTION_DAYS + 5)
        self.archive_job_completed("002-recent", days_ago=2)

        self.module._cleanup_archive()

        self.assertEqual([job["id"] for job in self.archived()], ["002-recent"])

    def test_a_complete_job_is_kept_for_the_retention_period_from_its_completion(self):
        # A board job has no completed_at; the server must stamp one for `complete` too, or the
        # cleanup would read the job as created long ago and delete it at once.
        created = (datetime.now(timezone.utc) - timedelta(days=self.module.ARCHIVE_RETENTION_DAYS + 5))
        self.sync(job_id="001-old-job", stage="complete", created=created.strftime("%Y-%m-%dT%H:%M:%SZ"))

        self.module._cleanup_archive()

        self.assertEqual([job["id"] for job in self.archived()], ["001-old-job"])

    def test_a_job_without_completed_at_falls_back_to_its_creation_time(self):
        # The board writes `created`, not `created_at`; the fallback must use the real field name
        # or an archived job with no completion time is treated as infinitely old and deleted.
        created = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.module._write_json_atomic(
            self.module.ARCHIVE_FILE,
            {"jobs": [{"id": "001-no-completion", "repo_path": "/work/alpha", "stage": "abandoned", "created": created}]},
        )

        self.module._cleanup_archive()

        self.assertEqual([job["id"] for job in self.archived()], ["001-no-completion"])


class ArchiveEndpointTests(CentralServerHarness, unittest.TestCase):
    def test_archiving_requires_an_id_and_a_repository_path(self):
        status, body = self.request("POST", "/api/jobs/archive", {"id": "001-first"})
        self.assertEqual(status, 400)
        self.assertIn("required", body["error"])

    def test_archiving_an_unknown_job_is_not_found(self):
        status, body = self.request("POST", "/api/jobs/archive", {"id": "001-nope", "repo_path": "/work/alpha"})
        self.assertEqual(status, 404)
        self.assertIn("not found", body["error"])

    def test_an_unreadable_body_is_a_client_error(self):
        self.assertEqual(self.request("POST", "/api/jobs/archive", raw_body=b"{nope")[0], 400)

    def test_unknown_post_routes_are_not_found(self):
        self.assertEqual(self.request("POST", "/api/nothing", {})[0], 404)


class AbandonEndpointTests(CentralServerHarness, unittest.TestCase):
    def test_abandoning_requires_an_id_and_a_repository_path(self):
        status, body = self.request("POST", "/api/jobs/abandon", {"id": "001-first"})
        self.assertEqual(status, 400)
        self.assertIn("required", body["error"])

    def test_abandoning_an_unknown_job_is_not_found(self):
        status, body = self.request("POST", "/api/jobs/abandon", {"id": "001-nope", "repo_path": "/work/alpha"})
        self.assertEqual(status, 404)
        self.assertIn("not found", body["error"])

    def test_an_unreadable_body_is_a_client_error(self):
        self.assertEqual(self.request("POST", "/api/jobs/abandon", raw_body=b"{nope")[0], 400)


class JobEventSyncTests(CentralServerHarness, unittest.TestCase):
    EVENTS = [
        {"stage": "spec", "round": 0, "at": "2026-10-30T10:00:00Z"},
        {"stage": "build", "round": 1, "at": "2026-10-30T10:30:00Z"},
    ]

    def test_events_in_a_sync_are_stored_and_not_kept_in_the_job_mirror(self):
        status, body = self.sync(events=self.EVENTS)

        self.assertEqual((status, body["events_stored"]), (200, True))
        self.assertEqual(self.store.list_events("/work/alpha", "001-first"), self.EVENTS)
        [job] = self.in_progress()
        self.assertNotIn("events", job)

    def test_resending_the_same_events_does_not_duplicate_them(self):
        self.sync(events=self.EVENTS)
        self.sync(events=self.EVENTS)
        self.assertEqual(len(self.store.list_events("/work/alpha", "001-first")), 2)

    def test_a_sync_without_events_still_works(self):
        # Boards from before events existed send none; that must stay valid (compatibility).
        status, body = self.sync()
        self.assertEqual(status, 200)
        self.assertTrue(body["events_stored"])
        self.assertEqual(len(self.in_progress()), 1)

    def test_malformed_events_do_not_lose_the_job_update_and_are_reported(self):
        # The job mirror is the established contract and the board must never be blocked (D15):
        # the job is saved, and the response says plainly that its events were not.
        status, body = self.sync(stage="review", events=[{"stage": "build", "round": "one", "at": "x"}])

        self.assertEqual(status, 200)
        self.assertFalse(body["events_stored"])
        self.assertIn("events", body["events_error"])
        [job] = self.in_progress()
        self.assertEqual(job["stage"], "review")
        self.assertEqual(self.store.list_events("/work/alpha", "001-first"), [])

    def test_events_that_are_not_a_list_are_reported_not_stored(self):
        status, body = self.sync(events={"stage": "spec"})
        self.assertEqual(status, 200)
        self.assertFalse(body["events_stored"])

    def test_an_unavailable_store_is_reported_without_blocking_the_job_update(self):
        self.store.close()
        status, body = self.sync(stage="review", events=self.EVENTS)

        self.assertEqual(status, 200)
        self.assertFalse(body["events_stored"])
        self.assertEqual(self.in_progress()[0]["stage"], "review")


class StatsEndpointTests(CentralServerHarness, unittest.TestCase):
    def test_stats_for_a_job_come_from_its_synced_events(self):
        self.sync(events=[
            {"stage": "spec", "round": 0, "at": "2026-10-30T10:00:00Z"},
            {"stage": "spec-review", "round": 0, "at": "2026-10-30T10:10:00Z"},
            {"stage": "abandoned", "round": 0, "at": "2026-10-30T10:40:00Z"},
        ])

        status, body = self.request("GET", "/api/jobs/stats?repo_path=/work/alpha&id=001-first")

        self.assertEqual(status, 200)
        stats = body["stats"]
        self.assertEqual(stats["total_seconds"], 2400)
        self.assertEqual(stats["human_seconds"], 1800)
        self.assertEqual(stats["agent_seconds"], 600)
        self.assertTrue(stats["finished"])

    def test_a_job_with_no_events_has_no_stats_but_is_not_an_error(self):
        status, stats = self.request("GET", "/api/jobs/stats?repo_path=/work/alpha&id=001-first")
        self.assertEqual(status, 200)
        self.assertIsNone(stats["stats"])

    def test_stats_need_both_a_repository_and_an_id(self):
        self.assertEqual(self.request("GET", "/api/jobs/stats?id=001-first")[0], 400)
        self.assertEqual(self.request("GET", "/api/jobs/stats?repo_path=/work/alpha")[0], 400)


class TaskEndpointTests(CentralServerHarness, unittest.TestCase):
    def create(self, **fields):
        fields.setdefault("title", "A task")
        fields.setdefault("prompt", "do it")
        return self.request("POST", "/api/tasks", fields)

    def test_the_task_list_includes_the_column_names_the_server_accepts(self):
        status, body = self.request("GET", "/api/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(body["tasks"], [])
        self.assertEqual(body["statuses"], ["backlog", "ready", "in-progress", "done"])

    def test_a_created_task_is_listed_with_its_prompt(self):
        status, task = self.create(title="Write docs", prompt="Document the store")
        self.assertEqual(status, 201)

        listed = self.request("GET", "/api/tasks")[1]["tasks"]
        self.assertEqual([(t["id"], t["title"], t["prompt"], t["status"]) for t in listed],
                         [(task["id"], "Write docs", "Document the store", "backlog")])

    def test_invalid_task_input_is_a_client_error_and_stores_nothing(self):
        self.assertEqual(self.create(title="  ")[0], 400)
        self.assertEqual(self.create(status="someday")[0], 400)
        self.assertEqual(self.request("GET", "/api/tasks")[1]["tasks"], [])

    def test_a_task_can_be_edited_and_moved(self):
        task = self.create(title="Old")[1]

        status, edited = self.request("PATCH", f"/api/tasks/{task['id']}", {"title": "New"})
        self.assertEqual((status, edited["title"]), (200, "New"))

        status, moved = self.request("POST", f"/api/tasks/{task['id']}/move", {"status": "ready"})
        self.assertEqual((status, moved["status"]), (200, "ready"))

    def test_moving_to_an_unknown_column_is_rejected(self):
        task = self.create()[1]
        self.assertEqual(self.request("POST", f"/api/tasks/{task['id']}/move", {"status": "limbo"})[0], 400)

    def test_an_unknown_task_is_not_found(self):
        self.assertEqual(self.request("PATCH", "/api/tasks/999", {"title": "x"})[0], 404)
        self.assertEqual(self.request("POST", "/api/tasks/999/move", {"status": "ready"})[0], 404)
        self.assertEqual(self.request("DELETE", "/api/tasks/999")[0], 404)

    def test_a_non_numeric_task_id_is_not_found(self):
        self.assertEqual(self.request("PATCH", "/api/tasks/abc", {"title": "x"})[0], 404)

    def test_a_deleted_task_disappears(self):
        task = self.create()[1]
        self.assertEqual(self.request("DELETE", f"/api/tasks/{task['id']}")[0], 200)
        self.assertEqual(self.request("GET", "/api/tasks")[1]["tasks"], [])

    def test_hostile_text_is_stored_verbatim_and_returned_as_json(self):
        # The server never interprets task text; rendering safety is the UI's job.
        hostile = "'); DROP TABLE tasks;-- <script>alert(1)</script>"
        task = self.create(title=hostile, prompt=hostile)[1]

        listed = self.request("GET", "/api/tasks")[1]["tasks"]
        self.assertEqual((listed[0]["id"], listed[0]["title"], listed[0]["prompt"]), (task["id"], hostile, hostile))

    def test_a_server_side_failure_is_not_reported_as_a_client_error(self):
        self.store.close()
        status, _ = self.request("GET", "/api/tasks")
        self.assertEqual(status, 500)

    def test_an_unreadable_body_is_a_client_error(self):
        self.assertEqual(self.request("POST", "/api/tasks", raw_body=b"{nope")[0], 400)
        self.assertEqual(self.request("POST", "/api/tasks", raw_body=b"[1, 2]")[0], 400)


class NoteEndpointTests(CentralServerHarness, unittest.TestCase):
    def test_a_task_note_round_trips_newest_first(self):
        task = self.request("POST", "/api/tasks", {"title": "T", "prompt": "p"})[1]
        self.request("POST", "/api/notes", {"task_id": task["id"], "body": "first"})
        self.request("POST", "/api/notes", {"task_id": task["id"], "body": "second"})

        status, body = self.request("GET", f"/api/notes?task_id={task['id']}")

        self.assertEqual(status, 200)
        self.assertEqual([note["body"] for note in body["notes"]], ["second", "first"])

    def test_job_notes_are_kept_per_repository(self):
        self.request("POST", "/api/notes", {"repo_path": "/work/alpha", "job_id": "001-first", "body": "alpha"})
        self.request("POST", "/api/notes", {"repo_path": "/work/beta", "job_id": "001-first", "body": "beta"})

        for repository in ("alpha", "beta"):
            with self.subTest(repository=repository):
                body = self.request("GET", f"/api/notes?repo_path=/work/{repository}&job_id=001-first")[1]
                self.assertEqual([note["body"] for note in body["notes"]], [repository])

    def test_a_note_needs_exactly_one_parent(self):
        task = self.request("POST", "/api/tasks", {"title": "T", "prompt": "p"})[1]
        self.assertEqual(self.request("POST", "/api/notes", {"body": "orphan"})[0], 400)
        both = {"body": "both", "task_id": task["id"], "repo_path": "/work/alpha", "job_id": "001-first"}
        self.assertEqual(self.request("POST", "/api/notes", both)[0], 400)

    def test_a_note_on_an_unknown_task_is_not_found(self):
        self.assertEqual(self.request("POST", "/api/notes", {"task_id": 999, "body": "lost"})[0], 404)

    def test_listing_notes_needs_a_parent(self):
        self.assertEqual(self.request("GET", "/api/notes")[0], 400)

    def test_a_note_can_be_deleted_once(self):
        task = self.request("POST", "/api/tasks", {"title": "T", "prompt": "p"})[1]
        note = self.request("POST", "/api/notes", {"task_id": task["id"], "body": "x"})[1]

        self.assertEqual(self.request("DELETE", f"/api/notes/{note['id']}")[0], 200)
        self.assertEqual(self.request("DELETE", f"/api/notes/{note['id']}")[0], 404)




class AbandonThroughTheBoardTests(CentralServerHarness, BoardHarness, unittest.TestCase):
    """The dashboard's Abandon button against a real board in a real Git repository."""

    def setUp(self):
        # Both mixins define setUp/tearDown, so each is run explicitly. The board harness owns
        # self.repo (a Path); the server harness owns the temporary data directory.
        CentralServerHarness.setUp(self)
        BoardHarness.setUp(self)

    def tearDown(self):
        BoardHarness.tearDown(self)
        CentralServerHarness.tearDown(self)

    def mirror(self, job):
        """What the board's own sync would have sent the server for this job."""
        self.sync(job_id=job["id"], repo=str(self.repo), stage=job["stage"], files={"spec.md": "# Spec"})

    def abandon(self, job_id, reason):
        return self.request("POST", "/api/jobs/abandon", {"id": job_id, "repo_path": str(self.repo), "reason": reason})

    def test_a_job_in_review_can_be_abandoned_with_a_reason_and_moves_to_the_archive(self):
        job_id = self.job_in_review()
        self.mirror({"id": job_id, "stage": "review"})

        status, body = self.abandon(job_id, "wrong approach")

        self.assertEqual(status, 200)
        self.assertEqual(body["job"]["stage"], "abandoned")
        self.assertEqual(body["job"]["warnings"], ["abandoned: wrong approach"])
        self.assertEqual(self.in_progress(), [])
        [archived] = self.archived()
        self.assertEqual(archived["id"], job_id)
        # The mirrored files the dashboard shows survive the close.
        self.assertEqual(archived["files"], {"spec.md": "# Spec"})
        # The board, the source of truth, agrees: the worktree is free for the next job.
        self.assertEqual(self.factory("resume", job_id)["job"]["stage"], "abandoned")

    def test_abandoning_without_a_reason_is_refused_and_leaves_the_job_open(self):
        job_id = self.job_in_review()
        self.mirror({"id": job_id, "stage": "review"})

        status, body = self.abandon(job_id, "  ")

        self.assertEqual(status, 400)
        self.assertIn("reason", body["error"])
        self.assertEqual([job["id"] for job in self.in_progress()], [job_id])

    def test_abandoning_an_already_closed_job_is_refused(self):
        job_id = self.job_in_review()
        self.mirror({"id": job_id, "stage": "review"})
        self.assertEqual(self.abandon(job_id, "first")[0], 200)
        # The job now lives in the archive, so the server no longer finds it as open.
        self.assertEqual(self.abandon(job_id, "again")[0], 404)


class AliasedBoardTests(CentralServerHarness, unittest.TestCase):
    """One board seen under two paths (a worktree whose `.factory` is a symlink) is one job."""

    def make_repo(self, name):
        path = Path(self.temp.name) / name
        (path / ".factory").mkdir(parents=True)
        (path / ".factory" / "board.json").write_text('{"jobs": []}', encoding="utf-8")
        return str(path)

    def make_worktree_sharing(self, repo, name="worktree"):
        path = Path(self.temp.name) / name
        path.mkdir()
        os.symlink(Path(repo) / ".factory", path / ".factory")
        return str(path)

    def test_a_terminal_sync_removes_the_in_progress_entry_seen_under_another_path_to_the_same_board(self):
        main = self.make_repo("main")
        worktree = self.make_worktree_sharing(main)
        self.sync(repo=main, stage="needs-human")
        self.sync(repo=worktree, stage="needs-human")
        self.assertEqual(len(self.in_progress()), 2)

        self.sync(repo=main, stage="complete")

        self.assertEqual(self.in_progress(), [])
        [job] = self.archived()
        self.assertEqual(job["repo_path"], main)

    def test_a_terminal_sync_under_the_alias_replaces_the_archive_entry_instead_of_adding_one(self):
        main = self.make_repo("main")
        worktree = self.make_worktree_sharing(main)
        self.sync(repo=main, stage="complete")
        self.sync(repo=worktree, stage="needs-human")

        self.sync(repo=worktree, stage="complete")

        self.assertEqual(self.in_progress(), [])
        [job] = self.archived()
        self.assertEqual(job["repo_path"], worktree)

    def test_the_same_id_in_different_repositories_stays_separate_even_when_both_have_boards(self):
        alpha = self.make_repo("alpha")
        beta = self.make_repo("beta")
        self.sync(repo=alpha, stage="needs-human")
        self.sync(repo=beta, stage="needs-human")

        self.sync(repo=alpha, stage="complete")

        self.assertEqual([job["repo_path"] for job in self.in_progress()], [beta])
        self.assertEqual([job["repo_path"] for job in self.archived()], [alpha])

        self.sync(repo=beta, stage="abandoned")
        self.assertEqual(sorted(job["repo_path"] for job in self.archived()), sorted([alpha, beta]))

    def test_different_jobs_on_one_board_stay_separate_when_one_of_them_closes(self):
        # Every real repository has a board, so the alias rule must never join two different ids.
        repo = self.make_repo("shared")
        self.sync(job_id="001-first", repo=repo, stage="needs-human")
        self.sync(job_id="002-second", repo=repo, stage="needs-human")

        self.sync(job_id="001-first", repo=repo, stage="complete")

        self.assertEqual([job["id"] for job in self.in_progress()], ["002-second"])
        self.assertEqual([job["id"] for job in self.archived()], ["001-first"])

        self.sync(job_id="002-second", repo=repo, stage="abandoned")

        self.assertEqual(self.in_progress(), [])
        self.assertEqual(sorted(job["id"] for job in self.archived()), ["001-first", "002-second"])

    def test_paths_without_a_board_file_keep_the_repo_path_identity(self):
        self.sync(repo="/work/alpha", stage="needs-human")
        self.sync(repo="/work/beta", stage="needs-human")

        self.sync(repo="/work/alpha", stage="complete")

        self.assertEqual([job["repo_path"] for job in self.in_progress()], ["/work/beta"])

    def test_non_terminal_syncs_under_two_paths_stay_two_entries(self):
        main = self.make_repo("main")
        worktree = self.make_worktree_sharing(main)
        self.sync(repo=main, stage="build")
        self.sync(repo=worktree, stage="review")
        self.assertEqual(sorted(job["stage"] for job in self.in_progress()), ["build", "review"])


class ClosingStaleEntriesTests(CentralServerHarness, BoardHarness, unittest.TestCase):
    """The dashboard's close buttons against a real board whose job the board already closed."""

    def setUp(self):
        CentralServerHarness.setUp(self)
        BoardHarness.setUp(self)

    def tearDown(self):
        BoardHarness.tearDown(self)
        CentralServerHarness.tearDown(self)

    def job_in_needs_human(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)
        self.job_file(job_id, "decision.md", "ESCALATE\n\nReady for approval.\n")
        self.factory("decision", job_id)
        return job_id

    def mirror(self, job_id, repo, stage="needs-human"):
        self.sync(job_id=job_id, repo=str(repo), stage=stage, files={"spec.md": "# Spec"})

    def board_job(self, job_id):
        board = json.loads((self.repo / ".factory" / "board.json").read_text(encoding="utf-8"))
        return next(job for job in board["jobs"] if job["id"] == job_id)

    def close(self, action, job_id, repo, reason=""):
        return self.request("POST", f"/api/jobs/{action}", {"id": job_id, "repo_path": str(repo), "reason": reason})

    def test_archiving_from_the_dashboard_completes_the_job(self):
        job_id = self.job_in_needs_human()
        self.mirror(job_id, self.repo)

        status, body = self.close("archive", job_id, self.repo)

        self.assertEqual(status, 200)
        self.assertEqual(body["job"]["stage"], "complete")
        self.assertEqual(self.in_progress(), [])
        [archived] = self.archived()
        self.assertEqual((archived["stage"], archived["files"]), ("complete", {"spec.md": "# Spec"}))
        self.assertIn("completed_at", archived)
        self.assertEqual(self.board_job(job_id)["stage"], "complete")

    def test_a_stale_entry_for_a_job_the_board_completed_is_cleared_without_changing_the_outcome(self):
        job_id = self.job_in_needs_human()
        self.mirror(job_id, self.repo)  # the dashboard last saw needs-human
        self.factory("archive", job_id)  # the board closed it; the push never arrived
        before = self.board_job(job_id)

        status, body = self.close("abandon", job_id, self.repo, "stale")

        self.assertEqual(status, 200)
        self.assertEqual(body["job"]["stage"], "complete")
        self.assertEqual(self.in_progress(), [])
        [archived] = self.archived()
        self.assertEqual((archived["id"], archived["stage"]), (job_id, "complete"))
        self.assertIn("completed_at", archived)
        self.assertEqual(archived["files"], {"spec.md": "# Spec"})
        after = self.board_job(job_id)
        self.assertEqual(after["history"], before["history"])
        self.assertEqual((after["stage"], after["updated"]), ("complete", before["updated"]))

    def test_clearing_a_stale_entry_stores_the_events_the_missed_push_never_delivered(self):
        job_id = self.job_in_needs_human()
        board_events = self.board_job(job_id)["events"]
        # The dashboard last heard the job reach needs-human, then the push for the close was lost.
        self.sync(job_id=job_id, repo=str(self.repo), stage="needs-human", events=board_events)
        self.assertFalse(self.store.job_stats(str(self.repo), job_id)["finished"])
        self.factory("archive", job_id)

        status, body = self.close("abandon", job_id, self.repo, "stale")

        self.assertEqual(status, 200)
        self.assertIs(body["events_stored"], True)
        self.assertNotIn("events", body["job"])
        self.assertNotIn("events", self.archived()[0])
        stats = self.store.job_stats(str(self.repo), job_id)
        self.assertTrue(stats["finished"])
        self.assertEqual(self.store.list_events(str(self.repo), job_id)[-1]["stage"], "complete")

    def test_closing_an_open_job_from_the_dashboard_stores_its_close_event_too(self):
        job_id = self.job_in_needs_human()
        self.mirror(job_id, self.repo)

        status, _ = self.close("archive", job_id, self.repo)

        self.assertEqual(status, 200)
        self.assertNotIn("events", self.archived()[0])
        self.assertTrue(self.store.job_stats(str(self.repo), job_id)["finished"])

    def test_a_stale_entry_for_a_job_the_board_abandoned_is_cleared_through_archive_too(self):
        job_id = self.job_in_needs_human()
        self.mirror(job_id, self.repo)
        self.factory("abandon", job_id, "crashed")

        status, body = self.close("archive", job_id, self.repo)

        self.assertEqual((status, body["job"]["stage"]), (200, "abandoned"))
        self.assertEqual(self.in_progress(), [])
        self.assertEqual([job["stage"] for job in self.archived()], ["abandoned"])
        self.assertEqual(self.board_job(job_id)["warnings"], ["abandoned: crashed"])

    def test_the_symlinked_worktree_entry_left_behind_by_an_archive_can_be_cleared(self):
        job_id = self.job_in_needs_human()
        worktree = Path(self.temp_directory.name) / "worktree"
        worktree.mkdir()
        os.symlink(self.repo / ".factory", worktree / ".factory")
        self.mirror(job_id, self.repo)
        self.mirror(job_id, worktree)
        # What the server held after the archive ran from the main checkout: an Archive entry for
        # the main path while both in-progress entries (one per path to the board) stayed behind.
        self.factory("archive", job_id)
        archived = {**self.board_job(job_id), "repository": "repo", "repo_path": str(self.repo),
                    "worktree_path": str(self.repo), "files": {}, "completed_at": "2026-11-19T10:00:00+00:00"}
        self.module._append_to_archive(archived)
        self.assertEqual([job["repo_path"] for job in self.in_progress()], [str(self.repo), str(worktree)])

        status, _ = self.close("abandon", job_id, worktree, "stale")

        self.assertEqual(status, 200)
        [archived_job] = self.archived()
        self.assertEqual((archived_job["id"], archived_job["stage"]), (job_id, "complete"))
        # The main checkout's entry is the same board job, so it left In Progress as well.
        self.assertEqual(self.in_progress(), [])
        self.assertEqual(archived_job["repo_path"], str(worktree))

    def test_closing_a_job_the_board_cannot_read_reports_an_error_and_leaves_both_stores_alone(self):
        job_id = self.job_in_needs_human()
        self.mirror(job_id, self.repo)
        (self.repo / ".factory" / "board.json").write_text("{corrupt", encoding="utf-8")
        before = self.in_progress()

        status, body = self.close("abandon", job_id, self.repo, "stale")

        self.assertEqual(status, 500)
        self.assertIn("error", body)
        self.assertEqual(self.in_progress(), before)
        self.assertEqual(self.archived(), [])

    def test_an_open_job_at_a_later_stage_than_the_dashboard_shows_is_still_abandoned_for_real(self):
        job_id = self.job_in_needs_human()
        self.mirror(job_id, self.repo, stage="review")  # stale: the board is already at needs-human

        status, body = self.close("abandon", job_id, self.repo, "wrong approach")

        self.assertEqual((status, body["job"]["stage"]), (200, "abandoned"))
        self.assertEqual(self.board_job(job_id)["history"][-1]["abandoned_from"], "needs-human")


if __name__ == "__main__":
    unittest.main()
