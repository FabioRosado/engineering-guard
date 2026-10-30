import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "factory" / "scripts" / "quality_gate.py"

# Built at run time so this test file never itself contains a secret-shaped literal.
FAKE_AWS_KEY = "AKIA" + "A" * 16


class GateRepositoryCase(unittest.TestCase):
    """A disposable Git repository and a way to run the real gate script against it."""

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory(prefix="engineering-guard-gate-")
        self.repo = Path(self.temp_directory.name) / "repo"
        self.repo.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.email", "gate@example.com")
        self.git("config", "user.name", "Gate Test")
        self.write("app.py", "VALUE = 1\n")
        self.write("tests/test_app.py", "def test_value():\n    assert 1 == 1\n    assert 2 == 2\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "initial")

    def tearDown(self):
        self.temp_directory.cleanup()

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.repo, check=True, capture_output=True, text=True).stdout

    def write(self, relative_path, text):
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def gate(self, *arguments, path_without_tools=False):
        environment = {**os.environ}
        if path_without_tools:
            # Keep git and python reachable but hide gitleaks and bandit, to test the missing-tool path.
            environment["PATH"] = os.pathsep.join(
                [str(Path(sys.executable).parent), "/usr/bin", "/bin", str(Path(self.git_path()).parent)]
            )
        result = subprocess.run(
            [sys.executable, str(GATE_SCRIPT), *arguments],
            cwd=self.repo, capture_output=True, text=True, env=environment,
        )
        return result.returncode, json.loads(result.stdout)

    def git_path(self):
        return subprocess.run(["which", "git"], capture_output=True, text=True).stdout.strip()

    def rules(self, report, key="findings"):
        return {entry["rule"] for entry in report[key]}

    def check(self, report, name):
        return next(check for check in report["checks"] if check["name"] == name)


class QualityGateTests(GateRepositoryCase):
    def test_clean_change_passes_with_exit_zero(self):
        self.write("app.py", "VALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["tamper"], [])

    def test_comment_banner_fails_and_ordinary_comments_do_not(self):
        self.write("app.py", "# ---------------------------\nVALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertIn("comment-banner", self.rules(report))

        self.write("app.py", "# Why: the limit is per user, not per request.\nVALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)

    def test_secret_shaped_literal_fails_without_reproducing_the_value(self):
        self.write("app.py", f'KEY = "{FAKE_AWS_KEY}"\n')
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertIn("secret-aws-access-key-id", self.rules(report))
        self.assertNotIn(FAKE_AWS_KEY, json.dumps(report))

    def test_obvious_placeholder_credential_is_not_flagged(self):
        self.write("app.py", 'password = "your-password-goes-here-please"\n')
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)

    def test_swallowed_python_error_fails_but_handled_error_does_not(self):
        self.write("app.py", "try:\n    int('x')\nexcept ValueError:\n    pass\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertIn("swallowed-error", self.rules(report))

        self.write("app.py", "try:\n    int('x')\nexcept ValueError as error:\n    raise RuntimeError('bad') from error\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)

    def test_empty_javascript_catch_fails(self):
        self.write("app.js", "try { run(); } catch (error) {}\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertIn("swallowed-error", self.rules(report))

    def test_existing_problems_outside_the_change_are_not_reported(self):
        self.write("legacy.py", "try:\n    int('x')\nexcept ValueError:\n    pass\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "legacy code")
        self.write("app.py", "VALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)


    def test_naming_issues_warn_without_failing_the_gate(self):
        self.write("app.py", "x = 1\ndata = 2\nfor i in range(3):\n    pass\nsquares = [q * q for q in range(3)]\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        names = {warning["name"] for warning in report["warnings"]}
        self.assertEqual(names, {"x", "data"})
        self.assertTrue(all(warning["id"] for warning in report["warnings"]))


    def test_suppression_comment_is_tamper_and_fails_until_accepted(self):
        self.write("app.py", "import os  # noqa\nVALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        entry = next(entry for entry in report["tamper"] if entry["rule"] == "suppression-python-noqa")
        self.assertFalse(entry["accepted"])

        accepted = self.repo / "accepted.json"
        accepted.write_text(json.dumps([entry["id"]]), encoding="utf-8")
        code, report = self.gate("--accepted", str(accepted), path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["tamper"][0]["accepted"])

    def test_accepting_one_tamper_entry_does_not_accept_another(self):
        self.write("app.py", "import os  # noqa\nimport sys  # type: ignore\n")
        _, report = self.gate(path_without_tools=True)
        first, second = report["tamper"][0], report["tamper"][1]
        accepted = self.repo / "accepted.json"
        accepted.write_text(json.dumps([first["id"]]), encoding="utf-8")
        code, report = self.gate("--accepted", str(accepted), path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertEqual(report["summary"]["unresolvedTamper"], [second["id"]])

    def test_editing_linter_or_gate_configuration_is_tamper(self):
        self.write("ruff.toml", "line-length = 200\n")
        self.write(".quality-gate.json", "{}\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        flagged = {entry["file"] for entry in report["tamper"] if entry["rule"] == "config-edit"}
        self.assertEqual(flagged, {"ruff.toml", ".quality-gate.json"})

    def test_skipped_test_and_removed_assertions_are_tamper(self):
        self.write("tests/test_app.py", "import pytest\n\n@pytest.mark.skip\ndef test_value():\n    assert 1 == 1\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        rules = self.rules(report, "tamper")
        self.assertIn("skipped-test", rules)
        self.assertIn("removed-assertions", rules)

    def test_deleting_a_test_is_tamper(self):
        self.write("tests/test_app.py", "# nothing here any more\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertIn("deleted-tests", self.rules(report, "tamper"))

    def test_adding_a_test_with_assertions_is_not_tamper(self):
        self.write("tests/test_app.py", "def test_value():\n    assert 1 == 1\n    assert 2 == 2\n\ndef test_more():\n    assert 3 == 3\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)


    def test_declared_failing_check_fails_the_gate_and_passing_check_does_not(self):
        self.git("add", ".")
        self.write(".quality-gate.json", json.dumps({"checks": {"lint": [sys.executable, "-c", "raise SystemExit(3)"]}}))
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "declare checks")
        self.write("app.py", "VALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertEqual(self.check(report, "lint")["status"], "fail")
        self.assertEqual(self.check(report, "lint")["exitCode"], 3)

        self.write(".quality-gate.json", json.dumps({"checks": {"lint": [sys.executable, "-c", "pass"]}}))
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "passing lint")
        self.write("app.py", "VALUE = 3\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(self.check(report, "lint")["status"], "pass")

    def test_undeclared_checks_are_reported_not_hidden(self):
        self.write("app.py", "VALUE = 2\n")
        _, report = self.gate(path_without_tools=True)
        self.assertEqual(self.check(report, "types")["status"], "not_configured")

    def test_declared_command_that_does_not_exist_fails_rather_than_passing(self):
        self.write(".quality-gate.json", json.dumps({"checks": {"lint": ["definitely-not-a-real-tool-xyz"]}}))
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "declare checks")
        self.write("app.py", "VALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertEqual(self.check(report, "lint")["status"], "fail")

    def test_missing_optional_tool_warns_with_install_hint_and_does_not_fail(self):
        self.write("app.py", "VALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        gitleaks = self.check(report, "gitleaks")
        self.assertEqual(gitleaks["status"], "skipped")
        self.assertIn("brew install gitleaks", gitleaks["message"])
        self.assertEqual(report["status"], "warn")
        self.assertIn("gitleaks", report["summary"]["skippedTools"])

    def test_invalid_gate_config_is_a_gate_error_not_a_pass(self):
        self.write(".quality-gate.json", "{not json")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "error")


    def test_suppression_marker_in_a_string_or_prose_is_not_a_suppression(self):
        self.write("rules.py", 'PATTERN = "noqa"\nOTHER = r"#\\s*type:\\s*ignore"\n')
        self.write("notes.md", "Never add `# noqa` or eslint-disable to make the gate pass.\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["tamper"], [])

    def test_a_real_python_comment_suppression_is_still_caught(self):
        self.write("rules.py", 'PATTERN = "noqa"\nimport os  # noqa: F401\n')
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        flagged = [entry for entry in report["tamper"] if entry["rule"] == "suppression-python-noqa"]
        self.assertEqual([entry["line"] for entry in flagged], [2])

    def test_javascript_comment_suppression_is_caught_but_prose_is_not(self):
        self.write("app.js", "// eslint-disable-next-line no-console\nconsole.log(1);\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        self.assertIn("suppression-javascript-eslint-disable", self.rules(report, "tamper"))

    def declare_scoped_lint(self, command):
        config = {"checks": {"lint": command}, "suffixes": {"lint": [".py"]}}
        self.write(".quality-gate.json", json.dumps(config))
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "declare scoped lint")

    def test_scoped_check_runs_only_on_changed_files_of_the_declared_suffix(self):
        recorder = "import sys, pathlib; pathlib.Path('seen.txt').write_text('\\n'.join(sys.argv[1:]))"
        self.declare_scoped_lint([sys.executable, "-c", recorder, "{changed}"])
        self.write("app.py", "VALUE = 2\n")
        self.write("README.md", "docs\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        seen = (self.repo / "seen.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("app.py", seen)
        self.assertNotIn("README.md", seen)

    def test_scoped_check_ignores_failures_in_files_the_change_did_not_touch(self):
        # The command fails if it is ever handed legacy.py; only app.py changed, so it must not be.
        script = ("import sys; raise SystemExit(1 if any('legacy' in a for a in sys.argv[1:]) else 0)")
        self.write("legacy.py", "VALUE = 1\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "legacy")
        self.declare_scoped_lint([sys.executable, "-c", script, "{changed}"])
        self.write("app.py", "VALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(self.check(report, "lint")["status"], "pass")

    def test_scoped_check_with_no_matching_changed_files_is_reported_not_silently_passed(self):
        self.declare_scoped_lint([sys.executable, "-c", "raise SystemExit(1)", "{changed}"])
        self.write("README.md", "docs only\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(self.check(report, "lint")["status"], "not_configured")

    def test_a_skip_marker_inside_a_string_is_not_a_skipped_test(self):
        fixture = 'SOURCE = "@pytest.mark.skip"\n\ndef test_value():\n    assert 1 == 1\n    assert 2 == 2\n'
        self.write("tests/test_app.py", fixture)
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertNotIn("skipped-test", self.rules(report, "tamper"))

    def test_unittest_and_javascript_skips_are_caught(self):
        self.write("tests/test_app.py", "import unittest\n\n@unittest.skip('later')\ndef test_value():\n    assert 1 == 1\n    assert 2 == 2\n")
        self.write("tests/app.test.js", "it.skip('later', () => {});\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 1)
        files = {entry["file"] for entry in report["tamper"] if entry["rule"] == "skipped-test"}
        self.assertEqual(files, {"tests/test_app.py", "tests/app.test.js"})

    def test_the_word_noqa_in_a_comment_sentence_is_not_a_suppression(self):
        self.write("rules.py", "# A doc that merely names noqa in a sentence is not a suppression.\nVALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)


class InitDetectionTests(GateRepositoryCase):
    """--init proposes a config from what the repository declares; it never runs those commands."""

    def init(self):
        code, output = self.gate("--init")
        self.assertEqual(code, 0, output)
        return output

    def written_config(self):
        return json.loads((self.repo / ".quality-gate.json").read_text(encoding="utf-8"))

    def test_make_targets_are_preferred_and_carry_the_repositorys_own_environment(self):
        self.write("Makefile", "lint:\n\truff check .\nformat-check:\n\truff format --check .\n"
                               "typecheck:\n\tmypy src\ntest:\n\tpytest\n")
        self.write("pyproject.toml", "[tool.ruff]\nline-length = 100\n")
        self.init()
        self.assertEqual(self.written_config()["checks"], {
            "lint": ["make", "lint"], "format": ["make", "format-check"],
            "types": ["make", "typecheck"], "test": ["make", "test"],
        })

    def test_a_mutating_format_target_is_never_proposed(self):
        self.write("Makefile", "lint:\n\truff check .\nformat:\n\truff format .\n")
        output = self.init()
        self.assertNotIn("format", self.written_config()["checks"])
        self.assertTrue(any("mutating" in note for note in output["notes"]), output["notes"])

    def test_targets_that_need_credentials_or_infrastructure_are_never_proposed(self):
        self.write("Makefile", "system-test:\n\techo live\ndeploy-test:\n\techo deploy\nintegration-test:\n\techo x\n")
        self.init()
        self.assertNotIn("test", self.written_config()["checks"])

    def test_the_hermetic_target_is_chosen_when_a_live_one_sits_beside_it(self):
        self.write("Makefile", "system-test:\n\techo live\ntest:\n\techo hermetic\n")
        self.init()
        self.assertEqual(self.written_config()["checks"]["test"], ["make", "test"])

    def test_npm_scripts_are_used_when_there_is_no_makefile(self):
        self.write("package.json", json.dumps({"scripts": {"lint": "eslint .", "test": "jest", "format": "prettier -w ."}}))
        self.init()
        self.assertEqual(self.written_config()["checks"], {"lint": ["npm", "run", "lint"], "test": ["npm", "run", "test"]})

    def test_configured_ruff_is_scoped_to_changed_python_files(self):
        self.write("pyproject.toml", "[tool.ruff]\nline-length = 100\n")
        self.init()
        config = self.written_config()
        self.assertEqual(config["checks"]["lint"], ["ruff", "check", "{changed}"])
        self.assertEqual(config["checks"]["format"], ["ruff", "format", "--check", "{changed}"])
        self.assertEqual(config["suffixes"], {"lint": [".py"], "format": [".py"]})

    def test_make_targets_are_not_scoped_because_make_cannot_take_a_file_list(self):
        self.write("Makefile", "lint:\n\truff check .\n")
        self.init()
        self.assertNotIn("suffixes", self.written_config())

    def test_cargo_uses_check_mode_formatting(self):
        self.write("Cargo.toml", "[package]\nname = 'x'\n")
        self.init()
        self.assertEqual(self.written_config()["checks"]["format"], ["cargo", "fmt", "--check"])

    def test_an_existing_config_is_never_overwritten(self):
        self.write(".quality-gate.json", '{"checks": {"lint": ["hand-written"]}}\n')
        self.write("Makefile", "lint:\n\truff check .\n")
        code, output = self.gate("--init")
        self.assertEqual(code, 2)
        self.assertIn("already exists", output["error"])
        self.assertEqual(self.written_config(), {"checks": {"lint": ["hand-written"]}})

    def test_detection_never_runs_the_repositorys_commands(self):
        marker = self.repo / "ran.txt"
        self.write("Makefile", f"lint:\n\ttouch {marker}\n")
        self.init()
        self.assertFalse(marker.exists())

    def test_a_repository_with_nothing_detectable_gets_an_empty_proposal_and_says_so(self):
        output = self.init()
        self.assertEqual(self.written_config(), {"checks": {}})
        self.assertEqual(len(output["notes"]), 4)

    def test_the_proposed_config_is_one_the_gate_accepts_and_runs(self):
        self.write("Makefile", "test:\n\t@echo ok\n")
        self.init()
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "adopt proposed gate config")
        self.write("app.py", "VALUE = 2\n")
        code, report = self.gate(path_without_tools=True)
        self.assertEqual(code, 0, report)
        self.assertEqual(self.check(report, "test")["status"], "pass")

    def test_not_configured_message_tells_the_human_how_to_fix_it(self):
        self.write("app.py", "VALUE = 2\n")
        _, report = self.gate(path_without_tools=True)
        self.assertIn("--init", self.check(report, "lint")["message"])


@unittest.skipUnless(shutil.which("bandit"), "bandit is not installed")
class BanditScopeTests(GateRepositoryCase):
    """bandit scans whole files; the gate must only fail on lines the change added."""

    # B108 (hardcoded /tmp) is a MEDIUM issue that bandit -ll reports.
    TEMP_PATH_LINE = 'DENIED_PATHS = ["/tmp"]\n'

    def bandit_check(self):
        _, report = self.gate()
        return self.check(report, "bandit")

    def commit_legacy_issue(self):
        self.write("legacy.py", self.TEMP_PATH_LINE + "VALUE = 1\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "legacy issue")

    def test_an_existing_issue_in_a_touched_file_does_not_fail_the_gate(self):
        self.commit_legacy_issue()
        self.write("legacy.py", self.TEMP_PATH_LINE + "VALUE = 2\n")
        bandit = self.bandit_check()
        self.assertEqual(bandit["status"], "pass", bandit)

    def test_an_issue_on_an_added_line_fails_and_the_report_says_which(self):
        self.commit_legacy_issue()
        self.write("legacy.py", self.TEMP_PATH_LINE + "VALUE = 1\nOTHER_PATHS = ['/tmp/x']\n")
        bandit = self.bandit_check()
        self.assertEqual(bandit["status"], "fail")
        self.assertIn("legacy.py:3 B108", bandit["output"])
        self.assertNotIn("legacy.py:1 ", bandit["output"])

    def test_an_issue_in_a_new_file_fails(self):
        self.write("fresh.py", self.TEMP_PATH_LINE)
        bandit = self.bandit_check()
        self.assertEqual(bandit["status"], "fail")
        self.assertIn("fresh.py:1 B108", bandit["output"])

    def test_a_file_bandit_cannot_parse_fails_rather_than_passing(self):
        self.write("broken.py", "VALUE = (\n")
        bandit = self.bandit_check()
        self.assertEqual(bandit["status"], "fail")
        self.assertIn("broken.py", bandit["message"])


if __name__ == "__main__":
    unittest.main()
