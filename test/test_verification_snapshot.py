import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCRIPT = PROJECT_ROOT / "scripts" / "verification_snapshot.py"


class VerificationSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory(prefix="engineering-guard-snapshot-")
        self.fixture_root = Path(self.temp_directory.name) / "fixture"
        (self.fixture_root / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(self.fixture_root)], check=True)
        (self.fixture_root / "src" / "handler.mjs").write_text("export const value = 1;\n", encoding="utf-8")

    def tearDown(self):
        self.temp_directory.cleanup()

    def check_snapshot(self, expected=None):
        command = [sys.executable, str(SNAPSHOT_SCRIPT)]
        if expected:
            command.append(expected)
        result = subprocess.run(command, cwd=self.fixture_root, capture_output=True, text=True)
        self.assertTrue(result.stdout.strip(), result.stderr)
        output = json.loads(result.stdout) if result.stdout.strip() else None
        return result, output

    def test_evidence_is_missing_until_a_fingerprint_is_supplied(self):
        result, missing = self.check_snapshot()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(missing["status"], "missing")
        self.assertRegex(missing["fingerprint"], r"^[a-f0-9]{64}$")

        current_result, current = self.check_snapshot(missing["fingerprint"])
        self.assertEqual(current_result.returncode, 0)
        self.assertEqual(current["status"], "current")

    def test_edit_addition_and_deletion_stale_previous_evidence(self):
        initial = self.check_snapshot()[1]["fingerprint"]
        source = self.fixture_root / "src" / "handler.mjs"
        source.write_text("export const value = 2;\n", encoding="utf-8")
        after_edit_result, after_edit = self.check_snapshot(initial)
        self.assertEqual(after_edit_result.returncode, 1)
        self.assertEqual(after_edit["status"], "stale")

        (self.fixture_root / "src" / "new-handler.mjs").write_text("export const added = true;\n", encoding="utf-8")
        after_add_result, after_add = self.check_snapshot(after_edit["fingerprint"])
        self.assertEqual(after_add_result.returncode, 1)
        self.assertEqual(after_add["status"], "stale")

        source.unlink()
        after_delete_result, after_delete = self.check_snapshot(after_add["fingerprint"])
        self.assertEqual(after_delete_result.returncode, 1)
        self.assertEqual(after_delete["status"], "stale")

    def test_uncommitted_repository_can_be_fingerprinted(self):
        head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=self.fixture_root, capture_output=True)
        self.assertNotEqual(head.returncode, 0)
        result, output = self.check_snapshot()
        self.assertEqual(result.returncode, 0)
        self.assertRegex(output["fingerprint"], r"^[a-f0-9]{64}$")

    def test_symlink_target_is_included_in_fingerprint(self):
        link = self.fixture_root / "src" / "current"
        link.symlink_to("handler.mjs")
        first = self.check_snapshot()[1]["fingerprint"]
        link.unlink()
        link.symlink_to("missing.mjs")
        second = self.check_snapshot()[1]["fingerprint"]
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
