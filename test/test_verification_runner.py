import json
import os
import signal
import subprocess
import sys
import tempfile
import time
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

    def run_runner_with_limits(self, root, command_timeout, cleanup_timeout, terminate_grace, *args):
        # Exercise the real CLI and npm subprocesses with shorter deadlines for deterministic tests.
        harness = (
            "import importlib.util, sys; "
            "spec = importlib.util.spec_from_file_location('runner_under_test', sys.argv[1]); "
            "runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner); "
            "runner.TIMEOUT_SECONDS = float(sys.argv[2]); "
            "runner.CLEANUP_TIMEOUT_SECONDS = float(sys.argv[3]); "
            "runner.TERMINATE_GRACE_SECONDS = float(sys.argv[4]); "
            "sys.exit(runner.main(sys.argv[5:]))"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                harness,
                str(RUNNER_SCRIPT),
                str(command_timeout),
                str(cleanup_timeout),
                str(terminate_grace),
                *args,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
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

    def test_staged_only_change_appears_in_scope(self):
        root = self.create_repository({}, {"src/handler.mjs": "original"})
        source = root / "src" / "handler.mjs"
        source.write_text("staged", encoding="utf-8")
        subprocess.run(["git", "add", "src/handler.mjs"], cwd=root, check=True)
        source.write_text("original", encoding="utf-8")

        result, report = self.run_runner(root)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["repository"]["changedFiles"], [{"path": "src/handler.mjs", "status": "M"}])

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
        self.assertEqual(check["commandOutcome"], "passed")
        self.assertEqual(check["cleanup"]["status"], "not_needed")
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
        self.assertEqual(report["checks"]["executed"][0]["commandOutcome"], "failed")
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

    def test_change_then_restore_between_checks_remains_stale(self):
        root = self.create_repository(
            {
                "change": "node -e \"require('node:fs').writeFileSync('src/handler.mjs', 'changed')\"",
                "restore": "node -e \"require('node:fs').writeFileSync('src/handler.mjs', 'original')\"",
            },
            {"src/handler.mjs": "original"},
        )
        result, report = self.run_runner(root, "--run", "change", "--run", "restore")
        checks = report["checks"]["executed"]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["status"], "snapshot_changed")
        self.assertEqual(report["repository"]["snapshot"]["before"], report["repository"]["snapshot"]["after"])
        self.assertFalse(report["repository"]["snapshot"]["unchangedDuringChecks"])
        self.assertEqual(checks[0]["snapshotAfter"], checks[1]["repositoryFingerprint"])
        self.assertNotEqual(checks[0]["repositoryFingerprint"], checks[1]["repositoryFingerprint"])

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
        self.assertEqual(check["commandOutcome"], "failed")
        self.assertLessEqual(len(check["stdout"]), 20_000)

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup contract")
    def test_output_overflow_escalates_and_reaps_remaining_process_group(self):
        root = self.create_repository(
            {"test": "python3 overflow_parent.py"},
            {
                ".gitignore": "child.pid\nchild.ready\n",
                "overflow_parent.py": (
                    "import subprocess\n"
                    "import sys\n"
                    "import time\n"
                    "from pathlib import Path\n"
                    "child = subprocess.Popen([sys.executable, '-c', \"import signal, time; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); Path('child.ready').touch(); time.sleep(60)\"])\n"
                    "Path('child.pid').write_text(str(child.pid), encoding='utf-8')\n"
                    "for _ in range(300):\n"
                    "    if Path('child.ready').exists():\n"
                    "        break\n"
                    "    time.sleep(0.01)\n"
                    "else:\n"
                    "    raise RuntimeError('child did not become ready')\n"
                    "sys.stdout.write('x' * (3 * 1024 * 1024))\n"
                    "sys.stdout.flush()\n"
                ),
            },
        )
        child_pid = None
        try:
            result, report = self.run_runner_with_limits(root, 3, 0.8, 0.2, "--run", "test")
            check = report["checks"]["executed"][0]
            child_pid = int((root / "child.pid").read_text(encoding="utf-8"))

            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            self.assertEqual(report["status"], "checks_failed")
            self.assertFalse(report["checks"]["allPassed"])
            self.assertEqual(check["error"]["code"], "ERR_CHILD_PROCESS_STDIO_MAXBUFFER")
            self.assertEqual(check["commandOutcome"], "failed")
            self.assertEqual(check["cleanup"]["status"], "complete")
            self.assertTrue(check["cleanup"]["directProcessReaped"])
            self.assertTrue(check["cleanup"]["outputReadersStopped"])
            self.assertEqual(check["cleanup"]["trackedProcessGroup"], "absent")
            self.assertEqual(check["cleanup"]["terminationRequestsSent"], ["SIGTERM", "SIGKILL"])
            self.assertLess(check["durationMs"], 2_200)
            self.assertLessEqual(len(check["stdout"]), 20_000)
        finally:
            if child_pid is None and (root / "child.pid").exists():
                child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup contract")
    def test_timeout_escalates_for_a_process_that_ignores_sigterm_within_one_cleanup_budget(self):
        root = self.create_repository(
            {"test": 'node -e "process.on(\'SIGTERM\', () => {}); setInterval(() => {}, 1000)"'}
        )

        result, report = self.run_runner_with_limits(root, 0.4, 0.8, 0.2, "--run", "test")

        check = report["checks"]["executed"][0]
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["status"], "checks_failed")
        self.assertEqual(check["error"]["code"], "ETIMEDOUT")
        self.assertEqual(check["commandOutcome"], "failed")
        self.assertEqual(check["cleanup"]["status"], "complete")
        self.assertTrue(check["cleanup"]["directProcessReaped"])
        self.assertTrue(check["cleanup"]["outputReadersStopped"])
        self.assertEqual(check["cleanup"]["trackedProcessGroup"], "absent")
        self.assertEqual(check["cleanup"]["terminationRequestsSent"], ["SIGTERM", "SIGKILL"])
        self.assertLessEqual(check["durationMs"], 1_700)

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup contract")
    def test_terminal_interrupt_cleans_up_the_selected_process_group(self):
        for interrupt_signal in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=signal.Signals(interrupt_signal).name):
                self.assert_runner_signal_cleans_up_process_group(interrupt_signal)

    def assert_runner_signal_cleans_up_process_group(self, interrupt_signal):
        root = self.create_repository(
            {"test": "python3 wait_for_interrupt.py"},
            {
                ".gitignore": "process.pid\nprocess.pgid\nprocess.ready\n",
                "wait_for_interrupt.py": (
                    "import os\n"
                    "import signal\n"
                    "import time\n"
                    "from pathlib import Path\n"
                    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                    "Path('process.pid').write_text(str(os.getpid()), encoding='utf-8')\n"
                    "Path('process.pgid').write_text(str(os.getpgrp()), encoding='utf-8')\n"
                    "Path('process.ready').touch()\n"
                    "time.sleep(60)\n"
                ),
            },
        )
        runner = subprocess.Popen(
            [sys.executable, str(RUNNER_SCRIPT), "--run", "test"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        command_group = None
        try:
            ready_path = root / "process.ready"
            startup_deadline = time.monotonic() + 10
            while not ready_path.exists() and runner.poll() is None and time.monotonic() < startup_deadline:
                time.sleep(0.01)
            self.assertTrue(ready_path.exists(), "selected command did not reach its ready state")
            command_pid = int((root / "process.pid").read_text(encoding="utf-8"))
            command_group = int((root / "process.pgid").read_text(encoding="utf-8"))

            # SIGINT to this group models terminal Ctrl-C; SIGTERM follows the same cleanup path.
            os.killpg(runner.pid, interrupt_signal)
            stdout, stderr = runner.communicate(timeout=10)
            self.assertEqual(runner.returncode, 1, stderr + stdout)
            report = json.loads(stdout)
            check = report["checks"]["executed"][0]

            self.assertEqual(report["status"], "checks_failed")
            self.assertFalse(report["checks"]["allPassed"])
            self.assertEqual(check["error"]["code"], "EINTR")
            self.assertEqual(check["commandOutcome"], "failed")
            self.assertEqual(check["cleanup"]["status"], "complete")
            self.assertTrue(check["cleanup"]["directProcessReaped"])
            self.assertTrue(check["cleanup"]["outputReadersStopped"])
            self.assertEqual(check["cleanup"]["trackedProcessGroup"], "absent")
            self.assertEqual(check["cleanup"]["terminationRequestsSent"], ["SIGTERM", "SIGKILL"])
            self.assertLess(check["durationMs"], 6_500)
            with self.assertRaises(ProcessLookupError):
                os.kill(command_pid, 0)
            with self.assertRaises(ProcessLookupError):
                os.killpg(command_group, 0)
        finally:
            if runner.poll() is None:
                try:
                    os.killpg(runner.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                runner.wait(timeout=5)
            if command_group is not None:
                try:
                    os.killpg(command_group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if runner.stdout:
                runner.stdout.close()
            if runner.stderr:
                runner.stderr.close()

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup contract")
    def test_remaining_group_is_escalated_after_npm_leader_exits(self):
        root = self.create_repository(
            {"test": "python3 spawn_child.py"},
            {
                ".gitignore": "child.pid\nchild.ready\n",
                "spawn_child.py": (
                    "import subprocess\n"
                    "import sys\n"
                    "import time\n"
                    "from pathlib import Path\n"
                    "child = subprocess.Popen([sys.executable, '-c', \"import signal, time; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); Path('child.ready').touch(); time.sleep(60)\"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                    "Path('child.pid').write_text(str(child.pid), encoding='utf-8')\n"
                    "for _ in range(300):\n"
                    "    if Path('child.ready').exists():\n"
                    "        break\n"
                    "    time.sleep(0.01)\n"
                    "else:\n"
                    "    raise RuntimeError('child did not become ready')\n"
                )
            },
        )

        child_pid = None
        try:
            result, report = self.run_runner_with_limits(root, 3, 0.8, 0.2, "--run", "test")

            check = report["checks"]["executed"][0]
            child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(check["commandOutcome"], "passed")
            self.assertEqual(check["cleanup"]["status"], "complete")
            self.assertEqual(check["cleanup"]["trackedProcessGroup"], "absent")
            try:
                child_group = os.getpgid(child_pid)
            except ProcessLookupError:
                child_group = None
            self.assertEqual(
                check["cleanup"]["terminationRequestsSent"],
                ["SIGTERM", "SIGKILL"],
                f"cleanup={check['cleanup']}, surviving_child_group={child_group}",
            )
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
        finally:
            if child_pid is None and (root / "child.pid").exists():
                child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup contract")
    def test_successful_group_signal_does_not_claim_escaped_descendant_cleanup(self):
        root = self.create_repository(
            {"test": "python3 spawn_parent.py"},
            {
                ".gitignore": "child.pid\nchild.ready\nescaped.pid\n",
                "spawn_parent.py": (
                    "import subprocess\n"
                    "import sys\n"
                    "import time\n"
                    "from pathlib import Path\n"
                    "child = subprocess.Popen([sys.executable, 'wait_and_escape.py'])\n"
                    "for _ in range(300):\n"
                    "    if Path('child.ready').exists():\n"
                    "        break\n"
                    "    time.sleep(0.01)\n"
                    "else:\n"
                    "    raise RuntimeError('child did not become ready')\n"
                    "Path('child.pid').write_text(str(child.pid), encoding='utf-8')\n"
                ),
                "wait_and_escape.py": (
                    "import signal\n"
                    "import subprocess\n"
                    "import sys\n"
                    "import time\n"
                    "from pathlib import Path\n"
                    "def escape(_signum, _frame):\n"
                    "    subprocess.Popen([sys.executable, '-c', \"import os, time; from pathlib import Path; Path('escaped.pid').write_text(str(os.getpid()), encoding='utf-8'); time.sleep(60)\"], start_new_session=True, stdin=subprocess.DEVNULL)\n"
                    "    raise SystemExit(0)\n"
                    "signal.signal(signal.SIGTERM, escape)\n"
                    "Path('child.ready').touch()\n"
                    "time.sleep(60)\n"
                )
            },
        )
        escaped_pid = None
        try:
            result, report = self.run_runner_with_limits(root, 3, 0.5, 0.2, "--run", "test")
            check = report["checks"]["executed"][0]
            escaped_pid = int((root / "escaped.pid").read_text(encoding="utf-8"))

            self.assertEqual(result.returncode, 1)
            self.assertEqual(check["commandOutcome"], "passed")
            self.assertEqual(check["outcome"], "failed")
            self.assertEqual(check["cleanup"]["status"], "incomplete")
            self.assertTrue(check["cleanup"]["directProcessReaped"])
            self.assertFalse(check["cleanup"]["outputReadersStopped"])
            self.assertEqual(check["cleanup"]["trackedProcessGroup"], "absent")
            self.assertEqual(check["cleanup"]["terminationRequestsSent"], ["SIGTERM"])
            self.assertLess(check["durationMs"], 2_000)
            self.assertIsNone(report["repository"]["snapshot"]["after"])
            self.assertIsNone(report["repository"]["snapshot"]["unchangedDuringChecks"])
            self.assertEqual(report["status"], "checks_failed")
            self.assertFalse(report["checks"]["allPassed"])
        finally:
            if escaped_pid is None and (root / "escaped.pid").exists():
                escaped_pid = int((root / "escaped.pid").read_text(encoding="utf-8"))
            if escaped_pid is not None:
                try:
                    os.kill(escaped_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
