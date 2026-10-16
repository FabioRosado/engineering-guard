import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = PROJECT_ROOT / ".codex" / "hooks" / "testing_guard.py"
HOOK_CONFIG_PATH = PROJECT_ROOT / ".codex" / "hooks.json"
POLICIES = {
    "testing": (PROJECT_ROOT / "policies" / "testing-policy.md").read_text(encoding="utf-8"),
    "engineering": (PROJECT_ROOT / "policies" / "engineering-policy.md").read_text(encoding="utf-8"),
}
SKILLS = (
    ("research", "engineering-guard-research"),
    ("implement", "engineering-guard-implement"),
    ("testing", "engineering-guard-testing"),
    ("verify", "engineering-guard-verify"),
    ("better-prompt", "engineering-guard-better-prompt"),
    ("align", "engineering-guard-align"),
    ("security", "engineering-guard-security"),
)
USER_IDENTITY = str(
    os.getuid()
    if hasattr(os, "getuid")
    else os.environ.get("USERPROFILE") or os.environ.get("HOME") or "user"
)


def session_event(event_name, session_id, **extra):
    return {
        "session_id": session_id,
        "transcript_path": None,
        "cwd": str(PROJECT_ROOT),
        "hook_event_name": event_name,
        "permission_mode": "default",
        **extra,
    }


def tool_event(tool_name, command, session_id="test-session"):
    return {
        **session_event("PreToolUse", session_id),
        "turn_id": "turn-123",
        "tool_name": tool_name,
        "tool_use_id": "call-456",
        "tool_input": {"command": command},
    }


class HookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory(prefix="engineering-guard-test-")
        cls.base_temp_directory = Path(cls.temp_directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp_directory.cleanup()

    def run_hook(self, event, script_path=HOOK_PATH, state_root=None, prepare_state_root=True):
        state_root = Path(state_root or self.base_temp_directory)
        if prepare_state_root:
            state_root.mkdir(parents=True, exist_ok=True)
        environment = {
            **os.environ,
            "TMP": str(state_root),
            "TEMP": str(state_root),
            "TMPDIR": str(state_root),
        }
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(event),
            text=True,
            capture_output=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def test_session_start_delivers_testing_policy_and_not_engineering_policy(self):
        started = self.run_hook(session_event("SessionStart", "startup-session", source="startup"))
        context = started["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(started["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn(POLICIES["testing"], context)
        self.assertNotIn(POLICIES["engineering"], context)
        self.assertIsNone(self.run_hook(tool_event("apply_patch", "*** Begin Patch\n*** Add File: tests/test_checkout.py\n+print('test')\n*** End Patch", "startup-session")))

    def test_missed_session_start_blocks_one_test_edit_then_allows_retry(self):
        patch = "*** Begin Patch\n*** Add File: tests/test_checkout.py\n+print('test')\n*** End Patch"
        first_attempt = self.run_hook(tool_event("apply_patch", patch, "first-test-session"))
        result = first_attempt["hookSpecificOutput"]
        self.assertEqual(result["hookEventName"], "PreToolUse")
        self.assertEqual(result["permissionDecision"], "deny")
        self.assertIn(POLICIES["testing"], result["additionalContext"])
        self.assertRegex(result["permissionDecisionReason"], r"retry this file change once")
        self.assertIsNone(self.run_hook(tool_event("apply_patch", patch, "first-test-session")))

    def test_codex_apply_patch_and_unrelated_tools(self):
        patch = "*** Begin Patch\n*** Update File: src/checkout.cjs\n-old\n+new\n*** End Patch"
        first_attempt = self.run_hook(tool_event("apply_patch", patch, "source-session"))
        self.assertEqual(first_attempt["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(POLICIES["engineering"], first_attempt["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.run_hook(tool_event("apply_patch", patch, "source-session")))
        self.assertIsNone(self.run_hook(tool_event("Bash", "node src/checkout.cjs")))

        unrelated = {
            **session_event("PreToolUse", "unrelated-session"),
            "tool_name": "mcp__filesystem__write_file",
            "tool_use_id": "call-mcp",
            "tool_input": {"path": "src/checkout.cjs", "contents": "new"},
        }
        self.assertIsNone(self.run_hook(unrelated))
        self.assertIsNone(self.run_hook(tool_event("some_other_tool", patch)))

    def test_bash_uses_codex_tool_input_command_for_writes_only(self):
        source_command = "node -e \"require('fs').writeFileSync('src/checkout.cjs', 'new')\""
        source_denied = self.run_hook(tool_event("Bash", source_command, "bash-source-session"))
        self.assertEqual(source_denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(POLICIES["engineering"], source_denied["hookSpecificOutput"]["additionalContext"])

        test_command = "cat > 'tests/test_checkout.py' <<'EOF'\nprint('test')\nEOF"
        test_denied = self.run_hook(tool_event("Bash", test_command, "bash-test-session"))
        self.assertEqual(test_denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(POLICIES["testing"], test_denied["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.run_hook(tool_event("Bash", "pytest tests/test_checkout.py", "bash-test-session")))

    def test_mixed_production_and_test_patch_delivers_both_policies_once(self):
        patch = "*** Begin Patch\n*** Update File: src/checkout.cjs\n-old\n+new\n*** Add File: tests/checkout.test.cjs\n+assert.ok(true)\n*** End Patch"
        denied = self.run_hook(tool_event("apply_patch", patch, "mixed-session"))
        output = denied["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn(POLICIES["testing"], output["additionalContext"])
        self.assertIn(POLICIES["engineering"], output["additionalContext"])
        self.assertIsNone(self.run_hook(tool_event("apply_patch", patch, "mixed-session")))

    def test_recognized_python_and_javascript_test_patterns(self):
        cases = (
            tool_event("Bash", "python -c \"open('tests/orders_test.py', 'w').write('x')\""),
            tool_event("Bash", "node -e \"require('fs').writeFileSync('src/checkout.test.ts', 'x')\""),
            tool_event("apply_patch", "*** Begin Patch\n*** Update File: src/__tests__/checkout.jsx\n-old\n+new\n*** End Patch"),
        )
        for index, event in enumerate(cases):
            event["session_id"] = f"naming-pattern-{index}"
            self.assertEqual(self.run_hook(event)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_session_start_after_compaction_restores_delivered_policies(self):
        session_id = "compact-session"
        self.run_hook(session_event("SessionStart", session_id, source="startup"))
        patch = "*** Begin Patch\n*** Update File: src/checkout.cjs\n-old\n+new\n*** End Patch"
        self.assertEqual(self.run_hook(tool_event("apply_patch", patch, session_id))["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(self.run_hook(tool_event("apply_patch", patch, session_id)))
        compacted = self.run_hook(session_event("SessionStart", session_id, source="compact"))
        context = compacted["hookSpecificOutput"]["additionalContext"]
        self.assertIn(POLICIES["testing"], context)
        self.assertIn(POLICIES["engineering"], context)

    def test_policy_edits_invalidate_acknowledgements(self):
        temp_project = Path(tempfile.mkdtemp(prefix="changed-policy-", dir=self.base_temp_directory))
        copied_hook = temp_project / ".codex" / "hooks" / "testing_guard.py"
        copied_testing_policy = temp_project / "policies" / "testing-policy.md"
        copied_engineering_policy = temp_project / "policies" / "engineering-policy.md"
        copied_hook.parent.mkdir(parents=True)
        copied_testing_policy.parent.mkdir(parents=True)
        shutil.copyfile(HOOK_PATH, copied_hook)
        shutil.copyfile(PROJECT_ROOT / "policies" / "testing-policy.md", copied_testing_policy)
        shutil.copyfile(PROJECT_ROOT / "policies" / "engineering-policy.md", copied_engineering_policy)
        state_root = self.base_temp_directory / "changed-policy-state"
        session_id = "changed-policy-session"
        options = {"script_path": copied_hook, "state_root": state_root}

        self.run_hook(session_event("SessionStart", session_id, source="startup"), **options)
        patch = "*** Begin Patch\n*** Update File: src/checkout.cjs\n-old\n+new\n*** End Patch"
        first_source_write = self.run_hook(tool_event("apply_patch", patch, session_id), **options)
        self.assertIn(POLICIES["engineering"], first_source_write["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.run_hook(tool_event("apply_patch", patch, session_id), **options))

        revised_engineering = f"{POLICIES['engineering']}\nUpdated engineering policy.\n"
        copied_engineering_policy.write_text(revised_engineering, encoding="utf-8")
        stale_engineering_ack = self.run_hook(tool_event("apply_patch", patch, session_id), **options)
        self.assertEqual(stale_engineering_ack["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Updated engineering policy.", stale_engineering_ack["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.run_hook(tool_event("apply_patch", patch, session_id), **options))

        revised_testing = f"{POLICIES['testing']}\nUpdated testing policy.\n"
        copied_testing_policy.write_text(revised_testing, encoding="utf-8")
        test_patch = "*** Begin Patch\n*** Add File: tests/test_checkout.py\n+print('test')\n*** End Patch"
        stale_testing_ack = self.run_hook(tool_event("apply_patch", test_patch, session_id), **options)
        self.assertEqual(stale_testing_ack["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Updated testing policy.", stale_testing_ack["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.run_hook(tool_event("apply_patch", test_patch, session_id), **options))

    def test_session_state_isolation_cleanup_and_missing_session_id(self):
        session_a = "session-a"
        self.run_hook(session_event("SessionStart", session_a, source="startup"))
        self.assertIsNone(self.run_hook(tool_event("apply_patch", "*** Begin Patch\n*** Add File: tests/test_x.py\n+x\n*** End Patch", session_a)))

        session_b = self.run_hook(tool_event("apply_patch", "*** Begin Patch\n*** Add File: tests/test_x.py\n+x\n*** End Patch", "session-b"))
        self.assertEqual(session_b["hookSpecificOutput"]["permissionDecision"], "deny")
        self.run_hook(session_event("SessionEnd", session_a, reason="other"))
        namespace = hashlib.sha256(USER_IDENTITY.encode()).hexdigest()[:16]
        session_hash = hashlib.sha256(session_a.encode()).hexdigest()
        state_file = self.base_temp_directory / f"engineering-guard-{namespace}" / f"{session_hash}.json"
        self.assertFalse(state_file.exists())

        missing_id = self.run_hook(tool_event("apply_patch", "*** Begin Patch\n*** Add File: tests/test_x.py\n+x\n*** End Patch", None))
        self.assertEqual(missing_id["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertRegex(missing_id["hookSpecificOutput"]["permissionDecisionReason"], r"did not provide a session_id")

    def test_state_storage_failure_denies_without_retry_loop(self):
        unavailable_path = self.base_temp_directory / "temp-path-is-a-file"
        unavailable_path.write_text("not a directory", encoding="utf-8")
        start = self.run_hook(
            session_event("SessionStart", "state-error-session", source="startup"),
            state_root=unavailable_path,
            prepare_state_root=False,
        )
        self.assertRegex(start["systemMessage"], r"could not load or record a policy")
        denied = self.run_hook(
            tool_event("Bash", "cat > tests/test_checkout.py", "state-error-session"),
            state_root=unavailable_path,
            prepare_state_root=False,
        )
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertRegex(denied["hookSpecificOutput"]["permissionDecisionReason"], r"Do not retry until")

    def test_codex_config_and_skills_use_expected_repository_discovery_paths(self):
        config = json.loads(HOOK_CONFIG_PATH.read_text(encoding="utf-8"))
        matchers = [group["matcher"] for group in config["hooks"]["PreToolUse"]]
        self.assertIn("SessionStart", config["hooks"])
        self.assertIn("PreToolUse", config["hooks"])
        self.assertIn("SessionEnd", config["hooks"])
        self.assertTrue(any(re.search(matcher, "Bash") for matcher in matchers))
        self.assertTrue(any(re.search(matcher, "apply_patch") for matcher in matchers))
        self.assertNotIn("Stop", config["hooks"])
        for directory, name in SKILLS:
            path = PROJECT_ROOT / ".agents" / "skills" / directory / "SKILL.md"
            skill = path.read_text(encoding="utf-8")
            self.assertTrue(skill.startswith("---\n"), str(path))
            self.assertEqual(skill.count("\n---\n"), 1, str(path))
            self.assertIn(f"name: {name}\n", skill)
        for event in ("SessionStart", "PreToolUse", "SessionEnd"):
            command = config["hooks"][event][0]["hooks"][0]
            self.assertIn("python3 .codex/hooks/testing_guard.py", command["command"])
            self.assertIn("py -3 .codex/hooks/testing_guard.py", command["commandWindows"])

    def test_malformed_hook_input_preserves_codex_handling(self):
        result = subprocess.run([sys.executable, str(HOOK_PATH)], input="{not-json", text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
