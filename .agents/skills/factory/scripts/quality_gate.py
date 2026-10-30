"""Quality gate: deterministic checks over the uncommitted change (decisions/quality-gate.md).

Policies are advisory text and agents skip them, so this script checks what can be
checked mechanically and writes one JSON report. The same script is run by humans
(`npm run quality`) and by the factory's `quality-gate-done`, so both see the same
result. It uses only the standard library; external scanners are optional.

Result of each check is one of:
  pass            ran and found nothing
  fail            found a problem that must be fixed (never loosened or bypassed)
  warn            needs the builder's attention but does not fail the gate
  skipped         optional tool is not installed (warns with an install hint)
  not_configured  the repository declares no command for this check

Findings never contain matched secret values: only file, line and rule.

Exit code: 0 when no check failed and no tamper entry is unresolved, 1 otherwise,
2 when the gate itself could not run.
"""

import argparse
import ast
import fnmatch
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

REPORT_SCHEMA_VERSION = 1
GATE_CONFIG_NAME = ".quality-gate.json"
CHECK_TIMEOUT_SECONDS = 300
OUTPUT_TAIL_CHARACTERS = 4000

PYTHON_SUFFIXES = (".py",)
JAVASCRIPT_SUFFIXES = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
CODE_SUFFIXES = PYTHON_SUFFIXES + JAVASCRIPT_SUFFIXES
TEST_PATH_PATTERN = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)test_[^/]*$|[._]test\.[^/]*$|[._]spec\.[^/]*$")

# A line made only of a comment marker followed by a run of one repeated rule character
# is a banner. Four characters keeps a markdown-style "# ---" or "// ===" from tripping it.
BANNER_PATTERN = re.compile(r"^\s*(#|//|/\*|\*)\s*([-=*#~_+<>/\\.])\2{3,}\s*(\*/)?\s*$")
BANNER_TITLE_PATTERN = re.compile(r"^\s*(#|//)\s*([-=*#~_+])\2{3,}\s+\S.*\s+\2{3,}\s*$")

# Shapes of credentials. Matching is on the *added line text* and only the rule name is
# reported, so a leaked value never reaches the report or the dashboard.
SECRET_PATTERNS = (
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("bearer-literal", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{24,}")),
    (
        "credential-assignment",
        re.compile(
            r"""(?ix)\b(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b
                \s*[:=]\s*["'][^"'\s]{12,}["']"""
        ),
    ),
)
# Obvious placeholders are not credentials; flagging them would only teach agents to ignore the gate.
PLACEHOLDER_PATTERN = re.compile(r"(?i)(example|placeholder|changeme|your[_-]|<[^>]+>|\$\{|xxx|\*{3,}|dummy|fake|test)")

# Matched against a real comment only, and for Python only at the start of the comment text, so
# code, strings and explanatory prose that merely mention a marker are not suppressions.
# Flagging those would teach agents to ignore the gate.
PYTHON_COMMENT_SUPPRESSIONS = (
    ("python-noqa", re.compile(r"^\s*noqa\b", re.IGNORECASE)),
    ("python-type-ignore", re.compile(r"^\s*type:\s*ignore\b")),
    ("python-nosec", re.compile(r"^\s*nosec\b")),
    ("python-pylint-disable", re.compile(r"^\s*pylint:\s*disable")),
    ("python-pragma-no-cover", re.compile(r"^\s*pragma:\s*no\s+cover")),
    ("gitleaks-allow", re.compile(r"(^|\s)gitleaks:allow\b")),
)
JAVASCRIPT_COMMENT_SUPPRESSIONS = (
    ("javascript-eslint-disable", re.compile(r"eslint-disable")),
    ("typescript-ignore", re.compile(r"@ts-(ignore|expect-error|nocheck)\b")),
    ("gitleaks-allow", re.compile(r"gitleaks:allow")),
)
JAVASCRIPT_COMMENT_START = re.compile(r"(//|/\*)(.*)$")
# Configuration whose edit can loosen a check. The gate's own config is included so an agent
# cannot disable a check by editing the file that declares it.
GUARDED_CONFIG_PATTERNS = (
    GATE_CONFIG_NAME, "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini", "setup.cfg", "tox.ini",
    ".flake8", ".pylintrc", "pylintrc", ".eslintrc", ".eslintrc.*", "eslint.config.*", "tsconfig*.json",
    ".prettierrc", ".prettierrc.*", "prettier.config.*", "biome.json", ".gitleaks.toml", ".gitleaksignore",
    ".bandit", "bandit.yaml", ".coveragerc", "jest.config.*", "vitest.config.*", "pytest.ini", "conftest.py",
)
PYPROJECT_TOOL_SECTION = re.compile(r"^\+\s*\[tool\.(ruff|mypy|pylint|pytest|coverage|black|bandit)")
JAVASCRIPT_SKIP_PATTERN = re.compile(r"\b(it|test|describe)\.(skip|only)\b|\bxit\(|\bxdescribe\(")
PYTHON_SKIP_NAMES = frozenset({"skip", "skipif", "skipUnless", "skipIf", "xfail", "expectedFailure"})
ASSERTION_PATTERN = re.compile(r"\b(assert\w*|expect|should|verify)\b")
TEST_FUNCTION_PATTERN = re.compile(r"^\s*(def test_\w+|(async\s+)?function\s+test\w*|(it|test)\()")

# Names that say nothing about what they hold. `_` and conventional loop/comprehension
# indices are exempt, because the policy allows short names where they are unambiguous.
SINGLE_CHARACTER_EXEMPT = frozenset("_")
LOOP_INDEX_NAMES = frozenset("ijkn")
GENERIC_NAMES = frozenset({"data", "tmp", "temp", "val", "res", "obj", "foo", "bar", "baz", "stuff", "thing", "var"})

TOOL_INSTALL_HINTS = {
    "gitleaks": "brew install gitleaks (or see https://github.com/gitleaks/gitleaks)",
    "bandit": "pip install bandit",
}


class GateError(Exception):
    """The gate could not run; this is not a finding about the change."""


def run(command, cwd, timeout=None, input_text=None):
    return subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, errors="replace",
        timeout=timeout, input=input_text,
    )


def git(arguments, cwd):
    result = run(["git", *arguments], cwd)
    if result.returncode != 0:
        raise GateError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def repository_root(start):
    return Path(git(["rev-parse", "--show-toplevel"], start).strip())


def changed_paths(root, base):
    """Changed and untracked paths against base, excluding the factory's own state."""
    tracked = git(["diff", "--name-only", "-z", base], root).split("\0")
    untracked = git(["ls-files", "--others", "--exclude-standard", "-z"], root).split("\0")
    return sorted({path for path in tracked + untracked if path and not path.startswith(".factory/")})


def added_lines(root, base, paths):
    """Map path -> [(line_number, text)] for lines added relative to base.

    Untracked files are entirely new, so every line counts as added. Binary files and
    deletions contribute nothing.
    """
    result = {}
    tracked = set(git(["ls-files", "-z"], root).split("\0"))
    for path in paths:
        full = root / path
        if path not in tracked:
            if full.is_file():
                try:
                    text = full.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                result[path] = list(enumerate(text.splitlines(), start=1))
            continue
        diff = run(["git", "diff", "--unified=0", "--no-color", base, "--", path], root).stdout
        lines = []
        line_number = 0
        for raw in diff.splitlines():
            hunk = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if hunk:
                line_number = int(hunk.group(1))
            elif raw.startswith("+") and not raw.startswith("+++"):
                lines.append((line_number, raw[1:]))
                line_number += 1
        if lines:
            result[path] = lines
    return result


def removed_lines(root, base, paths):
    """Map path -> [text] for lines removed relative to base (tracked files only)."""
    result = {}
    for path in paths:
        diff = run(["git", "diff", "--unified=0", "--no-color", base, "--", path], root).stdout
        lines = [raw[1:] for raw in diff.splitlines() if raw.startswith("-") and not raw.startswith("---")]
        if lines:
            result[path] = lines
    return result


def finding_id(rule, path, line, detail=""):
    """Stable across runs so a human's acceptance of a tamper entry keeps applying."""
    digest = hashlib.sha256(f"{rule}|{path}|{detail}".encode("utf-8")).hexdigest()[:10]
    return f"{rule}-{digest}"


def is_test_path(path):
    return bool(TEST_PATH_PATTERN.search(path))


def guarded_config(path):
    name = Path(path).name
    return any(fnmatch.fnmatch(name, pattern) for pattern in GUARDED_CONFIG_PATTERNS)


def banner_findings(added):
    findings = []
    for path, lines in added.items():
        if not path.endswith(CODE_SUFFIXES):
            continue
        for line_number, text in lines:
            if BANNER_PATTERN.match(text) or BANNER_TITLE_PATTERN.match(text):
                findings.append({"rule": "comment-banner", "file": path, "line": line_number,
                                 "message": "Decorative comment banner; remove it or explain why in a normal comment."})
    return findings


def secret_findings(added):
    findings = []
    for path, lines in added.items():
        for line_number, text in lines:
            if PLACEHOLDER_PATTERN.search(text):
                continue
            for rule, pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    # Only the rule name is recorded: the matched text must never be reproduced.
                    findings.append({"rule": f"secret-{rule}", "file": path, "line": line_number,
                                     "message": "Secret-shaped literal. Remove it and rotate the credential if it was real."})
                    break
    return findings


def swallowed_error_findings(root, added):
    """Empty or pass-only exception handlers, which hide failures (engineering-policy.md)."""
    findings = []
    for path, lines in added.items():
        added_numbers = {number for number, _ in lines}
        if path.endswith(PYTHON_SUFFIXES):
            findings += _python_swallowed(root / path, path, added_numbers)
        elif path.endswith(JAVASCRIPT_SUFFIXES):
            findings += _javascript_swallowed(lines, path)
    return findings


def _python_swallowed(full_path, path, added_numbers):
    try:
        tree = ast.parse(full_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.lineno not in added_numbers:
            continue
        only_ignores = all(
            isinstance(statement, ast.Pass)
            or (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
            for statement in node.body
        )
        if only_ignores:
            findings.append({"rule": "swallowed-error", "file": path, "line": node.lineno,
                             "message": "Exception handler does nothing; handle, log or re-raise the error."})
    return findings


def _javascript_swallowed(lines, path):
    text = "\n".join(line_text for _, line_text in lines)
    findings = []
    for match in re.finditer(r"catch\s*(\([^)]*\))?\s*\{\s*\}", text):
        line_number = lines[text[:match.start()].count("\n")][0]
        findings.append({"rule": "swallowed-error", "file": path, "line": line_number,
                         "message": "Empty catch block; handle, log or re-throw the error."})
    return findings


def weakened_test_findings(root, paths, added, removed):
    """Deleted or loosened tests. Every one is a tamper entry: only a human may accept it."""
    entries = []
    for path in paths:
        if not is_test_path(path):
            continue
        for line_number in skipped_test_lines(root, path, added.get(path, [])):
            entries.append(_tamper("skipped-test", path, line_number,
                                   "Test is skipped or focused; it no longer runs with the suite."))
        removed_here = removed.get(path, [])
        added_assertions = sum(1 for _, text in added.get(path, []) if ASSERTION_PATTERN.search(text))
        removed_assertions = sum(1 for text in removed_here if ASSERTION_PATTERN.search(text))
        if removed_assertions > added_assertions:
            entries.append(_tamper("removed-assertions", path, 0,
                                   f"{removed_assertions - added_assertions} more assertion line(s) removed than added."))
        removed_tests = sum(1 for text in removed_here if TEST_FUNCTION_PATTERN.match(text))
        added_tests = sum(1 for _, text in added.get(path, []) if TEST_FUNCTION_PATTERN.match(text))
        if removed_tests > added_tests:
            entries.append(_tamper("deleted-tests", path, 0, f"{removed_tests - added_tests} test(s) removed."))
    return entries


def skipped_test_lines(root, path, added_lines_for_path):
    """Line numbers where the change added a skip, xfail or focus marker to a test.

    Python goes through the AST so a fixture string that merely contains "@pytest.mark.skip"
    is not mistaken for a skipped test; JS/TS is matched on the line (decision D25).
    """
    if path.endswith(JAVASCRIPT_SUFFIXES):
        return [number for number, text in added_lines_for_path if JAVASCRIPT_SKIP_PATTERN.search(text)]
    if not path.endswith(PYTHON_SUFFIXES):
        return []
    added_numbers = {number for number, _ in added_lines_for_path}
    try:
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    lines = set()
    for node in ast.walk(tree):
        marker = node.func if isinstance(node, ast.Call) else node
        if isinstance(marker, ast.Attribute) and marker.attr in PYTHON_SKIP_NAMES:
            if marker.lineno in added_numbers:
                lines.add(marker.lineno)
        elif isinstance(marker, ast.Name) and marker.id in PYTHON_SKIP_NAMES:
            if marker.lineno in added_numbers:
                lines.add(marker.lineno)
    return sorted(lines)


def naming_warnings(root, added):
    """Single-character and generic names. Warnings only: the policy allows short names
    where unambiguous, so the builder must justify or fix each one rather than the gate failing."""
    warnings = []
    for path, lines in added.items():
        if not path.endswith(PYTHON_SUFFIXES):
            continue
        added_numbers = {number for number, _ in lines}
        try:
            tree = ast.parse((root / path).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        loop_targets = _loop_and_comprehension_targets(tree)
        for node in ast.walk(tree):
            names = _bound_names(node)
            for name, line_number in names:
                if line_number not in added_numbers or id(node) in loop_targets:
                    continue
                if name in SINGLE_CHARACTER_EXEMPT:
                    continue
                if len(name) == 1 and name not in LOOP_INDEX_NAMES:
                    rule = "single-character-name"
                elif name.lower() in GENERIC_NAMES:
                    rule = "generic-name"
                else:
                    continue
                warnings.append({"id": finding_id(rule, path, line_number, name), "rule": rule, "file": path,
                                 "line": line_number, "name": name,
                                 "message": f"Name '{name}' does not say what it holds; rename it or justify it in build.md."})
    return warnings


def _loop_and_comprehension_targets(tree):
    """Nodes that bind a loop or comprehension variable, where short names are conventional."""
    targets = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)):
            targets.update(id(child) for child in ast.walk(node.target))
        elif isinstance(node, ast.comprehension):
            targets.update(id(child) for child in ast.walk(node.target))
    return targets


def _bound_names(node):
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return [(node.id, node.lineno)]
    if isinstance(node, ast.arg):
        return [(node.arg, node.lineno)]
    return []


def _tamper(rule, path, line, message):
    return {"id": finding_id(rule, path, line, message if line == 0 else ""), "rule": rule, "file": path,
            "line": line, "message": message}


def python_comment_lines(full_path):
    """Map line number -> comment text for real comment tokens, ignoring strings and code."""
    try:
        source = full_path.read_text(encoding="utf-8")
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError, OSError):
        return {}
    return {token.start[0]: token.string.lstrip("#") for token in tokens if token.type == tokenize.COMMENT}


def suppression_entries(root, added):
    """Suppression comments the change added, found only inside real comments."""
    entries = []
    for path, lines in added.items():
        if path.endswith(PYTHON_SUFFIXES):
            comments = python_comment_lines(root / path)
            candidates = [(number, comments[number]) for number, _ in lines if number in comments]
            patterns = PYTHON_COMMENT_SUPPRESSIONS
        elif path.endswith(JAVASCRIPT_SUFFIXES):
            candidates = []
            for number, text in lines:
                match = JAVASCRIPT_COMMENT_START.search(text)
                if match:
                    candidates.append((number, match.group(2)))
            patterns = JAVASCRIPT_COMMENT_SUPPRESSIONS
        else:
            continue
        for line_number, comment in candidates:
            for rule, pattern in patterns:
                if pattern.search(comment):
                    entries.append(_tamper(f"suppression-{rule}", path, line_number,
                                           "Suppression comment added; fix the underlying finding instead."))
    return entries


def tamper_entries(root, paths, added):
    """Moves that loosen a check. They need a human's acceptance, never the builder's."""
    entries = suppression_entries(root, added)
    for path in paths:
        if guarded_config(path):
            entries.append(_tamper("config-edit", path, 0, "Linter, scanner, type or gate configuration changed."))
        elif Path(path).name == "pyproject.toml" and any(
            PYPROJECT_TOOL_SECTION.match(f"+{text}") for _, text in added.get(path, [])
        ):
            entries.append(_tamper("config-edit", path, 0, "Tool configuration in pyproject.toml changed."))
    return entries


def load_gate_config(root):
    path = root / GATE_CONFIG_NAME
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise GateError(f"{GATE_CONFIG_NAME} is not valid JSON: {error}") from error
    if not isinstance(config, dict) or not isinstance(config.get("checks", {}), dict):
        raise GateError(f"{GATE_CONFIG_NAME} must be an object with a 'checks' object")
    if not isinstance(config.get("suffixes", {}), dict):
        raise GateError(f"{GATE_CONFIG_NAME}: 'suffixes' must map a check name to a list of file suffixes")
    return config


def tail(text):
    return text[-OUTPUT_TAIL_CHARACTERS:]


def expand_changed(command, changed, suffixes):
    """Replace the literal argument {changed} with the changed files that still exist.

    Lint and format commands should set it so existing debt in files the builder never touched
    cannot fail the job. Type and test commands leave it out: a change can break them anywhere.
    `suffixes` (from the check's "suffixes" setting) keeps files the tool cannot read out of
    its arguments; ruff, for one, would parse package.json as Python.
    Returns None when the command is scoped to changed files and none are left to check.
    """
    if "{changed}" not in command:
        return command
    if suffixes:
        changed = [path for path in changed if path.endswith(tuple(suffixes))]
    if not changed:
        return None
    expanded = []
    for part in command:
        expanded.extend(changed if part == "{changed}" else [part])
    return expanded


def run_declared_checks(root, config, changed_files):
    """Run the repository's own lint/format/type/test commands, exactly as declared."""
    results = []
    declared = config.get("checks", {})
    suffixes_by_check = config.get("suffixes", {})
    for name in ("lint", "format", "types", "test"):
        command = declared.get(name)
        if not command:
            results.append({"name": name, "status": "not_configured",
                            "message": f"No '{name}' command declared in {GATE_CONFIG_NAME}."})
            continue
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise GateError(f"{GATE_CONFIG_NAME}: checks.{name} must be a list of strings (an argv, no shell)")
        command = expand_changed(command, changed_files, suffixes_by_check.get(name))
        if command is None:
            results.append({"name": name, "status": "not_configured",
                            "message": "Scoped to changed files, and none of them exist to check."})
            continue
        try:
            completed = run(command, root, timeout=CHECK_TIMEOUT_SECONDS)
        except FileNotFoundError:
            results.append({"name": name, "status": "fail", "command": command,
                            "message": f"Declared command not found: {command[0]}"})
            continue
        except subprocess.TimeoutExpired:
            results.append({"name": name, "status": "fail", "command": command,
                            "message": f"Timed out after {CHECK_TIMEOUT_SECONDS}s."})
            continue
        results.append({
            "name": name, "command": command, "exitCode": completed.returncode,
            "status": "pass" if completed.returncode == 0 else "fail",
            "output": tail(completed.stdout + completed.stderr) if completed.returncode else "",
        })
    return results


def run_optional_tools(root, base, paths):
    """gitleaks and bandit when installed. A missing tool warns; it never fails the gate."""
    results = []
    python_changed = [path for path in paths if path.endswith(PYTHON_SUFFIXES) and (root / path).is_file()]

    if shutil.which("gitleaks"):
        # --redact keeps matched values out of the report; the patch is streamed on stdin
        # so only the change under review is scanned, not the whole history.
        patch = run(["git", "diff", "--no-color", base], root).stdout
        completed = run(["gitleaks", "stdin", "--redact", "--no-banner", "--no-color", "--exit-code", "1"],
                        root, timeout=CHECK_TIMEOUT_SECONDS, input_text=patch)
        results.append({"name": "gitleaks", "command": ["gitleaks", "stdin"], "exitCode": completed.returncode,
                        "status": "pass" if completed.returncode == 0 else "fail",
                        "output": tail(completed.stdout + completed.stderr) if completed.returncode else ""})
    else:
        results.append(_skipped("gitleaks", "Secret scanning by gitleaks did not run."))

    if not python_changed:
        results.append({"name": "bandit", "status": "not_configured", "message": "No Python files changed."})
    elif shutil.which("bandit"):
        completed = run(["bandit", "-q", "-ll", *python_changed], root, timeout=CHECK_TIMEOUT_SECONDS)
        results.append({"name": "bandit", "command": ["bandit", "-ll"], "exitCode": completed.returncode,
                        "status": "pass" if completed.returncode == 0 else "fail",
                        "output": tail(completed.stdout + completed.stderr) if completed.returncode else ""})
    else:
        results.append(_skipped("bandit", "Python static security analysis did not run."))
    return results


def _skipped(tool, consequence):
    return {"name": tool, "status": "skipped",
            "message": f"{consequence} {tool} is not installed. Install: {TOOL_INSTALL_HINTS[tool]}"}


def accepted_ids(path):
    if not path:
        return set()
    try:
        return set(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise GateError(f"cannot read accepted tamper entries from {path}: {error}") from error


def build_report(root, base, accepted):
    paths = changed_paths(root, base)
    code_paths = [path for path in paths if path.endswith(CODE_SUFFIXES)]
    added = added_lines(root, base, paths)
    removed = removed_lines(root, base, [path for path in paths if is_test_path(path)])

    hard_findings = (
        banner_findings(added) + secret_findings(added) + swallowed_error_findings(root, added)
    )
    for finding in hard_findings:
        finding["id"] = finding_id(finding["rule"], finding["file"], finding["line"], finding["message"])

    tamper = tamper_entries(root, paths, added) + weakened_test_findings(root, paths, added, removed)
    for entry in tamper:
        entry["accepted"] = entry["id"] in accepted
    warnings = naming_warnings(root, {path: lines for path, lines in added.items() if path in code_paths})

    config = load_gate_config(root)
    existing_changed = [path for path in paths if (root / path).is_file()]
    checks = run_declared_checks(root, config, existing_changed) + run_optional_tools(root, base, paths)
    failed_checks = [check["name"] for check in checks if check["status"] == "fail"]
    unresolved_tamper = [entry["id"] for entry in tamper if not entry["accepted"]]
    skipped_tools = [check["name"] for check in checks if check["status"] == "skipped"]

    failed = bool(hard_findings or failed_checks or unresolved_tamper)
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "status": "fail" if failed else ("warn" if warnings or skipped_tools else "pass"),
        "base": base,
        "changedFiles": paths,
        "findings": hard_findings,
        "tamper": tamper,
        "warnings": warnings,
        "checks": checks,
        "summary": {
            "findings": len(hard_findings),
            "failedChecks": failed_checks,
            "unresolvedTamper": unresolved_tamper,
            "skippedTools": skipped_tools,
            "warnings": len(warnings),
        },
        "instructions": (
            "Fix every finding and failed check at its cause. Do not add suppression comments, edit "
            "linter/scanner/gate configuration, or weaken tests to make this pass; those moves are listed "
            "under 'tamper' and only the human can accept them."
        ),
    }


def build_parser():
    parser = argparse.ArgumentParser(description="Engineering Guard quality gate.")
    parser.add_argument("--base", default="HEAD", help="Git ref the change is measured against (default HEAD).")
    parser.add_argument("--accepted", help="JSON file listing tamper entry ids the human accepted.")
    parser.add_argument("--output", help="Also write the JSON report to this path.")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    try:
        root = repository_root(Path.cwd())
        report = build_report(root, arguments.base, accepted_ids(arguments.accepted))
    except GateError as error:
        print(json.dumps({"schemaVersion": REPORT_SCHEMA_VERSION, "status": "error", "error": str(error)}, indent=2))
        return 2
    text = json.dumps(report, indent=2)
    if arguments.output:
        Path(arguments.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
