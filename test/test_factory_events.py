"""Stage-transition events recorded by the board (decisions/factory-workspace.md, D54, R2).

The dashboard derives run statistics from these events, so the board is the component that must
record them: only it sees a job change stage. Each test drives the real board script in a
disposable Git repository.
"""

import json
import re
import unittest

from test_factory_board import FactoryBoardHarness

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class StageEventTests(FactoryBoardHarness, unittest.TestCase):
    def events(self, job_id):
        return self.factory("show", job_id)["events"]

    def stages(self, job_id):
        return [event["stage"] for event in self.events(job_id)]

    def test_a_new_job_records_its_first_event_in_the_spec_stage(self):
        job_id = self.factory("new", "Add rate limiting")["id"]

        [event] = self.events(job_id)
        self.assertEqual((event["stage"], event["round"]), ("spec", 0))
        self.assertRegex(event["at"], TIMESTAMP)

    def test_every_transition_is_recorded_once_in_order(self):
        job_id = self.job_in_review()

        self.assertEqual(self.stages(job_id), ["spec", "spec-review", "build", "test-audit", "review"])

    def test_saving_without_a_transition_adds_no_event(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        before = self.events(job_id)

        # record-model saves the job (and refreshes `updated`) but the stage does not change.
        self.factory("record-model", job_id, "spec", "some-model")

        self.assertEqual(self.events(job_id), before)

    def test_a_rebuild_is_a_new_event_even_though_the_stage_name_repeats(self):
        job_id = self.job_in_review_after_failed_test_audit()

        builds = [event for event in self.events(job_id) if event["stage"] == "build"]
        self.assertEqual([event["round"] for event in builds], [1, 2])

    def test_closing_a_job_records_the_terminal_stage(self):
        job_id = self.factory("new", "Add rate limiting")["id"]

        self.factory("abandon", job_id, "no longer needed")

        self.assertEqual(self.stages(job_id), ["spec", "abandoned"])

    def test_archiving_a_job_records_the_complete_stage(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)
        self.job_file(job_id, "decision.md", "ESCALATE\n\nReady.\n")
        self.factory("decision", job_id)

        self.factory("archive", job_id)

        self.assertEqual(self.stages(job_id)[-2:], ["needs-human", "complete"])

    def test_a_job_created_before_events_existed_starts_recording_from_its_current_stage(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        board_path = self.repo / ".factory" / "board.json"
        board = json.loads(board_path.read_text(encoding="utf-8"))
        del board["jobs"][0]["events"]
        board_path.write_text(json.dumps(board), encoding="utf-8")

        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        self.factory("spec-written", job_id)

        # Nothing is invented for history the board never saw: only the transition it made.
        self.assertEqual(self.stages(job_id), ["spec-review"])


if __name__ == "__main__":
    unittest.main()
