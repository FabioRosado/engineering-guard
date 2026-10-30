"""Whether `npm run dashboard` rebuilds the UI (scripts/ui-build-state.mjs), decided from file times."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE = PROJECT_ROOT / "scripts" / "ui-build-state.mjs"
HOUR = 3600


@unittest.skipUnless(shutil.which("node"), "node is required to evaluate the build-state module")
class UiBuildStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ui-build-state-")
        self.ui = Path(self.temp.name) / "ui"
        (self.ui / "src" / "lib").mkdir(parents=True)
        (self.ui / "dist" / "assets").mkdir(parents=True)
        for name in ("index.html", "package.json", "package-lock.json", "vite.config.js", "svelte.config.js"):
            (self.ui / name).write_text("x", encoding="utf-8")
        (self.ui / "src" / "App.svelte").write_text("x", encoding="utf-8")
        (self.ui / "src" / "lib" / "jobs.js").write_text("x", encoding="utf-8")
        (self.ui / "dist" / "index.html").write_text("built", encoding="utf-8")
        self.set_times_everywhere(older_than_build=True)

    def tearDown(self):
        self.temp.cleanup()

    def set_times_everywhere(self, older_than_build):
        """Sources an hour older than the build, or leave them at 'now' (newer than it)."""
        build_time = 1_700_000_000
        os.utime(self.ui / "dist" / "index.html", (build_time, build_time))
        for path in self.ui.rglob("*"):
            if "dist" in path.relative_to(self.ui).parts or not path.is_file():
                continue
            stamp = build_time - HOUR if older_than_build else build_time + HOUR
            os.utime(path, (stamp, stamp))

    def touch(self, relative):
        newer = 1_700_000_000 + HOUR
        os.utime(self.ui / relative, (newer, newer))

    def reason(self):
        script = (
            f"import {{ buildReason }} from {json.dumps(MODULE.as_uri())};"
            f"process.stdout.write(JSON.stringify(buildReason({json.dumps(str(self.ui))})));"
        )
        result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_a_current_build_is_not_rebuilt(self):
        self.assertIsNone(self.reason())

    def test_a_missing_build_is_built(self):
        (self.ui / "dist" / "index.html").unlink()
        self.assertIn("not been built", self.reason())

    def test_an_edited_source_file_triggers_a_rebuild_naming_where(self):
        self.touch("src/App.svelte")
        self.assertIn("ui/src changed", self.reason())

    def test_an_edit_in_a_nested_source_folder_is_noticed(self):
        self.touch("src/lib/jobs.js")
        self.assertIn("ui/src changed", self.reason())

    def test_each_build_input_outside_src_is_watched(self):
        for name in ("index.html", "package.json", "package-lock.json", "vite.config.js", "svelte.config.js"):
            with self.subTest(file=name):
                self.set_times_everywhere(older_than_build=True)
                self.touch(name)
                self.assertIn(name, self.reason())

    def test_build_output_and_dependencies_do_not_cause_a_rebuild(self):
        # Rebuilding because dist/ or node_modules changed would rebuild on every launch.
        (self.ui / "node_modules" / "pkg").mkdir(parents=True)
        module_file = self.ui / "node_modules" / "pkg" / "index.js"
        module_file.write_text("x", encoding="utf-8")
        os.utime(module_file, (1_700_000_000 + HOUR, 1_700_000_000 + HOUR))
        asset = self.ui / "dist" / "assets" / "app.js"
        asset.write_text("x", encoding="utf-8")
        os.utime(asset, (1_700_000_000 + HOUR, 1_700_000_000 + HOUR))
        self.assertIsNone(self.reason())


if __name__ == "__main__":
    unittest.main()
