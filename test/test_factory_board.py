import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOARD_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "factory" / "scripts" / "factory_board.py"


class FactoryBoardHarness:
    """Disposable Git repository plus helpers that drive the real board script.

    A mixin rather than a base TestCase so other test modules can reuse it without
    unittest re-collecting and re-running every board test inside the subclass.
    """

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
            env={**os.environ, "FACTORY_DISABLE_CENTRAL_SYNC": "1"},
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

    def job_in_review_after_failed_test_audit(self):
        job_id = self.approved_job()
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.job_file(job_id, "round-1/test-audit.md", "VERDICT: CHANGES\n\nNo test for the limit.\n")
        self.assertEqual(self.factory("test-audit-done", job_id)["next"], "rebuild")
        self.factory("build-done", job_id)
        self.pass_test_audit(job_id, 2)
        return job_id

    def approved_job(self, spec="spec\n"):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", spec)
        self.factory("spec-written", job_id)
        self.factory("approve-spec", job_id)
        return job_id

    def simulate_build(self, job_id, report="built\n"):
        (self.repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.job_file(job_id, "build.md", report)

    def pass_test_audit(self, job_id, round_number):
        self.job_file(job_id, f"round-{round_number}/test-audit.md", "VERDICT: PASS\n")
        return self.factory("test-audit-done", job_id)

    def write_reviews(self, job_id, round_number, verdicts):
        # Most tests exercise round, STRIDE or gate mechanics and name only the four original
        # reviewers; the architecture review is then fixture setup, not the behaviour under test.
        # Tests about the architecture reviewer pass it explicitly and are unaffected.
        verdicts = {"architecture": "N/A", **verdicts}
        for reviewer, verdict in verdicts.items():
            body = "Notes.\n"
            # security/stride CHANGES must cite a CRITICAL/HIGH finding (severity floor);
            # tests that only care about the round mechanics use this default finding.
            if verdict == "CHANGES" and reviewer in ("security", "stride"):
                body = "SEVERITY: HIGH\nPlaceholder finding for round mechanics.\n"
            self.job_file(job_id, f"round-{round_number}/review-{reviewer}.md", f"VERDICT: {verdict}\n\n{body}")

    def pass_stride_review(self, job_id, round_number):
        """Finish stride-review with a PASS; the job then waits at the quality gate."""
        self.job_file(job_id, f"round-{round_number}/review-stride.md", "VERDICT: PASS\n")
        return self.factory("stride-review-done", job_id)

    def close_round_to_approver(self, job_id, round_number):
        """close-round stops at stride-review, which leads to the quality gate; most tests
        only care about reaching the approver, so this walks all three."""
        self.assertEqual(self.factory("close-round", job_id)["next"], "stride-review")
        self.assertEqual(self.pass_stride_review(job_id, round_number)["next"], "quality-gate")
        result = self.factory("quality-gate-done", job_id)
        self.assertEqual(result["next"], "approver")
        return result



class FactoryBoardTests(FactoryBoardHarness, unittest.TestCase):
    """Rules of the board state machine."""

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
        self.assertEqual(status["reviews"]["ui"], "invalid")
        # Progress is saved for the dashboard even though the stage does not move.
        self.assertEqual(self.factory("show", job_id)["reviews"]["security"], "PASS")
        self.assertIn("ui", self.factory("close-round", job_id, expect_error=True))
        self.assertEqual(self.factory("show", job_id)["stage"], "review")

        self.write_reviews(job_id, 1, {"ui": "N/A"})
        # round-status is read-only: calling it twice must not advance the job.
        self.factory("round-status", job_id)
        status = self.factory("round-status", job_id)
        self.assertEqual((status["complete"], status["next"]), (True, "close-round"))
        self.assertEqual(self.factory("close-round", job_id)["next"], "stride-review")

    def test_security_and_code_cannot_be_not_applicable_and_changes_need_findings(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "N/A", "ux": "N/A", "ui": "N/A"})
        self.job_file(job_id, "round-1/review-code.md", "VERDICT: CHANGES\n\n")

        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["security"], "invalid")
        self.assertEqual(status["reviews"]["code"], "invalid")
        problems = " ".join(status["invalid"].values())
        self.assertIn("VERDICT: PASS or VERDICT: CHANGES", problems)
        self.assertIn("needs at least one finding", problems)

    def test_security_changes_needs_a_critical_or_high_severity_line(self):
        job_id = self.job_in_review()
        self.job_file(
            job_id, "round-1/review-security.md",
            "VERDICT: CHANGES\n\nSEVERITY: MEDIUM\nStale dependency, no known exploit path.\n",
        )
        self.write_reviews(job_id, 1, {"ux": "N/A", "ui": "N/A", "code": "PASS"})

        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["security"], "invalid")
        self.assertIn("SEVERITY: CRITICAL", " ".join(status["invalid"].values()))

        # A HIGH finding is enough to legitimately block the round.
        self.job_file(
            job_id, "round-1/review-security.md",
            "VERDICT: CHANGES\n\nSEVERITY: HIGH\nMissing authorization check on DELETE /items/:id.\n",
        )
        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["security"], "CHANGES")

    def test_security_pass_may_carry_lower_severity_notes(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.job_file(
            job_id, "round-1/review-security.md",
            "VERDICT: PASS\n\nSEVERITY: LOW\nConsider rotating the sample API key in fixtures.\n",
        )
        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["security"], "PASS")
        self.assertEqual(self.factory("close-round", job_id)["next"], "stride-review")

    def test_review_changes_trigger_one_rebuild_then_escalate(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "CHANGES", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        result = self.factory("close-round", job_id)
        self.assertEqual(result["next"], "rebuild")
        self.assertEqual((result["job"]["round"], result["job"]["stage"]), (2, "build"))

        self.factory("build-done", job_id)
        self.pass_test_audit(job_id, 2)
        self.write_reviews(job_id, 2, {"security": "CHANGES", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        result = self.factory("close-round", job_id)
        self.assertEqual(result["next"], "stride-review")
        self.assertEqual([entry["round"] for entry in result["job"]["history"]], [1, 2])
        self.assertEqual(self.pass_stride_review(job_id, 2)["next"], "quality-gate")

    def test_stride_review_runs_once_per_job_after_the_four_reviewers_pass(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        result = self.factory("close-round", job_id)
        self.assertEqual(result["next"], "stride-review")
        self.assertEqual(result["job"]["stage"], "stride-review")
        self.assertEqual(result["job"]["stride"], "pending")

        # stride-review-done is only valid once the job has actually reached that stage.
        self.assertIn("stride-review", self.factory("decision", job_id, expect_error=True))

        error = self.factory("stride-review-done", job_id, expect_error=True)
        self.assertIn("review-stride.md", error)

        self.job_file(job_id, "round-1/review-stride.md", "not a verdict at all\n")
        error = self.factory("stride-review-done", job_id, expect_error=True)
        self.assertIn("VERDICT: PASS or VERDICT: CHANGES", error)

        result = self.pass_stride_review(job_id, 1)
        self.assertEqual(result["next"], "quality-gate")
        self.assertEqual(result["job"]["stage"], "quality-gate")
        self.assertEqual(result["job"]["stride"], "PASS")

    def test_stride_review_changes_needs_critical_or_high_and_consumes_a_review_round(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)

        # A MEDIUM-only STRIDE finding must not block, same severity floor as security.
        self.job_file(
            job_id, "round-1/review-stride.md",
            "VERDICT: CHANGES\n\nSEVERITY: MEDIUM\nOpen finding I-004, pre-existing, not newly introduced.\n",
        )
        error = self.factory("stride-review-done", job_id, expect_error=True)
        self.assertIn("SEVERITY: CRITICAL", error)

        # A newly-introduced CRITICAL finding legitimately sends the job back to build,
        # consuming a round from the same budget the four reviewers share.
        self.job_file(
            job_id, "round-1/review-stride.md",
            "VERDICT: CHANGES\n\nSEVERITY: CRITICAL\nE-002: new endpoint reuses the unauthenticated "
            "legacy router at api/legacy.py:40.\n",
        )
        result = self.factory("stride-review-done", job_id)
        self.assertEqual(result["next"], "rebuild")
        self.assertEqual((result["job"]["round"], result["job"]["stage"]), (2, "build"))
        # close-round already spent one round getting the four reviewers to all-PASS;
        # this STRIDE rebuild spends the attempt's second and last review round.
        self.assertEqual(result["job"]["attempt"]["review_rounds"], 2)

        # The budget is now exhausted, so the rebuilt round's reviewers no longer get
        # a further rebuild even if one of them still finds a CRITICAL/HIGH issue: the
        # job goes straight to the approver with the finding carried as a warning.
        self.factory("build-done", job_id)
        self.pass_test_audit(job_id, 2)
        self.write_reviews(job_id, 2, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.assertEqual(self.factory("close-round", job_id)["next"], "stride-review")

        self.job_file(
            job_id, "round-2/review-stride.md",
            "VERDICT: CHANGES\n\nSEVERITY: CRITICAL\nE-002 still present after the fix.\n",
        )
        result = self.factory("stride-review-done", job_id)
        self.assertEqual(result["next"], "quality-gate")
        self.assertEqual(result["job"]["stage"], "quality-gate")
        self.assertTrue(any("STRIDE" in warning for warning in result["job"]["warnings"]))

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
        status = self.factory("close-round", job_id)
        self.assertEqual(status["next"], "stride-review")
        self.assertTrue(any("test audit" in warning for warning in status["job"]["warnings"]))
        self.assertEqual([entry["test_audit"] for entry in status["job"]["history"]], ["CHANGES", "CHANGES"])
        self.assertEqual(self.pass_stride_review(job_id, 2)["next"], "quality-gate")

    def test_test_audit_rebuilds_do_not_use_up_review_rounds(self):
        job_id = self.job_in_review_after_failed_test_audit()
        # Round 2 passed the audit; reviewers still get their full two rounds.
        self.write_reviews(job_id, 2, {"security": "CHANGES", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        result = self.factory("close-round", job_id)
        self.assertEqual((result["next"], result["job"]["round"]), ("rebuild", 3))

    def test_decision_must_escalate_and_rework_reopens_the_build(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)

        self.job_file(job_id, "decision.md", "APPROVE\n\nShip it.\n")
        error = self.factory("decision", job_id, expect_error=True)
        self.assertIn("ESCALATE", error)

        self.job_file(job_id, "decision.md", "ESCALATE\n\nReady for human approval.\n")
        self.assertEqual(self.factory("decision", job_id)["stage"], "needs-human")

        job = self.factory("rework", job_id, "Use a sliding window")
        self.assertEqual((job["stage"], job["round"]), ("build", 2))
        self.assertEqual(job["attempt"], {"review_rounds": 0, "test_rebuilds": 0, "gate_fixes": 0})
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
        self.close_round_to_approver(first, 1)
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

    def test_every_reviewer_gets_the_same_snapshot_including_untracked_files(self):
        job_id = self.approved_job()
        (self.repo / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
        (self.repo / "limits.py").write_text("LIMIT = 5\n", encoding="utf-8")
        self.job_file(job_id, "build.md", "built\n")
        job = self.factory("build-done", job_id)

        round_directory = self.repo / ".factory" / "jobs" / job_id / "round-1"
        patch = (round_directory / "change.patch").read_text(encoding="utf-8")
        self.assertIn("+VALUE = 2", patch)
        self.assertIn("+LIMIT = 5", patch)
        self.assertEqual((round_directory / "files.txt").read_text(encoding="utf-8"), "app.py\nlimits.py\n")
        self.assertEqual(job["changed_files"], ["app.py", "limits.py"])

    def test_ui_is_skipped_only_without_ui_impact_or_visual_files_and_ux_always_runs(self):
        spec = "**UI impact:** no\n"
        job_id = self.approved_job(spec)
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        result = self.pass_test_audit(job_id, 1)
        self.assertEqual(result["spawn"], ["security", "ux", "code", "architecture"])
        self.assertEqual((result["job"]["reviews"]["ux"], result["job"]["reviews"]["ui"]), ("pending", "N/A"))
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)

        self.job_file(job_id, "decision.md", "ESCALATE\n")
        self.factory("decision", job_id)
        self.git("commit", "--quiet", "-am", "human commits")
        other = self.approved_job(spec)
        (self.repo / "page.html").write_text("<p>hi</p>\n", encoding="utf-8")
        self.job_file(other, "build.md", "built\n")
        self.factory("build-done", other)
        result = self.pass_test_audit(other, 1)
        self.assertEqual(result["spawn"], ["security", "ux", "ui", "code", "architecture"])

    def test_ui_impact_mentioned_outside_its_field_line_does_not_skip_review(self):
        job_id = self.approved_job("**UI impact:** yes\n\nAn earlier draft said UI impact: no.\n")
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.assertEqual(self.pass_test_audit(job_id, 1)["spawn"], ["security", "ux", "ui", "code", "architecture"])

    def test_snapshot_handles_files_that_are_not_utf8(self):
        job_id = self.approved_job()
        (self.repo / "app.py").write_bytes("NAME = 'caf\xe9'\n".encode("latin-1"))
        (self.repo / "legacy.txt").write_bytes("na\xefve\n".encode("latin-1"))
        self.job_file(job_id, "build.md", "built\n")
        self.assertEqual(self.factory("build-done", job_id)["stage"], "test-audit")
        patch = (self.repo / ".factory" / "jobs" / job_id / "round-1" / "change.patch").read_bytes()
        self.assertIn("caf\xe9".encode("latin-1"), patch)
        self.assertIn("na\xefve".encode("latin-1"), patch)

    def test_renamed_files_are_reported_by_their_real_paths(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        for name in ("feature.md", "prompt.md", "spec.md"):
            self.job_file(job_id, name, "x\n")
        self.factory("spec-written", job_id)
        self.git("mv", "app.py", "renamed app.py")

        error = self.factory("approve-spec", job_id, expect_error=True)
        self.assertIn("'renamed app.py'", error)
        self.assertNotIn("->", error)

    def test_spec_feedback_is_saved_for_the_spec_writer_and_reopens_the_spec(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        self.factory("spec-written", job_id)

        result = self.factory("spec-feedback", job_id, "Limit per IP, not per user")
        self.assertEqual(result["job"]["stage"], "spec")
        feedback = self.repo / ".factory" / "jobs" / job_id / "spec-feedback-1.md"
        self.assertIn("per IP", feedback.read_text(encoding="utf-8"))
        self.assertIn("stage 'spec'", self.factory("approve-spec", job_id, expect_error=True))
        self.factory("spec-written", job_id)
        self.factory("spec-feedback", job_id, "Also log rejections")
        self.assertTrue((feedback.parent / "spec-feedback-2.md").is_file())

    def test_abandoning_a_stuck_job_frees_the_worktree_and_resume_explains_next_step(self):
        stuck = self.job_in_review()
        self.assertIn("spawn reviewers", self.factory("resume", stuck)["next"])
        self.git("checkout", "--", "app.py")

        second = self.factory("new", "Export CSV")["id"]
        for name in ("feature.md", "prompt.md", "spec.md"):
            self.job_file(second, name, "x\n")
        self.factory("spec-written", second)
        self.assertIn(stuck, self.factory("approve-spec", second, expect_error=True))

        self.assertIn("reason", self.factory("abandon", stuck, " ", expect_error=True))
        job = self.factory("abandon", stuck, "session crashed")
        self.assertEqual(job["stage"], "abandoned")
        self.assertEqual(self.factory("approve-spec", second)["stage"], "build")
        self.assertIn("already abandoned", self.factory("abandon", stuck, "again", expect_error=True))
        self.assertIn("nothing", self.factory("resume", stuck)["next"])

    def test_archive_closes_an_approved_job_and_only_from_needs_human(self):
        job_id = self.job_in_review()
        self.assertIn("needs-human", self.factory("archive", job_id, expect_error=True))

        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)
        self.job_file(job_id, "decision.md", "ESCALATE\n\nReady for approval.\n")
        self.factory("decision", job_id)

        job = self.factory("archive", job_id)
        self.assertEqual(job["stage"], "abandoned")
        self.assertEqual(job["warnings"], ["archived: approved"])
        self.assertEqual(job["history"][-1]["archived_from"], "needs-human")
        self.assertIn("nothing", self.factory("resume", job_id)["next"])
        self.assertIn("already abandoned", self.factory("archive", job_id, "again", expect_error=True))

    def test_record_model_rejects_unknown_stages(self):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.assertIn("unknown stage", self.factory("record-model", job_id, "reviewer", "x", expect_error=True))
        self.assertEqual(self.factory("record-model", job_id, "code", "sonnet")["models"], {"code": "sonnet"})
        self.assertEqual(self.factory("record-model", job_id, "stride", "opus")["models"], {"code": "sonnet", "stride": "opus"})

    def test_resume_explains_the_stride_review_step(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)
        action = self.factory("resume", job_id)["next"]
        self.assertIn("stride", action)
        self.assertIn("stride-review-done", action)

    def test_models_configure_the_stride_stage_as_expensive_tier(self):
        config = self.factory("models", "big-model", "small-model", "--cli", "kilo")
        self.assertEqual(config["stages"]["stride"], "big-model")

    def test_claude_install_writes_a_stride_reviewer_subagent(self):
        claude_home = Path(self.temp_directory.name) / "claude-home"
        self.factory("models", "opus-sonnet", "--cli", "claude")
        self.factory("install-claude", "--claude-home", str(claude_home))
        stride_agent = (claude_home / "agents" / "eg-review-stride.md").read_text(encoding="utf-8")
        self.assertIn("model: opus", stride_agent)
        self.assertNotIn("Edit", stride_agent)

    def job_at_quality_gate(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.assertEqual(self.factory("close-round", job_id)["next"], "stride-review")
        self.assertEqual(self.pass_stride_review(job_id, 1)["next"], "quality-gate")
        return job_id

    def gate_fix_build(self, job_id, source):
        """Stand in for the builder repairing what the gate reported."""
        (self.repo / "app.py").write_text(source, encoding="utf-8")
        self.job_file(job_id, "build.md", "fixed the gate findings\n")
        return self.factory("build-done", job_id)

    def test_clean_change_passes_the_gate_straight_to_the_approver(self):
        job_id = self.job_at_quality_gate()
        result = self.factory("quality-gate-done", job_id)
        self.assertEqual(result["next"], "approver")
        self.assertEqual(result["job"]["stage"], "approver")
        report = self.repo / ".factory" / "jobs" / job_id / "round-1" / "quality-gate.json"
        self.assertTrue(report.is_file())
        self.assertTrue((report.parent / "quality-gate.md").is_file())

    def test_gate_is_not_run_during_the_build_test_review_loop(self):
        job_id = self.job_in_review()
        job_dir = self.repo / ".factory" / "jobs" / job_id
        self.assertFalse(list(job_dir.glob("round-*/quality-gate.json")))
        error = self.factory("quality-gate-done", job_id, expect_error=True)
        self.assertIn("expected one of ['quality-gate']", error)

    def test_a_finding_sends_the_job_to_one_gate_fix_round_that_skips_tests_and_reviews(self):
        job_id = self.job_in_review()
        (self.repo / "app.py").write_text("try:\n    int('x')\nexcept ValueError:\n    pass\n", encoding="utf-8")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)
        self.pass_stride_review(job_id, 1)

        result = self.factory("quality-gate-done", job_id)
        self.assertEqual(result["next"], "rebuild")
        self.assertEqual((result["job"]["stage"], result["job"]["round"]), ("build", 2))
        self.assertEqual(result["job"]["attempt"]["gate_fixes"], 1)
        self.assertEqual(result["job"]["gate_fix_rounds"], 1)

        # The fixed build goes straight back to the gate: no new test audit or reviews.
        job = self.gate_fix_build(job_id, "VALUE = 3\n")
        self.assertEqual(job["stage"], "quality-gate")
        result = self.factory("quality-gate-done", job_id)
        self.assertEqual(result["next"], "approver")
        self.assertNotEqual(result["report"]["status"], "fail")

    def test_findings_left_after_the_fix_round_continue_to_the_approver_as_warnings(self):
        job_id = self.job_in_review()
        broken = "try:\n    int('x')\nexcept ValueError:\n    pass\n"
        (self.repo / "app.py").write_text(broken, encoding="utf-8")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)
        self.pass_stride_review(job_id, 1)
        self.assertEqual(self.factory("quality-gate-done", job_id)["next"], "rebuild")

        self.gate_fix_build(job_id, broken + "# still broken\n")
        result = self.factory("quality-gate-done", job_id)
        self.assertEqual(result["next"], "approver")
        self.assertEqual(result["job"]["stage"], "approver")
        self.assertTrue(any("still reports findings" in warning for warning in result["job"]["warnings"]))
        self.assertEqual(result["job"]["attempt"]["gate_fixes"], 1)

    def test_tamper_is_not_sent_to_the_builder_and_needs_the_humans_acceptance(self):
        job_id = self.job_in_review()
        (self.repo / "app.py").write_text("import os  # noqa\nVALUE = 2\n", encoding="utf-8")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)
        self.pass_stride_review(job_id, 1)

        result = self.factory("quality-gate-done", job_id)
        self.assertEqual(result["next"], "approver")
        self.assertEqual(result["job"]["attempt"]["gate_fixes"], 0)
        unresolved = result["report"]["summary"]["unresolvedTamper"]
        self.assertEqual(len(unresolved), 1)
        self.assertTrue(any("tamper" in warning for warning in result["job"]["warnings"]))

        error = self.factory("accept-suppression", job_id, "not-a-real-entry", "because", expect_error=True)
        self.assertIn("unknown tamper entry", error)
        error = self.factory("accept-suppression", job_id, unresolved[0], "  ", expect_error=True)
        self.assertIn("reason", error)
        job = self.factory("accept-suppression", job_id, unresolved[0], "false positive on a re-export")
        self.assertEqual(job["accepted_tamper"][unresolved[0]]["reason"], "false positive on a re-export")

    def test_accepted_tamper_counts_as_resolved_on_the_next_gate_run(self):
        job_id = self.job_in_review()
        # One fixable finding (forces a second gate run) plus one tamper entry.
        source = "import os  # noqa\ntry:\n    int('x')\nexcept ValueError:\n    pass\n"
        (self.repo / "app.py").write_text(source, encoding="utf-8")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)
        self.pass_stride_review(job_id, 1)

        first = self.factory("quality-gate-done", job_id)
        self.assertEqual(first["next"], "rebuild")
        entry = first["report"]["summary"]["unresolvedTamper"][0]
        self.factory("accept-suppression", job_id, entry, "reviewed by the human")

        self.gate_fix_build(job_id, "import os  # noqa\nVALUE = 3\n")
        second = self.factory("quality-gate-done", job_id)
        self.assertEqual(second["report"]["summary"]["unresolvedTamper"], [])
        self.assertTrue(all(item["accepted"] for item in second["report"]["tamper"]))
        self.assertIn(second["report"]["status"], ("pass", "warn"))
        self.assertFalse(any("tamper" in warning for warning in second["job"]["warnings"]))

    def test_a_missing_optional_tool_is_carried_as_a_warning_not_a_failure(self):
        job_id = self.job_at_quality_gate()
        result = self.factory("quality-gate-done", job_id)
        self.assertEqual(result["next"], "approver")
        skipped = result["report"]["summary"]["skippedTools"]
        for tool in skipped:
            self.assertTrue(any(tool in warning for warning in result["job"]["warnings"]), tool)

    def test_resume_names_the_quality_gate_step(self):
        job_id = self.job_at_quality_gate()
        self.assertIn("quality-gate-done", self.factory("resume", job_id)["next"])

    def test_a_job_at_the_gate_still_blocks_another_job_from_starting(self):
        first = self.job_at_quality_gate()
        second = self.factory("new", "Another feature")["id"]
        self.job_file(second, "feature.md", "feature\n")
        self.job_file(second, "prompt.md", "prompt\n")
        self.job_file(second, "spec.md", "spec\n")
        self.factory("spec-written", second)
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "wip")
        error = self.factory("approve-spec", second, expect_error=True)
        self.assertIn(first, error)

    def job_blocked_during_a_gate_fix(self):
        job_id = self.job_in_review()
        (self.repo / "app.py").write_text("try:\n    int('x')\nexcept ValueError:\n    pass\n", encoding="utf-8")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)
        self.pass_stride_review(job_id, 1)
        self.assertEqual(self.factory("quality-gate-done", job_id)["next"], "rebuild")
        # The gate-fix builder cannot proceed, so the job goes to the human.
        self.job_file(job_id, "build.md", "BLOCKED: cannot fix without a new dependency\n")
        return job_id

    def test_a_blocked_gate_fix_build_clears_the_gate_fix_shortcut(self):
        job_id = self.job_blocked_during_a_gate_fix()
        blocked = self.factory("build-done", job_id)
        self.assertEqual(blocked["stage"], "needs-human")
        self.assertIsNone(blocked["quality_gate"])

    def test_rework_after_a_blocked_gate_fix_goes_back_through_tests_and_reviews(self):
        job_id = self.job_blocked_during_a_gate_fix()
        self.factory("build-done", job_id)
        rework = self.factory("rework", job_id, "Use the standard library instead")
        self.assertEqual(rework["attempt"]["gate_fixes"], 0)
        self.gate_fix_build(job_id, "VALUE = 5\n")
        self.assertEqual(self.factory("show", job_id)["stage"], "test-audit")

    def test_rework_clears_a_stale_gate_fix_flag_whatever_route_left_it_set(self):
        # Construct the stale state directly: a job in needs-human whose quality_gate is still "fixing".
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)
        self.job_file(job_id, "decision.md", "ESCALATE\n\nready\n")
        self.factory("decision", job_id)
        board_path = self.repo / ".factory" / "board.json"
        board = json.loads(board_path.read_text(encoding="utf-8"))
        board["jobs"][0]["quality_gate"] = "fixing"
        board_path.write_text(json.dumps(board), encoding="utf-8")

        rework = self.factory("rework", job_id, "Try another approach")
        self.assertIsNone(rework["quality_gate"])
        self.gate_fix_build(job_id, "VALUE = 6\n")
        self.assertEqual(self.factory("show", job_id)["stage"], "test-audit")


if __name__ == "__main__":
    unittest.main()
