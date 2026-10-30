"""Structured findings and the BLOCKED verdict (decisions/factory-intelligence.md, D41, D46, D47).

These drive the real board script against a disposable Git repository, so they exercise the
parsing, the cross-round ledger and the stage transitions together rather than any one function.
"""

import unittest

from test_factory_board import FactoryBoardHarness


def finding(identifier, status="open", severity="HIGH", location="app.py:3"):
    return f"FINDING: {identifier} | SEVERITY: {severity} | LOCATION: {location} | STATUS: {status}\n"


class FindingLedgerTests(FactoryBoardHarness, unittest.TestCase):

    def audit(self, job_id, round_number, verdict, findings=""):
        self.job_file(job_id, f"round-{round_number}/test-audit.md", f"VERDICT: {verdict}\n\n{findings}Notes.\n")
        return self.factory("test-audit-done", job_id)

    def rebuild(self, job_id):
        self.simulate_build(job_id, report="built again\n")
        (self.repo / "app.py").write_text(f"VALUE = {len(list(self.repo.glob('*')))}\n", encoding="utf-8")
        self.factory("build-done", job_id)

    def job_in_test_audit(self):
        job_id = self.approved_job()
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        return job_id

    def test_a_job_with_no_finding_lines_behaves_as_before(self):
        job_id = self.job_in_review()
        job = self.factory("show", job_id)
        self.assertEqual(job["findings"], {})
        self.assertEqual(job["unresolved"], [])

    def test_open_findings_are_recorded_with_severity_and_location(self):
        job_id = self.job_in_test_audit()
        result = self.audit(job_id, 1, "CHANGES", finding("tests-1", location="test_app.py:12", severity="MEDIUM"))
        recorded = result["job"]["findings"]["tests-1"]
        self.assertEqual(
            (recorded["role"], recorded["severity"], recorded["location"], recorded["status"], recorded["first_round"]),
            ("tests", "MEDIUM", "test_app.py:12", "open", 1),
        )
        self.assertEqual(result["job"]["unresolved"], ["tests-1"])

    def test_a_finding_closed_in_a_later_round_leaves_the_unresolved_list(self):
        job_id = self.job_in_test_audit()
        self.audit(job_id, 1, "CHANGES", finding("tests-1"))
        self.rebuild(job_id)
        result = self.audit(job_id, 2, "PASS", finding("tests-1", status="closed"))
        self.assertEqual(result["job"]["findings"]["tests-1"]["status"], "closed")
        self.assertEqual(result["job"]["unresolved"], [])
        self.assertEqual(result["job"]["warnings"], [])

    def test_a_disputed_finding_stays_unresolved_until_its_reviewer_closes_it(self):
        job_id = self.job_in_test_audit()
        self.audit(job_id, 1, "CHANGES", finding("tests-1"))
        self.rebuild(job_id)
        # The builder rebutted the finding in build.md; the auditor records it as disputed
        # rather than closing it, so the human still sees it as open.
        result = self.audit(job_id, 2, "PASS", finding("tests-1", status="disputed"))
        self.assertEqual(result["job"]["findings"]["tests-1"]["status"], "disputed")
        self.assertEqual(result["job"]["unresolved"], ["tests-1"])

    def test_a_closed_finding_raised_again_is_reported_as_reopened(self):
        job_id = self.job_in_test_audit()
        self.audit(job_id, 1, "CHANGES", finding("tests-1"))
        self.rebuild(job_id)
        self.audit(job_id, 2, "PASS", finding("tests-1", status="closed"))
        # Round 2 passed, so the job is in review; a human rework reopens the build and the
        # auditor raises the same id again.
        self.write_reviews(job_id, 2, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 2)
        self.job_file(job_id, "decision.md", "ESCALATE\n")
        self.factory("decision", job_id)
        rework_round = self.factory("rework", job_id, "still broken")["round"]
        self.rebuild(job_id)
        result = self.audit(job_id, rework_round, "CHANGES", finding("tests-1"))
        self.assertTrue(result["job"]["findings"]["tests-1"]["reopened"])
        self.assertTrue(any("tests-1" in w and "re-raised" in w for w in result["job"]["warnings"]))
        self.assertEqual(result["job"]["unresolved"], ["tests-1"])

    def test_a_finding_dropped_without_being_closed_stays_open_and_is_flagged(self):
        job_id = self.job_in_test_audit()
        self.audit(job_id, 1, "CHANGES", finding("tests-1") + finding("tests-2", severity="LOW"))
        self.rebuild(job_id)
        # Round 2 restates only tests-1; tests-2 silently disappears.
        result = self.audit(job_id, 2, "CHANGES", finding("tests-1"))
        self.assertTrue(any("tests-2" in w and "neither restates nor closes" in w for w in result["job"]["warnings"]))
        self.assertIn("tests-2", result["job"]["unresolved"])

    def test_a_role_that_did_not_run_is_not_blamed_for_dropping_a_finding(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ui": "N/A", "code": "PASS"})
        self.job_file(
            job_id, "round-1/review-ux.md",
            "VERDICT: CHANGES\n\n" + finding("ux-1", location="cli.py:1") + "Error message gives no next step.\n",
        )
        self.assertEqual(self.factory("close-round", job_id)["next"], "rebuild")
        self.rebuild(job_id)
        self.pass_test_audit(job_id, 2)
        # Only ux, ui and architecture may be N/A (code and security always run). The rebuild
        # made the change non-visual, so ux is N/A in round 2 and restates nothing: that is
        # not a silently dropped finding.
        self.write_reviews(job_id, 2, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        result = self.factory("close-round", job_id)
        self.assertFalse(any("ux-1" in warning for warning in result["job"]["warnings"]))

    def test_unresolved_findings_are_named_for_the_human_at_the_decision(self):
        job_id = self.job_in_test_audit()
        self.audit(job_id, 1, "CHANGES", finding("tests-1"))
        self.rebuild(job_id)
        self.audit(job_id, 2, "CHANGES", finding("tests-1"))
        self.write_reviews(job_id, 2, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 2)
        self.job_file(job_id, "decision.md", "ESCALATE\n\nNeeds rework.\n")
        job = self.factory("decision", job_id)
        self.assertEqual(job["stage"], "needs-human")
        self.assertIn("unresolved findings: tests-1", job["warnings"])


class FindingValidationTests(FactoryBoardHarness, unittest.TestCase):

    def test_a_malformed_finding_line_is_rejected_not_silently_dropped(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A"})
        self.job_file(
            job_id, "round-1/review-code.md",
            "VERDICT: CHANGES\n\nFINDING: code-1 | SEVERITY: URGENT | LOCATION: app.py | STATUS: open\n",
        )
        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["code"], "invalid")
        self.assertIn("FINDING line is malformed", list(status["invalid"].values())[0])

    def test_a_reviewer_cannot_raise_or_close_another_roles_finding(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A"})
        self.job_file(
            job_id, "round-1/review-code.md",
            "VERDICT: PASS\n\n" + finding("security-1", status="closed") + "Looks fixed to me.\n",
        )
        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["code"], "invalid")
        self.assertIn("belongs to 'security'", list(status["invalid"].values())[0])

    def test_findings_are_read_from_every_role_not_only_the_test_auditor(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"ux": "N/A", "ui": "N/A", "code": "PASS"})
        # No standalone SEVERITY line: the FINDING line alone must satisfy the severity floor.
        self.job_file(
            job_id, "round-1/review-security.md",
            "VERDICT: CHANGES\n\n" + finding("security-1", severity="CRITICAL", location="auth.py:9")
            + "Token logged.\n",
        )
        status = self.factory("round-status", job_id)
        # The verdict must be accepted, not merely parsed into the ledger: a file the severity
        # floor rejects is still read into the ledger, so the ledger alone proves nothing.
        self.assertEqual(status["reviews"]["security"], "CHANGES")
        self.assertEqual(status["invalid"], {})
        job = self.factory("show", job_id)
        self.assertEqual(job["findings"]["security-1"]["role"], "security")
        self.assertEqual(job["findings"]["security-1"]["severity"], "CRITICAL")

    def test_the_severity_floor_counts_open_findings_only(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"ux": "N/A", "ui": "N/A", "code": "PASS"})
        # A MEDIUM open finding plus a CRITICAL one that is already closed: nothing blocking is open.
        self.job_file(
            job_id, "round-1/review-security.md",
            "VERDICT: CHANGES\n\n" + finding("security-1", severity="MEDIUM")
            + finding("security-2", severity="CRITICAL", status="closed") + "Notes.\n",
        )
        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["security"], "invalid")
        self.assertIn("SEVERITY: CRITICAL", list(status["invalid"].values())[0])

    def test_a_standalone_severity_line_still_satisfies_the_floor(self):
        # Backward compatibility: reviews written before the FINDING format keep working.
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.job_file(job_id, "round-1/review-security.md", "VERDICT: CHANGES\n\nSEVERITY: HIGH\nOld style finding.\n")
        self.assertEqual(self.factory("round-status", job_id)["reviews"]["security"], "CHANGES")


class SpecImpactFieldTests(FactoryBoardHarness, unittest.TestCase):
    """The board reads the spec's impact fields by pattern; the new optional spec sections
    (decisions/factory-intelligence.md, D43) must not be able to change what it decides."""

    ALL_REVIEWERS = ["security", "ux", "ui", "code", "architecture"]

    def spawned(self, spec):
        job_id = self.approved_job(spec)
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        return self.pass_test_audit(job_id, 1)["spawn"]

    def test_a_later_line_beginning_with_the_label_cannot_skip_a_review_the_field_asked_for(self):
        # "UI impact: no screens" under User-facing surface once overruled "UI impact: yes".
        spec = "**UI impact:** yes\n\n## User-facing surface\nUI impact: no screens, only the response text.\n"
        self.assertIn("ui", self.spawned(spec))

    def test_the_same_holds_for_the_architecture_label(self):
        spec = (
            "**Architecture impact:** yes\n\n## Edge cases\n"
            "Architecture impact: none beyond this one handler (criterion 1).\n"
        )
        self.assertIn("architecture", self.spawned(spec))

    def test_the_heading_form_used_by_real_specs_still_skips_when_it_says_no(self):
        # Real specs write "## UI impact", a blank line, then "no". The pattern accepts this by
        # letting its non-word run span the newlines; reading only the label line would regress it.
        spec = "## UI impact\n\nno\n\n## Architecture impact\n\nno\n\n## Out of scope\n\nNothing.\n"
        self.assertEqual(self.spawned(spec), ["security", "ux", "code"])

    def test_a_spec_with_every_optional_section_still_skips_what_its_fields_say(self):
        spec = (
            "**Status:** Proposed\n\n## Acceptance criteria\n1. Generic 500 message.\n\n"
            "## Edge cases\n- Custom exception with a message attribute (criterion 1).\n\n"
            "## Assumptions\n- No client parses the old text.\n\n"
            "## Compatibility\n- Response shape must not change.\n\n"
            "## Verification plan\n`pytest -q`\n\n"
            "## User-facing surface\nThe 500 response message.\n\n"
            "**UI impact:** no\n\n**Architecture impact:** no\n\n## Out of scope\nLogging.\n"
        )
        self.assertEqual(self.spawned(spec), ["security", "ux", "code"])


class BlockedVerdictTests(FactoryBoardHarness, unittest.TestCase):

    def test_a_bare_blocked_verdict_is_rejected(self):
        job_id = self.approved_job()
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.job_file(job_id, "round-1/test-audit.md", "VERDICT: BLOCKED\n")
        error = self.factory("test-audit-done", job_id, expect_error=True)
        self.assertIn("needs a reason", error)

    def test_a_blocked_test_audit_sends_the_job_to_the_human_without_a_rebuild(self):
        job_id = self.approved_job()
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.job_file(job_id, "round-1/test-audit.md", "VERDICT: BLOCKED\n\nNo database is reachable to run the suite.\n")
        result = self.factory("test-audit-done", job_id)
        self.assertEqual(result["next"], "needs-human")
        self.assertEqual((result["job"]["stage"], result["job"]["round"]), ("needs-human", 1))
        self.assertEqual(result["job"]["attempt"]["test_rebuilds"], 0)
        self.assertIn(
            "tests review blocked in round 1: No database is reachable to run the suite.", result["job"]["warnings"]
        )

    def test_a_blocked_reviewer_stops_the_round_even_when_the_others_pass(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A"})
        self.job_file(job_id, "round-1/review-code.md", "VERDICT: BLOCKED\n\nChange patch is empty.\n")
        result = self.factory("close-round", job_id)
        self.assertEqual((result["next"], result["job"]["stage"]), ("needs-human", "needs-human"))
        # Blocking must not spend a review round or be mistaken for CHANGES.
        self.assertEqual(result["job"]["attempt"]["review_rounds"], 0)
        self.assertTrue(any("code review blocked" in warning for warning in result["job"]["warnings"]))

    def test_a_blocked_stride_review_stops_the_job(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.factory("close-round", job_id)
        self.job_file(job_id, "round-1/review-stride.md", "VERDICT: BLOCKED\n\nNo trust-zone profile could be built.\n")
        result = self.factory("stride-review-done", job_id)
        self.assertEqual(result["job"]["stage"], "needs-human")

    def test_resume_does_not_point_the_human_at_a_decision_that_was_never_written(self):
        job_id = self.approved_job()
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.job_file(job_id, "round-1/test-audit.md", "VERDICT: BLOCKED\n\nNo database reachable.\n")
        self.factory("test-audit-done", job_id)
        hint = self.factory("resume", job_id)["next"]
        self.assertIn("no decision.md", hint)
        self.assertIn("rework", hint)

    def test_resume_still_points_at_decision_md_when_the_approver_ran(self):
        # Negative control for the test above: the changed hint must apply only to jobs that
        # never reached the approver, not to every needs-human job.
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)
        self.job_file(job_id, "decision.md", "ESCALATE\n\nReady.\n")
        self.factory("decision", job_id)
        self.assertIn("reads decision.md and runs approve or rework", self.factory("resume", job_id)["next"])

    def test_rework_reopens_a_blocked_job(self):
        job_id = self.approved_job()
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.job_file(job_id, "round-1/test-audit.md", "VERDICT: BLOCKED\n\nNo database reachable.\n")
        self.factory("test-audit-done", job_id)
        job = self.factory("rework", job_id, "database is up now")
        self.assertEqual((job["stage"], job["round"]), ("build", 2))
        self.assertEqual(job["attempt"], {"review_rounds": 0, "test_rebuilds": 0, "gate_fixes": 0})


if __name__ == "__main__":
    unittest.main()
