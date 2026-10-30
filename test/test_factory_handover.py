"""Handover diagrams, the architecture reviewer and its skip rule (decisions/factory-visual-handover.md).

These drive the real board script and, where a test needs a verdict on a diagram, the real
mermaid parser. Tests that need the validator's npm packages skip with a reason when they are
not installed, because the packages are optional (D37); the degradation tests always run.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_factory_board import BOARD_SCRIPT, FactoryBoardHarness

VALIDATOR_DIRECTORY = BOARD_SCRIPT.parents[1] / "validator"
VALIDATOR_SCRIPT = VALIDATOR_DIRECTORY / "check_mermaid.mjs"
PACKAGES_INSTALLED = (VALIDATOR_DIRECTORY / "node_modules" / "mermaid").is_dir() and shutil.which("node")

VALID_DIAGRAM = "```mermaid\nflowchart LR\n  A[spec] --> B[build]\n```\n"
BROKEN_DIAGRAM = "```mermaid\nflowchart LR\n  A[spec -->\n```\n"
needs_packages = unittest.skipUnless(
    PACKAGES_INSTALLED, f"run npm install in {VALIDATOR_DIRECTORY} to enable real diagram parsing"
)


class HandoverTests(FactoryBoardHarness, unittest.TestCase):
    """Handover diagrams, the architecture reviewer and the staleness signal."""

    def factory_without_node(self, *arguments):
        """Run the board with no `node` on PATH, as on a machine that never installed it."""
        empty_bin = tempfile.mkdtemp(prefix="no-node-")
        self.addCleanup(shutil.rmtree, empty_bin, True)
        # The board is launched by absolute interpreter path, so an empty PATH hides only node and git
        # lookups made by name; git is symlinked in because the board shells out to it.
        os.symlink(shutil.which("git"), os.path.join(empty_bin, "git"))
        result = subprocess.run(
            [sys.executable, str(BOARD_SCRIPT), *arguments],
            cwd=self.repo, capture_output=True, text=True,
            env={**os.environ, "FACTORY_DISABLE_CENTRAL_SYNC": "1", "PATH": empty_bin},
        )
        return result.returncode, json.loads(result.stdout)

    def written_job(self, handover=None):
        job_id = self.factory("new", "Add rate limiting")["id"]
        self.job_file(job_id, "feature.md", "feature\n")
        self.job_file(job_id, "prompt.md", "prompt\n")
        self.job_file(job_id, "spec.md", "spec\n")
        if handover is not None:
            self.job_file(job_id, "handover.md", handover)
        return job_id

    @needs_packages
    def test_a_broken_diagram_is_rejected_at_spec_written_and_the_stage_does_not_move(self):
        job_id = self.written_job(f"# Handover\n\n{BROKEN_DIAGRAM}")
        error = self.factory("spec-written", job_id, expect_error=True)
        self.assertIn("invalid mermaid", error)
        self.assertEqual(self.factory("show", job_id)["stage"], "spec")

        self.job_file(job_id, "handover.md", f"# Handover\n\n{VALID_DIAGRAM}")
        self.assertEqual(self.factory("spec-written", job_id)["stage"], "spec-review")

    @needs_packages
    def test_a_broken_diagram_is_rejected_at_build_done_without_recording_the_round(self):
        job_id = self.written_job()
        self.factory("spec-written", job_id)
        self.factory("approve-spec", job_id)
        self.simulate_build(job_id)
        self.job_file(job_id, "handover.md", BROKEN_DIAGRAM)

        self.assertIn("invalid mermaid", self.factory("build-done", job_id, expect_error=True))
        job = self.factory("show", job_id)
        self.assertEqual(job["stage"], "build")
        self.assertFalse((self.repo / ".factory" / "jobs" / job_id / "round-1" / "change.patch").exists())

    @needs_packages
    def test_a_broken_diagram_is_rejected_at_decision(self):
        job_id = self.job_in_review()
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.close_round_to_approver(job_id, 1)
        self.job_file(job_id, "decision.md", "ESCALATE\n\nReady.\n")
        self.job_file(job_id, "handover.md", BROKEN_DIAGRAM)

        self.assertIn("invalid mermaid", self.factory("decision", job_id, expect_error=True))
        self.assertEqual(self.factory("show", job_id)["stage"], "approver")

    @needs_packages
    def test_the_error_names_which_diagram_is_broken(self):
        job_id = self.written_job(f"{VALID_DIAGRAM}\n{BROKEN_DIAGRAM}")
        error = self.factory("spec-written", job_id, expect_error=True)
        self.assertIn("1 invalid", error)
        self.assertIn("diagram 2", error)

    # Forms the dashboard draws as diagrams: the board must validate every one of them.
    BROKEN_BODY = "flowchart LR\n  A[spec -->\n"
    DRAWN_FENCES = {
        "tilde fence": "~~~mermaid\n{body}~~~\n",
        "capitalised info string": "```Mermaid\n{body}```\n",
        "longer fence": "````mermaid\n{body}````\n",
        "inside a blockquote": "> ```mermaid\n> flowchart LR\n>   A[spec -->\n> ```\n",
        "inside a list item": "- item\n\n  ```mermaid\n  flowchart LR\n    A[spec -->\n  ```\n",
    }

    @needs_packages
    def test_a_broken_diagram_is_rejected_in_every_fence_form_the_dashboard_draws(self):
        for name, template in self.DRAWN_FENCES.items():
            with self.subTest(fence=name):
                job_id = self.written_job("# Handover\n\n" + template.format(body=self.BROKEN_BODY))
                error = self.factory("spec-written", job_id, expect_error=True)
                self.assertIn("invalid mermaid", error)
                self.factory("abandon", job_id, "next fence form")

    @needs_packages
    def test_an_indented_code_block_is_not_treated_as_a_diagram(self):
        # Four spaces make this a code block in the dashboard, so there is nothing drawn to validate.
        indented = "    ```mermaid\n    flowchart LR\n      A[spec -->\n    ```\n"
        job_id = self.written_job(f"# Handover\n\n{indented}")
        self.assertEqual(self.factory("spec-written", job_id)["stage"], "spec-review")

    def test_a_handover_without_diagrams_needs_no_validator(self):
        job_id = self.written_job("# Handover\n\nSmall fix, nothing to draw.\n")
        job = self.factory("spec-written", job_id)
        self.assertEqual(job["stage"], "spec-review")
        self.assertEqual(job["warnings"], [])

    def test_a_job_with_no_handover_still_progresses(self):
        # Jobs created before the handover existed must keep working.
        job_id = self.written_job()
        self.assertEqual(self.factory("spec-written", job_id)["stage"], "spec-review")

    def test_a_machine_without_node_warns_and_continues(self):
        job_id = self.written_job(f"# Handover\n\n{BROKEN_DIAGRAM}")
        code, job = self.factory_without_node("spec-written", job_id)
        self.assertEqual(code, 0, job)
        self.assertEqual(job["stage"], "spec-review")
        self.assertTrue(any("not validated" in warning and "node is not installed" in warning
                            for warning in job["warnings"]), job["warnings"])

    @unittest.skipUnless(shutil.which("node"), "node is required to exercise the missing-packages path")
    def test_a_validator_without_its_packages_reports_unavailable_not_invalid(self):
        isolated = Path(tempfile.mkdtemp(prefix="validator-no-packages-"))
        self.addCleanup(shutil.rmtree, isolated, True)
        shutil.copy(VALIDATOR_SCRIPT, isolated / "check_mermaid.mjs")
        shutil.copy(VALIDATOR_DIRECTORY / "package.json", isolated / "package.json")
        diagram_file = isolated / "handover.md"
        diagram_file.write_text(BROKEN_DIAGRAM, encoding="utf-8")

        result = subprocess.run(["node", str(isolated / "check_mermaid.mjs"), str(diagram_file)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("not installed", json.loads(result.stdout)["unavailable"])

    def job_in_review_with(self, spec, handover=None):
        job_id = self.approved_job(spec)
        if handover is not None:
            self.job_file(job_id, "handover.md", handover)
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        return job_id, self.pass_test_audit(job_id, 1)

    def test_architecture_is_reviewed_by_default(self):
        _, result = self.job_in_review_with("spec\n")
        self.assertIn("architecture", result["spawn"])
        self.assertEqual(result["job"]["reviews"]["architecture"], "pending")

    def test_architecture_is_not_applicable_when_the_spec_says_no_and_there_is_no_diagram(self):
        job_id, result = self.job_in_review_with("**Architecture impact:** no\n", handover="# Handover\n\nSmall fix.\n")
        self.assertNotIn("architecture", result["spawn"])
        self.assertEqual(result["job"]["reviews"]["architecture"], "N/A")
        review = (self.repo / ".factory" / "jobs" / job_id / "round-1" / "review-architecture.md").read_text(encoding="utf-8")
        self.assertTrue(review.startswith("VERDICT: N/A"))

    def test_architecture_is_not_applicable_when_the_spec_says_no_and_there_is_no_handover(self):
        _, result = self.job_in_review_with("**Architecture impact:** no\n")
        self.assertNotIn("architecture", result["spawn"])

    @needs_packages
    def test_a_diagram_keeps_the_architecture_review_on_even_if_the_spec_says_no(self):
        _, result = self.job_in_review_with("**Architecture impact:** no\n", handover=f"# Handover\n\n{VALID_DIAGRAM}")
        self.assertIn("architecture", result["spawn"])

    def test_any_diagram_form_keeps_the_architecture_review_on_even_if_the_spec_says_no(self):
        # The skip evidence must not disagree with what the dashboard draws: a tilde fence or a
        # capitalised info string is a diagram, so skipping the review on them would hide a change.
        for name, fence in (("tilde", "~~~mermaid\nflowchart LR\n  A-->B\n~~~\n"),
                            ("capitalised", "```Mermaid\nflowchart LR\n  A-->B\n```\n"),
                            ("longer", "````mermaid\nflowchart LR\n  A-->B\n````\n")):
            with self.subTest(fence=name):
                job_id, result = self.job_in_review_with("**Architecture impact:** no\n", handover=f"# Handover\n\n{fence}")
                self.assertIn("architecture", result["spawn"])
                self.git("checkout", "--", "app.py")
                self.git("clean", "-fdq", "--", ".")
                self.factory("abandon", job_id, "next fence form")

    def test_architecture_impact_yes_or_mentioned_in_prose_does_not_skip(self):
        for spec in ("**Architecture impact:** yes\n",
                     "**Architecture impact:** yes\n\nAn earlier draft said Architecture impact: no.\n"):
            with self.subTest(spec=spec):
                _, result = self.job_in_review_with(spec)
                self.assertIn("architecture", result["spawn"])
                self.git("checkout", "--", "app.py")
                self.git("clean", "-fdq", "--", ".")
                self.factory("abandon", self.factory("show")["jobs"][-1]["id"], "next subtest")

    def test_ui_and_architecture_skips_are_independent(self):
        # UI stays on (a visual file changed) while architecture is skipped, and vice versa.
        job_id = self.approved_job("**UI impact:** no\n**Architecture impact:** no\n")
        (self.repo / "page.html").write_text("<p>hi</p>\n", encoding="utf-8")
        self.job_file(job_id, "build.md", "built\n")
        self.factory("build-done", job_id)
        result = self.pass_test_audit(job_id, 1)
        self.assertEqual(result["spawn"], ["security", "ux", "ui", "code"])

    def test_the_round_waits_for_the_architecture_review_and_accepts_not_applicable(self):
        job_id, _ = self.job_in_review_with("spec\n")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.job_file(job_id, "round-1/review-architecture.md", "")
        os.remove(self.repo / ".factory" / "jobs" / job_id / "round-1" / "review-architecture.md")
        self.assertIn("architecture", self.factory("close-round", job_id, expect_error=True))

        self.job_file(job_id, "round-1/review-architecture.md", "VERDICT: N/A\nNo architecture to compare.\n")
        self.assertEqual(self.factory("close-round", job_id)["next"], "stride-review")

    def test_a_round_that_started_before_the_architecture_reviewer_existed_is_not_stranded(self):
        job_id, _ = self.job_in_review_with("spec\n")
        board_path = self.repo / ".factory" / "board.json"
        board = json.loads(board_path.read_text(encoding="utf-8"))
        # The shape recorded by a board that predated the fifth reviewer.
        board["jobs"][0]["reviews"].pop("architecture")
        board_path.write_text(json.dumps(board), encoding="utf-8")
        for reviewer, verdict in (("security", "PASS"), ("ux", "N/A"), ("ui", "N/A"), ("code", "PASS")):
            self.job_file(job_id, f"round-1/review-{reviewer}.md", f"VERDICT: {verdict}\n")
        # No architecture file exists: the board of that era never asked for one.
        self.assertFalse((self.repo / ".factory" / "jobs" / job_id / "round-1" / "review-architecture.md").exists())

        # round-status is documented as repeatable and saves what it reads, so a second call is
        # the case that matters: the first call must not leave the job reading as pending.
        for attempt in (1, 2):
            status = self.factory("round-status", job_id)
            self.assertEqual(status["reviews"]["architecture"], "N/A", f"call {attempt}")
            self.assertTrue(status["complete"], f"call {attempt}")
        self.assertEqual(self.factory("close-round", job_id)["next"], "stride-review")

    def test_a_current_round_still_waits_for_the_architecture_review(self):
        # The legacy allowance must not let a new job skip the reviewer by omission.
        job_id, _ = self.job_in_review_with("spec\n")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        os.remove(self.repo / ".factory" / "jobs" / job_id / "round-1" / "review-architecture.md")
        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["architecture"], "pending")
        self.assertFalse(status["complete"])

    def test_a_malformed_architecture_review_is_rejected(self):
        job_id, _ = self.job_in_review_with("spec\n")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.job_file(job_id, "round-1/review-architecture.md", "Looks fine\n")
        status = self.factory("round-status", job_id)
        self.assertEqual(status["reviews"]["architecture"], "invalid")
        self.assertFalse(status["complete"])

    def test_architecture_changes_needs_a_finding_and_sends_the_job_back(self):
        job_id, _ = self.job_in_review_with("spec\n")
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "PASS"})
        self.job_file(job_id, "round-1/review-architecture.md", "VERDICT: CHANGES\n")
        invalid = self.factory("round-status", job_id)["invalid"]
        self.assertEqual(len(invalid), 1, invalid)
        self.assertIn("at least one finding", next(iter(invalid.values())))

        self.job_file(job_id, "round-1/review-architecture.md",
                      "VERDICT: CHANGES\n\nhandover.md shows a cache the patch never adds.\n")
        self.assertEqual(self.factory("close-round", job_id)["next"], "rebuild")

    def test_the_architecture_reviewer_runs_on_the_expensive_tier_and_gets_a_claude_subagent(self):
        self.factory("init")
        config = self.factory("models", "opus-sonnet", "--cli", "claude")
        self.assertEqual(config["stages"]["architecture"], config["expensive"])
        claude_home = Path(self.temp_directory.name) / "claude"
        self.factory("install-claude", "--claude-home", str(claude_home))
        agent = (claude_home / "agents" / "eg-review-architecture.md").read_text(encoding="utf-8")
        self.assertIn(f"model: {config['expensive']}", agent)
        self.assertNotIn("Edit", agent.split("tools:")[1].splitlines()[0])

    def config_without_architecture(self, cli):
        """A config.json as written before the architecture stage existed."""
        self.factory("models", "opus-sonnet" if cli == "claude" else "sol-luna", "--cli", cli)
        config_path = self.repo / ".factory" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["stages"].pop("architecture")
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return config_path, config

    def test_install_claude_upgrades_a_config_written_before_the_architecture_stage(self):
        config_path, config = self.config_without_architecture("claude")
        claude_home = Path(self.temp_directory.name) / "claude"

        self.factory("install-claude", "--claude-home", str(claude_home))

        agent = (claude_home / "agents" / "eg-review-architecture.md").read_text(encoding="utf-8")
        self.assertIn(f"model: {config['expensive']}", agent)
        stages = json.loads(config_path.read_text(encoding="utf-8"))["stages"]
        self.assertEqual(stages["architecture"], config["expensive"])

    def test_starting_a_run_repairs_an_older_config_on_any_cli(self):
        config_path, config = self.config_without_architecture("codex")
        self.factory("new", "Add a thing")
        stages = json.loads(config_path.read_text(encoding="utf-8"))["stages"]
        self.assertEqual(stages["architecture"], config["expensive"])

    def test_a_config_that_already_has_every_stage_is_left_alone(self):
        self.factory("models", "opus-sonnet", "--cli", "claude")
        config_path = self.repo / ".factory" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["stages"]["architecture"] = "custom-model"  # a deliberate per-stage choice
        config_path.write_text(json.dumps(config), encoding="utf-8")
        self.factory("new", "Add a thing")
        self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["stages"]["architecture"], "custom-model")

    def rebuild_round_two(self, job_id, handover):
        """Send a job through a CHANGES review and build round 2, optionally rewriting the handover."""
        self.write_reviews(job_id, 1, {"security": "PASS", "ux": "N/A", "ui": "N/A", "code": "CHANGES"})
        self.assertEqual(self.factory("close-round", job_id)["next"], "rebuild")
        (self.repo / "app.py").write_text("VALUE = 3\n", encoding="utf-8")
        self.job_file(job_id, "build.md", "built again\n")
        if handover is not None:
            self.job_file(job_id, "handover.md", handover)
        return self.factory("build-done", job_id)

    def test_a_handover_left_untouched_while_code_changes_is_flagged_as_possibly_stale(self):
        job_id = self.approved_job()
        self.job_file(job_id, "handover.md", "# Handover\n\nVersion one.\n")
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.pass_test_audit(job_id, 1)

        job = self.rebuild_round_two(job_id, handover=None)
        stale = [warning for warning in job["warnings"] if "handover.md was not updated" in warning]
        self.assertEqual(len(stale), 1, job["warnings"])
        self.assertIn("may no longer match", stale[0])

    def test_an_updated_handover_is_not_flagged(self):
        job_id = self.approved_job()
        self.job_file(job_id, "handover.md", "# Handover\n\nVersion one.\n")
        self.simulate_build(job_id)
        self.factory("build-done", job_id)
        self.pass_test_audit(job_id, 1)

        job = self.rebuild_round_two(job_id, handover="# Handover\n\nVersion two.\n")
        self.assertFalse([w for w in job["warnings"] if "handover.md" in w], job["warnings"])

    def test_the_first_build_and_handover_free_jobs_are_never_flagged(self):
        job_id = self.approved_job()
        self.job_file(job_id, "handover.md", "# Handover\n")
        self.simulate_build(job_id)
        self.assertFalse(self.factory("build-done", job_id)["warnings"])

        other = Path(self.temp_directory.name)
        self.assertTrue(other.exists())


@needs_packages
class DiagramExtractionTests(unittest.TestCase):
    """The extractor decides which text is validated, so a miss would silently skip a diagram."""

    def extract(self, markdown):
        # The markdown goes in on stdin: as an argument, a leading "- " would be read as a node option.
        script = (
            f"import {{ extractMermaidBlocks }} from {json.dumps(VALIDATOR_SCRIPT.as_uri())};"
            f"import {{ createRequire }} from 'node:module';"
            f"const {{ Lexer }} = await import(createRequire({json.dumps(str(VALIDATOR_DIRECTORY / 'package.json'))})"
            ".resolve('marked').replace(/^/, 'file://'));"
            "let text = ''; for await (const chunk of process.stdin) text += chunk;"
            "process.stdout.write(JSON.stringify(extractMermaidBlocks(text, Lexer)));"
        )
        result = subprocess.run(["node", "--input-type=module", "-e", script], input=markdown,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_only_mermaid_fences_are_extracted_with_their_line_numbers(self):
        blocks = self.extract("intro\n```python\nprint(1)\n```\n\n```mermaid\nflowchart LR\n  A-->B\n```\n")
        self.assertEqual(blocks, [{"line": 6, "source": "flowchart LR\n  A-->B"}])

    def test_several_blocks_and_windows_line_endings_are_found(self):
        blocks = self.extract("```mermaid\r\ngraph TD\r\n  A-->B\r\n```\r\ntext\r\n```mermaid\r\nsequenceDiagram\r\n```\r\n")
        self.assertEqual([block["line"] for block in blocks], [1, 6])

    def test_text_that_only_mentions_mermaid_is_not_a_block(self):
        self.assertEqual(self.extract("Use a ```mermaid fence for diagrams.\n    ```mermaidx\n"), [])

    def test_every_fence_form_the_dashboard_draws_is_found_at_its_own_line(self):
        cases = {
            "~~~mermaid\ngraph TD\n A-->B\n~~~\n": 1,
            "```Mermaid\ngraph TD\n A-->B\n```\n": 1,
            "````mermaid\ngraph TD\n A-->B\n````\n": 1,
            "text\n\n> ```mermaid\n> graph TD\n>  A-->B\n> ```\n": 3,
            "- item\n\n  ```mermaid\n  graph TD\n   A-->B\n  ```\n": 3,
        }
        for markdown, line in cases.items():
            with self.subTest(markdown=markdown):
                blocks = self.extract(markdown)
                self.assertEqual([block["line"] for block in blocks], [line])
                self.assertIn("A-->B", blocks[0]["source"])

    def test_an_indented_code_block_is_not_a_diagram(self):
        self.assertEqual(self.extract("    ```mermaid\n    graph TD\n    ```\n"), [])


if __name__ == "__main__":
    unittest.main()
