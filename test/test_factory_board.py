import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOARD_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "factory" / "scripts" / "factory_board.py"


class FactoryBoardTests(unittest.TestCase):
    """Drive the real board script against disposable Git repositories."""

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory(prefix="engineering-guard-factory-")
        self.repo = Path(self.temp_directory.name) / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.email", "factory@example.com")
        self.git("config", "user.name", "Factory Test")
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.git("add", "app.py")
        self.git("commit", "--quiet", "-m", "initial")

    def tearDown(self):
        self.temp_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(
            ["git", *arguments], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout

    def factory(self, *arguments, expect_error=False):
        result = subprocess.run(
            [sys.executable, str(BOARD_SCRIPT), *arguments],
            cwd=self.repo, capture_output=True, text=True,
        )
        output = json.loads(result.stdout)
        if expect_error:
            self.assertEqual(result.returncode, 2, result.stdout)
            return output["error"]
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return output

    def job_file(self, job_id, relative_path, text):
        path = self.repo / ".factory" / "jobs" / job_id / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def job_in_review(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        self.factory("spec-written", job_id)
        self.factory("approve-spec", job_id)
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.pass_test_audit(job_id, 1)
        return job_id

    def simulate_build(self, job_id, report="built\n"):
        (self.repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.job_file(job_id, "build.md", report)

    def pass_test_audit(self, job_id, round_number):
        self.job_file(job_id, f"round-{round_number}/test-audit.md", "VERDICT: PASS\n")
        return self.factory("test-audit-done", job_id)

    def write_reviews(self, job_id, round_number, verdicts):
        for reviewer, verdict in verdicts.items():
            self.job_file(job_id, f"round-{round_number}/review-{reviewer}.md", f"VERDICT: {verdict}\n\nNotes.\n")

    def test_factory_output_is_excluded_locally_without_touching_tracked_files(self):
        self.factory("init")
        self.factory("init")
        exclude = (self.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.splitlines().count("/.factory/"), 1)
        self.assertFalse((self.repo / ".gitignore").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_build_cannot_start_before_human_spec_approval(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        error = self.factory("spec-written", job_id, expect_error=True)
        self.assertIn("feature.md", error)
        self.job_file(job_id, "feature.md", "Investigate and fix the login bug\n")
        error = self.factory("spec-written", job_id, expect_error=True)
        self.assertIn("prompt.md", error)

        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        self.assertEqual(self.factory("spec-written", job_id)["stage"], "spec-review")
        self.job_file(job_id, "build.md", "built\n")
        error = self.factory("build-done", job_id, expect_error=True)
        self.assertIn("spec-review", error)

    def test_spec_approval_is_recorded_in_the_spec_the_builder_reads(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "# Rate limiting\n\n**Status:** Proposed — awaiting human spec approval\n\nBody\n")
        self.factory("spec-written", job_id)
        self.factory("approve-spec", job_id)

        spec = (self.repo / ".factory" / "jobs" / job_id / "spec.md").read_text(encoding="utf-8")
        self.assertNotIn("Proposed", spec)
        self.assertIn("**Status:** Approved by the human via `approve-spec`", spec)
        self.assertIn("Body", spec)

    def test_build_without_changes_is_rejected_and_blocked_builds_go_to_the_human(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        self.factory("spec-written", job_id)
        self.factory("approve-spec", job_id)

        self.job_file(job_id, "build.md", "No changes made.\n")
        self.assertIn("produced no changes", self.factory("build-done", job_id, expect_error=True))

        self.job_file(job_id, "build.md", "BLOCKED: needs a production credential\n\nDetails.\n")
        job = self.factory("build-done", job_id)
        self.assertEqual(job["stage"], "needs-human")
        self.assertTrue(any("production credential" in warning for warning in job["warnings"]))

    def test_spec_approval_refuses_a_dirty_worktree(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        self.factory("spec-written", job_id)
        (self.repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

        error = self.factory("approve-spec", job_id, expect_error=True)
        self.assertIn("app.py", error)

        self.git("checkout", "--", "app.py")
        job = self.factory("approve-spec", job_id)
        self.assertEqual(job["stage"], "build")
        self.assertEqual(job["base"], self.git("rev-parse", "HEAD").strip())

    def test_round_waits_for_every_reviewer_and_rejects_bad_headers(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "code": "PASS", "ux": "N/A"})
        self.job_file(job_id, "round-1/review-ui.md", "Looks good to me\n")

        status = self.factory("round-status", job_id)
        self.assertFalse(status["complete"])
        self.assertEqual(status["next"], "wait")
        self.assertEqual(status["job"]["reviews"]["ui"], "invalid")
        self.assertEqual(status["job"]["stage"], "review")

        self.write_reviews(job_id, 1, {"ui": "N/A"})
        status = self.factory("round-status", job_id)
        self.assertTrue(status["complete"])
        self.assertEqual(status["next"], "approver")

    def test_changes_trigger_one_rebuild_then_escalate_at_round_limit(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "CHANGES", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        status = self.factory("round-status", job_id)
        self.assertEqual(status["next"], "rebuild")
        self.assertEqual(status["job"]["round"], 2)
        self.assertEqual(status["job"]["stage"], "build")

        self.factory("build-done", job_id)
        self.pass_test_audit(job_id, 2)
        self.write_reviews(job_id, 2, {"security": "CHANGES", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        status = self.factory("round-status", job_id)
        self.assertEqual(status["next"], "approver")
        self.assertEqual([entry["round"] for entry in status["job"]["history"]], [1, 2])

    def test_reviewers_wait_for_a_passing_test_audit(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        self.factory("spec-written", job_id)
        self.factory("approve-spec", job_id)
        self.simulate_build(job_id)
        self.assertEqual(self.factory("build-done", job_id)["stage"], "test-audit")
        self.assertIn("test-audit", self.factory("round-status", job_id, expect_error=True))

        self.job_file(job_id, "round-1/test-audit.md", "VERDICT: N/A\n")
        self.assertIn("PASS or VERDICT: CHANGES", self.factory("test-audit-done", job_id, expect_error=True))

        self.job_file(job_id, "round-1/test-audit.md", "VERDICT: CHANGES\n\nNo test for the limit.\n")
        result = self.factory("test-audit-done", job_id)
        self.assertEqual(result["next"], "rebuild")
        self.assertEqual((result["job"]["stage"], result["job"]["round"]), ("build", 2))

        # At the round limit, unresolved test findings no longer block the reviewers
        # but must stay visible to the approver and the human.
        self.factory("build-done", job_id)
        self.job_file(job_id, "round-2/test-audit.md", "VERDICT: CHANGES\n\nStill weak.\n")
        result = self.factory("test-audit-done", job_id)
        self.assertEqual(result["next"], "review")
        self.assertEqual(result["job"]["reviews"]["code"], "pending")
        self.write_reviews(job_id, 2, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        status = self.factory("round-status", job_id)
        self.assertEqual(status["next"], "approver")
        self.assertTrue(any("test audit" in warning for warning in status["job"]["warnings"]))
        self.assertEqual([entry["test_audit"] for entry in status["job"]["history"]], ["CHANGES", "CHANGES"])

    def test_decision_must_escalate_and_rework_reopens_the_build(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("round-status", job_id)

        self.job_file(job_id, "decision.md", "APPROVE\n\nShip it.\n")
        error = self.factory("decision", job_id, expect_error=True)
        self.assertIn("ESCALATE", error)

        self.job_file(job_id, "decision.md", "ESCALATE\n\nReady for human approval.\n")
        self.assertEqual(self.factory("decision", job_id)["stage"], "needs-human")

        job = self.factory("rework", job_id, "Use a sliding window")
        self.assertEqual((job["stage"], job["round"], job["round_limit"]), ("build", 2, 3))
        note = self.repo / ".factory" / "jobs" / job_id / "rework-2.md"
        self.assertIn("sliding window", note.read_text(encoding="utf-8"))

    def test_next_takes_the_first_unchecked_backlog_item_once(self):
        self.factory("init")
        backlog = self.repo / ".factory" / "backlog.md"
        backlog.write_text("- [x] Done thing\n- [ ] Export CSV\n- [ ] Dark mode\n", encoding="utf-8")

        self.assertEqual(self.factory("new", "--from-backlog")["title"], "Export CSV")
        self.assertEqual(self.factory("new", "--from-backlog")["id"], "002-dark-mode")
        self.assertIn("backlog has no unchecked items", self.factory("new", "--from-backlog", expect_error=True))

    def test_models_rejects_presets_the_cli_cannot_run(self):
        error = self.factory("models", "sol-luna", "--cli", "claude", expect_error=True)
        self.assertIn("not available on claude", error)

        config = self.factory("models", "luna", "--cli", "codex")
        self.assertEqual(set(config["stages"].values()), {"gpt-6.1-luna"})

        config = self.factory("models", "big-model", "small-model", "--cli", "kilo")
        self.assertEqual(config["stages"]["security"], "big-model")
        self.assertEqual(config["stages"]["code"], "small-model")

    def test_claude_install_pins_models_and_limits_editing_to_the_builder(self):
        claude_home = Path(self.temp_directory.name) / "claude-home"
        self.factory("models", "luna", "--cli", "codex")
        error = self.factory("install-claude", "--claude-home", str(claude_home), expect_error=True)
        self.assertIn("written for codex", error)

        self.factory("models", "opus-sonnet", "--cli", "claude")
        self.factory("install-claude", "--claude-home", str(claude_home))
        agents = claude_home / "agents"
        builder = (agents / "eg-builder.md").read_text(encoding="utf-8")
        code_review = (agents / "eg-review-code.md").read_text(encoding="utf-8")
        self.assertIn("model: opus", builder)
        self.assertIn("Edit", builder)
        self.assertIn("model: sonnet", code_review)
        self.assertNotIn("Edit", code_review)
        self.assertIn("model: opus", (agents / "eg-review-security.md").read_text(encoding="utf-8"))
        self.assertNotIn("Edit", (agents / "eg-test-auditor.md").read_text(encoding="utf-8"))

        # The pointer must work from any repository, so it names the shared skill absolutely.
        pointer = (claude_home / "skills" / "engineering-guard-factory" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(str(BOARD_SCRIPT.parents[1] / "SKILL.md"), pointer)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_rework_refuses_while_another_job_is_building(self):
        first = self.job_in_review()
        self.write_reviews(first, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("round-status", first)
        self.job_file(first, "decision.md", "ESCALATE\n")
        self.factory("decision", first)
        self.git("commit", "--quiet", "-am", "human commits job one")

        second = self.factory("new", "Export CSV")["id"]
        self.job_file(second, "feature.md", "feature\n")
        self.job_file(second, "prompt.md", "prompt\n")
        self.job_file(second, "spec.md", "spec\n")
        self.factory("spec-written", second)
        self.factory("approve-spec", second)

        error = self.factory("rework", first, "Tighten limits", expect_error=True)
        self.assertIn(second, error)

if __name__ == "__main__":
    unittest.main()
