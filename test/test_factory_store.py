"""SQLite store for tasks, notes and job events (decisions/factory-workspace.md, D52, D55).

The store is exercised against a real SQLite file in a temporary directory. Expected values come
from the requirements in the decision record, not from the implementation.
"""

import importlib.util
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORE_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "factory" / "scripts" / "factory_store.py"


def load_store_module():
    spec = importlib.util.spec_from_file_location("factory_store_under_test", STORE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="factory-store-")
        self.module = load_store_module()
        self.database_path = Path(self.temp.name) / "data" / "factory.db"
        self.store = self.module.FactoryStore(self.database_path)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)


class SchemaTests(StoreTestCase):
    def test_the_database_file_is_private_to_the_user(self):
        mode = stat.S_IMODE(os.stat(self.database_path).st_mode)
        self.assertEqual(mode & 0o077, 0, f"database is accessible to others: {oct(mode)}")

    def test_reopening_an_existing_database_keeps_its_data(self):
        task = self.store.create_task(title="Keep me", prompt="prompt")
        self.store.close()

        reopened = self.module.FactoryStore(self.database_path)
        self.addCleanup(reopened.close)
        self.assertEqual([item["id"] for item in reopened.list_tasks()], [task["id"]])

    def test_a_database_from_a_newer_version_is_refused_rather_than_downgraded(self):
        self.store.close()
        raw = sqlite3.connect(self.database_path)
        raw.execute(f"PRAGMA user_version = {self.module.SCHEMA_VERSION + 1}")
        raw.commit()
        raw.close()

        with self.assertRaises(self.module.StoreError) as context:
            self.module.FactoryStore(self.database_path)
        self.assertIn("newer", str(context.exception))

    def test_a_failed_open_closes_the_connection_it_had_already_opened(self):
        # Startup fails after sqlite3.connect succeeded (the schema check refuses the file), so the
        # store must close that connection itself: no caller holds a reference to clean it up.
        # Locking cannot show a leak (an idle WAL connection blocks nobody), so the test watches
        # the connections the store opens and asks each one whether it still works.
        self.store.close()
        raw = sqlite3.connect(self.database_path)
        raw.execute(f"PRAGMA user_version = {self.module.SCHEMA_VERSION + 1}")
        raw.commit()
        raw.close()

        opened = []
        real_connect = sqlite3.connect

        def recording_connect(*arguments, **keywords):
            connection = real_connect(*arguments, **keywords)
            opened.append(connection)
            return connection

        self.module.sqlite3 = type("RecordingSqlite", (), {
            "connect": staticmethod(recording_connect), "Row": sqlite3.Row,
        })
        with self.assertRaises(self.module.StoreError):
            self.module.FactoryStore(self.database_path)

        self.assertEqual(len(opened), 1, "expected exactly one connection to have been opened")
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")  # raises "Cannot operate on a closed database"


class TaskTests(StoreTestCase):
    def test_a_new_task_starts_in_the_backlog_at_the_end_of_the_column(self):
        first = self.store.create_task(title="First", prompt="do first")
        second = self.store.create_task(title="Second", prompt="do second")

        self.assertEqual(first["status"], "backlog")
        self.assertEqual(second["status"], "backlog")
        self.assertLess(first["position"], second["position"])
        self.assertEqual([task["title"] for task in self.store.list_tasks()], ["First", "Second"])

    def test_a_task_keeps_its_prompt_text_exactly(self):
        prompt = "Line one\n\n  indented <b>html</b> & 'quotes' \"double\"\n```code```"
        task = self.store.create_task(title="Prompted", prompt=prompt)
        self.assertEqual(self.store.get_task(task["id"])["prompt"], prompt)

    def test_a_title_is_required(self):
        for blank in ("", "   "):
            with self.subTest(title=blank), self.assertRaises(self.module.InvalidInput):
                self.store.create_task(title=blank, prompt="p")

    def test_an_unknown_status_is_rejected(self):
        with self.assertRaises(self.module.InvalidInput):
            self.store.create_task(title="Bad", prompt="p", status="someday")
        task = self.store.create_task(title="Good", prompt="p")
        with self.assertRaises(self.module.InvalidInput):
            self.store.update_task(task["id"], status="someday")
        self.assertEqual(self.store.get_task(task["id"])["status"], "backlog")

    def test_update_changes_only_the_given_fields(self):
        task = self.store.create_task(title="Original", prompt="original prompt", repo_path="/work/alpha")

        updated = self.store.update_task(task["id"], title="Renamed")

        self.assertEqual(updated["title"], "Renamed")
        self.assertEqual(updated["prompt"], "original prompt")
        self.assertEqual(updated["repo_path"], "/work/alpha")

    def test_a_task_can_be_cleared_of_its_repository_and_job(self):
        task = self.store.create_task(title="Linked", prompt="p", repo_path="/work/alpha", job_id="001-x")
        updated = self.store.update_task(task["id"], repo_path=None, job_id=None)
        self.assertIsNone(updated["repo_path"])
        self.assertIsNone(updated["job_id"])

    def test_moving_a_task_to_another_column_places_it_at_the_end_there(self):
        backlog = self.store.create_task(title="Backlog item", prompt="p")
        ready = self.store.create_task(title="Ready item", prompt="p", status="ready")

        moved = self.store.move_task(backlog["id"], status="ready")

        self.assertEqual(moved["status"], "ready")
        ready_titles = [task["title"] for task in self.store.list_tasks() if task["status"] == "ready"]
        self.assertEqual(ready_titles, ["Ready item", "Backlog item"])
        self.assertLess(ready["position"], moved["position"])

    def test_moving_a_task_to_a_position_reorders_its_column(self):
        titles = ["A", "B", "C"]
        tasks = [self.store.create_task(title=title, prompt="p") for title in titles]

        self.store.move_task(tasks[2]["id"], status="backlog", index=0)

        order = [task["title"] for task in self.store.list_tasks() if task["status"] == "backlog"]
        self.assertEqual(order, ["C", "A", "B"])

    def test_an_unknown_task_is_reported_not_silently_ignored(self):
        for action in (
            lambda: self.store.get_task(999),
            lambda: self.store.update_task(999, title="x"),
            lambda: self.store.move_task(999, status="ready"),
            lambda: self.store.delete_task(999),
        ):
            with self.assertRaises(self.module.NotFound):
                action()

    def test_deleting_a_task_also_deletes_its_notes(self):
        task = self.store.create_task(title="Doomed", prompt="p")
        self.store.add_note("remember", task_id=task["id"])

        self.store.delete_task(task["id"])

        self.assertEqual(self.store.list_notes(task_id=task["id"]), [])


class NoteTests(StoreTestCase):
    def test_notes_attach_to_a_task_and_list_newest_first(self):
        task = self.store.create_task(title="Noted", prompt="p")
        self.store.add_note("first", task_id=task["id"])
        self.store.add_note("second", task_id=task["id"])

        self.assertEqual([note["body"] for note in self.store.list_notes(task_id=task["id"])], ["second", "first"])

    def test_notes_attach_to_a_job_identified_by_repository_and_id(self):
        # Job ids restart at 001 in every repository, so notes must not leak between them.
        self.store.add_note("alpha note", repo_path="/work/alpha", job_id="001-first")
        self.store.add_note("beta note", repo_path="/work/beta", job_id="001-first")

        alpha = self.store.list_notes(repo_path="/work/alpha", job_id="001-first")
        self.assertEqual([note["body"] for note in alpha], ["alpha note"])

    def test_a_note_needs_exactly_one_parent(self):
        task = self.store.create_task(title="T", prompt="p")
        with self.assertRaises(self.module.InvalidInput):
            self.store.add_note("orphan")
        with self.assertRaises(self.module.InvalidInput):
            self.store.add_note("both", task_id=task["id"], repo_path="/work/alpha", job_id="001-first")
        with self.assertRaises(self.module.InvalidInput):
            self.store.add_note("half a job key", repo_path="/work/alpha")

    def test_the_database_itself_refuses_a_note_without_exactly_one_parent(self):
        # add_note validates this too; the constraint protects against a future code path that
        # writes notes without going through it.
        task = self.store.create_task(title="T", prompt="p")
        invalid_rows = [
            ("orphan", None, None, None),
            ("both", task["id"], "/work/alpha", "001-first"),
            ("half a job key", None, "/work/alpha", None),
        ]
        for body, task_id, repo_path, job_id in invalid_rows:
            with self.subTest(body=body), self.assertRaises(sqlite3.IntegrityError):
                self.store.connection.execute(
                    "INSERT INTO notes (body, task_id, repo_path, job_id, created) VALUES (?, ?, ?, ?, 'now')",
                    (body, task_id, repo_path, job_id),
                )

    def test_a_blank_note_is_rejected(self):
        task = self.store.create_task(title="T", prompt="p")
        with self.assertRaises(self.module.InvalidInput):
            self.store.add_note("   ", task_id=task["id"])

    def test_a_note_on_an_unknown_task_is_not_found(self):
        with self.assertRaises(self.module.NotFound):
            self.store.add_note("lost", task_id=999)

    def test_deleting_a_note_removes_only_that_note(self):
        task = self.store.create_task(title="T", prompt="p")
        keep = self.store.add_note("keep", task_id=task["id"])
        drop = self.store.add_note("drop", task_id=task["id"])

        self.store.delete_note(drop["id"])

        self.assertEqual([note["id"] for note in self.store.list_notes(task_id=task["id"])], [keep["id"]])
        with self.assertRaises(self.module.NotFound):
            self.store.delete_note(drop["id"])


class EventTests(StoreTestCase):
    def event(self, stage, round_number=0, at="2026-10-30T10:00:00Z"):
        return {"stage": stage, "round": round_number, "at": at}

    def test_replaying_the_same_events_does_not_duplicate_them(self):
        events = [self.event("spec"), self.event("build", 1, "2026-10-30T10:05:00Z")]
        self.store.record_events("/work/alpha", "001-first", events)
        self.store.record_events("/work/alpha", "001-first", events)

        self.assertEqual(len(self.store.list_events("/work/alpha", "001-first")), 2)

    def test_events_are_returned_in_time_order_per_job(self):
        self.store.record_events("/work/alpha", "001-first", [
            self.event("build", 1, "2026-10-30T10:05:00Z"),
            self.event("spec", 0, "2026-10-30T10:00:00Z"),
        ])
        self.store.record_events("/work/beta", "001-first", [self.event("spec")])

        stages = [event["stage"] for event in self.store.list_events("/work/alpha", "001-first")]
        self.assertEqual(stages, ["spec", "build"])

    def test_malformed_events_are_rejected_without_storing_the_valid_ones(self):
        # A partial write would leave stats that silently disagree with the board.
        with self.assertRaises(self.module.InvalidInput):
            self.store.record_events("/work/alpha", "001-first", [
                self.event("spec"),
                {"stage": "build", "round": "one", "at": "2026-10-30T10:05:00Z"},
            ])
        self.assertEqual(self.store.list_events("/work/alpha", "001-first"), [])

    def test_an_event_with_an_unparseable_time_is_rejected(self):
        with self.assertRaises(self.module.InvalidInput):
            self.store.record_events("/work/alpha", "001-first", [self.event("spec", at="yesterday")])


class StatsTests(StoreTestCase):
    """Stats derive from events. Times use fixed offsets so the expected values are hand-computed."""

    def record(self, *steps, repo="/work/alpha", job="001-first"):
        events = [{"stage": stage, "round": round_number, "at": at} for stage, round_number, at in steps]
        self.store.record_events(repo, job, events)

    def test_a_job_without_events_has_no_stats(self):
        self.assertIsNone(self.store.job_stats("/work/alpha", "001-missing"))

    def test_time_in_each_stage_is_the_gap_to_the_next_transition(self):
        self.record(
            ("spec", 0, "2026-10-30T10:00:00Z"),
            ("spec-review", 0, "2026-10-30T10:10:00Z"),
            ("build", 1, "2026-10-30T10:40:00Z"),
            ("needs-human", 1, "2026-10-30T11:00:00Z"),
        )

        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T11:30:00Z")

        self.assertEqual(stats["seconds_by_stage"], {
            "spec": 600, "spec-review": 1800, "build": 1200, "needs-human": 1800,
        })
        self.assertEqual(stats["total_seconds"], 5400)

    def test_human_wait_is_separated_from_agent_time(self):
        self.record(
            ("spec", 0, "2026-10-30T10:00:00Z"),
            ("spec-review", 0, "2026-10-30T10:10:00Z"),
            ("build", 1, "2026-10-30T10:40:00Z"),
            ("needs-human", 1, "2026-10-30T11:00:00Z"),
        )

        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T11:30:00Z")

        self.assertEqual(stats["human_seconds"], 1800 + 1800)
        self.assertEqual(stats["agent_seconds"], 600 + 1200)

    def test_a_finished_job_stops_the_clock_at_its_terminal_event(self):
        self.record(
            ("spec", 0, "2026-10-30T10:00:00Z"),
            ("abandoned", 0, "2026-10-30T10:30:00Z"),
        )

        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-31T10:00:00Z")

        self.assertEqual(stats["total_seconds"], 1800)
        self.assertTrue(stats["finished"])
        self.assertNotIn("abandoned", stats["seconds_by_stage"])

    def test_a_running_job_counts_time_up_to_now(self):
        self.record(("build", 1, "2026-10-30T10:00:00Z"))
        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T10:15:00Z")
        self.assertEqual(stats["seconds_by_stage"], {"build": 900})
        self.assertFalse(stats["finished"])

    def test_a_stage_visited_twice_adds_up(self):
        self.record(
            ("build", 1, "2026-10-30T10:00:00Z"),
            ("test-audit", 1, "2026-10-30T10:10:00Z"),
            ("build", 2, "2026-10-30T10:20:00Z"),
            ("test-audit", 2, "2026-10-30T10:35:00Z"),
            ("needs-human", 2, "2026-10-30T10:40:00Z"),
        )

        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T10:40:00Z")

        self.assertEqual(stats["seconds_by_stage"]["build"], 600 + 900)
        self.assertEqual(stats["seconds_by_stage"]["test-audit"], 600 + 300)

    def test_rounds_and_rebuilds_come_from_build_events(self):
        self.record(
            ("build", 1, "2026-10-30T10:00:00Z"),
            ("test-audit", 1, "2026-10-30T10:10:00Z"),
            ("build", 2, "2026-10-30T10:20:00Z"),
            ("review", 2, "2026-10-30T10:30:00Z"),
            ("build", 3, "2026-10-30T10:40:00Z"),
            ("needs-human", 3, "2026-10-30T10:50:00Z"),
        )

        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T10:50:00Z")

        self.assertEqual(stats["rounds"], 3)
        self.assertEqual(stats["rebuilds"], 2)

    def test_agent_count_follows_the_roles_each_stage_runs(self):
        # spec-writer 1, builder 1, test-auditor 1, five reviewers, stride 1, approver 1.
        self.record(
            ("spec", 0, "2026-10-30T10:00:00Z"),
            ("spec-review", 0, "2026-10-30T10:05:00Z"),
            ("build", 1, "2026-10-30T10:10:00Z"),
            ("test-audit", 1, "2026-10-30T10:20:00Z"),
            ("review", 1, "2026-10-30T10:30:00Z"),
            ("stride-review", 1, "2026-10-30T10:40:00Z"),
            ("quality-gate", 1, "2026-10-30T10:50:00Z"),
            ("approver", 1, "2026-10-30T10:55:00Z"),
            ("needs-human", 1, "2026-10-30T11:00:00Z"),
        )

        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T11:00:00Z")

        self.assertEqual(stats["agents"], 1 + 1 + 1 + 5 + 1 + 1)

    def test_a_rebuild_round_counts_its_agents_again(self):
        self.record(
            ("build", 1, "2026-10-30T10:00:00Z"),
            ("test-audit", 1, "2026-10-30T10:10:00Z"),
            ("build", 2, "2026-10-30T10:20:00Z"),
            ("needs-human", 2, "2026-10-30T10:30:00Z"),
        )

        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T10:30:00Z")

        self.assertEqual(stats["agents"], 1 + 1 + 1)

    def test_the_quality_gate_runs_no_agent(self):
        self.record(
            ("quality-gate", 1, "2026-10-30T10:00:00Z"),
            ("needs-human", 1, "2026-10-30T10:05:00Z"),
        )
        stats = self.store.job_stats("/work/alpha", "001-first", now="2026-10-30T10:05:00Z")
        self.assertEqual(stats["agents"], 0)


if __name__ == "__main__":
    unittest.main()
