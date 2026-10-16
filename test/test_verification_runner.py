import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = PROJECT_ROOT / "scripts" / "verification_runner.py"


class VerificationRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory(prefix="engineering-guard-runner-")
        cls.temp_root = Path(cls.temp_directory.name)
        cls.next_fixture = 0

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    def create_repository(self, scripts=None, files=None, commit=True):
        scripts = scripts or {}
        files = files or {}
        root = self.temp_root / f"repo-{self.next_fixture}"
        type(self).next_fixture += 1
        root.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "engineering-guard@example.test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Engineering Guard Test"], cwd=root, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=root, check=True)
        (root / "package.json").write_text(json.dumps({"private": True, "scripts": scripts}, indent=2), encoding="utf-8")
        for relative_path, contents in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        if commit:
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "fixture baseline"], cwd=root, check=True)
        return root

    def run_runner(self, root, *args):
        result = subprocess.run(
            [sys.executable, str(RUNNER_SCRIPT), *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result, json.loads(result.stdout)

    def test_inventory_reports_baseline_changes_and_scripts_without_running_them(self):
        root = self.create_repository(
            {"test": "node -e \"process.exit(1)\""},
            {"src/handler.mjs": "export const value = 1;\n"},
        )
        (root / "src" / "handler.mjs").write_text("export const value = 2;\n", encoding="utf-8")
        (root / "notes.txt").write_text("untracked\n", encoding="utf-8")

        result, report = self.run_runner(root)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["status"], "inventory_only")
        self.assertEqual(report["assessment"], "execution_evidence_only")
        self.assertEqual(len(report["repository"]["baseline"]), 40)
        self.assertEqual(
            report["repository"]["changedFiles"],
            [{"path": "notes.txt", "status": "??"}, {"path": "src/handler.mjs", "status": "M"}],
        )
        self.assertEqual([item["name"] for item in report["checks"]["availableScripts"]], ["test"])
        self.assertEqual(report["checks"]["notRequested"], ["test"])
        self.assertEqual(report["checks"]["executed"], [])
        self.assertIsNone(report["checks"]["allPassed"])

    def test_explicit_baseline_includes_committed_changes_since_that_ref(self):
        root = self.create_repository({}, {"src/handler.mjs": "export const value = 1;\n"})
        baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        (root / "src" / "handler.mjs").write_text("export const value = 2;\n", encoding="utf-8")
        subprocess.run(["git", "add", "src/handler.mjs"], cwd=root, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "update handler"], cwd=root, check=True)

        result, report = self.run_runner(root, "--base", baseline)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["repository"]["baseline"], baseline)
        self.assertEqual(report["repository"]["changedFiles"], [{"path": "src/handler.mjs", "status": "M"}])
        self.assertIn("src/handler.mjs", report["repository"]["diffStat"])

    def test_unborn_repository_is_inventoried(self):
        root = self.create_repository({"test": "node --test"}, commit=False)

        result, report = self.run_runner(root)

        self.assertEqual(result.returncode, 0)
        self.assertIsNone(report["repository"]["head"])
        self.assertEqual(report["repository"]["baseline"], "unborn repository")
        self.assertEqual(report["repository"]["changedFiles"], [{"path": "package.json", "status": "??"}])

    def test_only_selected_npm_scripts_run_and_lifecycle_scripts_are_skipped(self):
        scripts = {
            "pretest": "node -e \"require('node:fs').writeFileSync('pretest-ran', 'yes')\"",
            "test": "node -e \"require('node:fs').mkdirSync('coverage',{recursive:true}); require('node:fs').writeFileSync('coverage/lcov.info','TN:\\n'); process.stdout.write('tests passed')\"",
            "lint": "node -e \"require('node:fs').writeFileSync('lint-ran', 'yes')\"",
        }
        root = self.create_repository(scripts, {".gitignore": "coverage/\n", "src/handler.mjs": "export const value = 1;\n"})

        result, report = self.run_runner(root, "--run", "test")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["status"], "checks_passed")
        self.assertTrue(report["checks"]["allPassed"])
        self.assertEqual(report["checks"]["requested"], ["test"])
        self.assertEqual(report["checks"]["notRequested"], ["pretest", "lint"])
        check = report["checks"]["executed"][0]
        self.assertEqual(check["command"], "npm run --ignore-scripts test")
        self.assertEqual(check["repositoryFingerprint"], report["repository"]["snapshot"]["before"])
        self.assertIn("tests passed", check["stdout"])
        self.assertEqual(report["coverageEvidence"], [{"path": "coverage/lcov.info", "sizeBytes": 4}])
        self.assertTrue(report["repository"]["snapshot"]["unchangedDuringChecks"])
        self.assertEqual(report["assessment"], "execution_evidence_only")
        self.assertFalse((root / "pretest-ran").exists())
        self.assertFalse((root / "lint-ran").exists())

    def test_failed_command_records_exit_code_and_output(self):
        root = self.create_repository({"test": "node -e \"console.error('intentional failure'); process.exitCode = 7\""})

        result, report = self.run_runner(root, "--run", "test")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["status"], "checks_failed")
        self.assertFalse(report["checks"]["allPassed"])
        self.assertEqual(report["checks"]["executed"][0]["exitCode"], 7)
        self.assertIn("intentional failure", report["checks"]["executed"][0]["stderr"])

    def test_passing_check_that_changes_source_is_reported_stale(self):
        command = "node -e \"require('node:fs').writeFileSync('src/handler.mjs', 'changed\\n')\""
        root = self.create_repository({"test": command}, {"src/handler.mjs": "export const value = 1;\n"})

        result, report = self.run_runner(root, "--run", "test")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["status"], "snapshot_changed")
        self.assertEqual(report["checks"]["executed"][0]["outcome"], "passed")
        self.assertFalse(report["repository"]["snapshot"]["unchangedDuringChecks"])
        self.assertNotEqual(report["repository"]["snapshot"]["before"], report["repository"]["snapshot"]["after"])
        self.assertEqual(report["assessment"], "execution_evidence_only")

    def test_unavailable_check_and_invalid_baseline_return_structured_errors(self):
        root = self.create_repository({"test": "node -e \"process.exit(9)\""})

        unavailable_result, unavailable = self.run_runner(root, "--run", "missing")
        self.assertEqual(unavailable_result.returncode, 2)
        self.assertEqual(unavailable["status"], "selection_error")
        self.assertEqual(unavailable["checks"]["unavailable"], ["missing"])
        self.assertEqual(unavailable["checks"]["executed"], [])

        invalid_result, invalid = self.run_runner(root, "--base", "not-a-commit")
        self.assertEqual(invalid_result.returncode, 2)
        self.assertEqual(invalid["status"], "error")
        self.assertIn("does not resolve to a commit", invalid["error"])

    def test_command_output_is_bounded(self):
        root = self.create_repository({"test": "node -e \"process.stdout.write('x'.repeat(3*1024*1024))\""})

        result, report = self.run_runner(root, "--run", "test")

        self.assertEqual(result.returncode, 1)
        check = report["checks"]["executed"][0]
        self.assertEqual(report["status"], "checks_failed")
        self.assertEqual(check["error"]["code"], "ERR_CHILD_PROCESS_STDIO_MAXBUFFER")
        self.assertLessEqual(len(check["stdout"]), 20_000)


if __name__ == "__main__":
    unittest.main()
