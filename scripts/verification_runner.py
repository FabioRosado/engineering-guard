import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


SNAPSHOT_SCRIPT = Path(__file__).resolve().with_name("verification_snapshot.py")
OUTPUT_LIMIT = 20_000
BUFFER_LIMIT = 2 * 1024 * 1024
TIMEOUT_SECONDS = 120
COVERAGE_PATHS = (
    "coverage/coverage-summary.json",
    "coverage/coverage-final.json",
    "coverage/lcov.info",
    "coverage.xml",
    "target/site/jacoco/jacoco.xml",
    ".nyc_output/coverage.json",
)
HELP = """Usage: python3 scripts/verification_runner.py [--base <git-ref>] [--run <npm-script> ...]

Inventory the current repository and available package scripts without executing checks.
Pass --run once per existing npm script to execute selected checks explicitly.
Use --base to compare the current worktree against another commit or ref; defaults to HEAD.
The JSON evidence report is printed to stdout and is not saved in the repository."""


def git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="surrogateescape")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def parse_arguments(args):
    parsed = {"base": None, "base_specified": False, "requested": [], "help": False}
    index = 0
    while index < len(args):
        argument = args[index]
        if argument in ("--help", "-h"):
            parsed["help"] = True
        elif argument == "--base":
            if parsed["base_specified"] or index + 1 >= len(args) or not args[index + 1] or args[index + 1].startswith("-"):
                raise ValueError("--base requires one Git commit or ref")
            parsed["base"] = args[index + 1]
            parsed["base_specified"] = True
            index += 1
        elif argument == "--run":
            if index + 1 >= len(args) or not args[index + 1] or args[index + 1].startswith("-"):
                raise ValueError("--run requires an existing npm script name")
            parsed["requested"].append(args[index + 1])
            index += 1
        else:
            raise ValueError(f"Unknown option: {argument}")
        index += 1
    parsed["requested"] = list(dict.fromkeys(parsed["requested"]))
    return parsed


def repository_root(cwd):
    return Path(git(["rev-parse", "--show-toplevel"], cwd).strip())


def commit_at(root, ref):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=root, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise ValueError(f"Git baseline does not resolve to a commit: {ref}")
    return result.stdout.strip()


def current_head(root):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"], cwd=root, capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    if result.returncode == 1:
        return None
    raise RuntimeError(result.stderr.strip() or "Could not read Git HEAD")


def changed_files(root, baseline):
    files = {}
    if baseline:
        entries = [entry for entry in git(["diff", "--no-ext-diff", "--no-renames", "--name-status", "-z", baseline, "--"], root).split("\0") if entry]
        for index in range(0, len(entries), 2):
            files[entries[index + 1]] = entries[index]
    else:
        entries = [entry for entry in git(["status", "--porcelain=v1", "--no-renames", "--untracked-files=all", "-z"], root).split("\0") if entry]
        for entry in entries:
            files[entry[3:]] = entry[:2].strip() or "??"

    untracked = [path for path in git(["ls-files", "--others", "--exclude-standard", "-z"], root).split("\0") if path]
    for path in untracked:
        files[path] = "??"
    return [{"path": path, "status": files[path]} for path in sorted(files)]


def snapshot(root):
    result = subprocess.run(
        [sys.executable, str(SNAPSHOT_SCRIPT)], cwd=root, capture_output=True, text=True, errors="replace", timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not capture repository snapshot")
    return json.loads(result.stdout)["fingerprint"]


def package_scripts(root):
    package_path = root / "package.json"
    if not package_path.exists():
        return {}
    package_json = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = package_json.get("scripts") if isinstance(package_json, dict) else None
    return scripts if isinstance(scripts, dict) else {}


def trim_output(value):
    return {"text": value[:OUTPUT_LIMIT], "truncated": len(value) > OUTPUT_LIMIT}


def _capture_stream(stream, captured, overflow, overflow_streams, stream_name, lock):
    while True:
        chunk = stream.read(65_536)
        if not chunk:
            return
        remaining = BUFFER_LIMIT - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
        if len(chunk) > remaining:
            with lock:
                overflow_streams.add(stream_name)
            overflow.set()


def _run_npm_script(root, name):
    command = ["npm", "run", "--ignore-scripts", name]
    started = time.monotonic()
    error = None
    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()
    overflow_streams = set()
    lock = threading.Lock()
    try:
        process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exception:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "command": "npm run --ignore-scripts " + name,
            "exitCode": None,
            "signal": None,
            "durationMs": duration_ms,
            "error": {"code": getattr(exception, "errno", None), "message": str(exception)},
            "stdout": "",
            "stderr": "",
            "outputTruncated": False,
        }

    readers = [
        threading.Thread(target=_capture_stream, args=(process.stdout, stdout, overflow, overflow_streams, "stdout", lock)),
        threading.Thread(target=_capture_stream, args=(process.stderr, stderr, overflow, overflow_streams, "stderr", lock)),
    ]
    for reader in readers:
        reader.start()

    deadline = started + TIMEOUT_SECONDS
    while process.poll() is None:
        if overflow.is_set():
            streams = ", ".join(sorted(overflow_streams))
            error = {"code": "ERR_CHILD_PROCESS_STDIO_MAXBUFFER", "message": f"{streams} exceeded the 2 MB capture limit"}
            process.kill()
            break
        if time.monotonic() >= deadline:
            error = {"code": "ETIMEDOUT", "message": f"Command timed out after {TIMEOUT_SECONDS} seconds"}
            process.kill()
            break
        time.sleep(0.01)

    process.wait()
    for reader in readers:
        reader.join()
    if overflow.is_set() and error is None:
        streams = ", ".join(sorted(overflow_streams))
        error = {"code": "ERR_CHILD_PROCESS_STDIO_MAXBUFFER", "message": f"{streams} exceeded the 2 MB capture limit"}

    return_code = process.returncode
    exit_code = return_code if return_code >= 0 else None
    signal_name = signal.Signals(-return_code).name if return_code < 0 else None
    stdout_text = stdout.decode("utf-8", "replace")
    stderr_text = stderr.decode("utf-8", "replace")
    trimmed_stdout = trim_output(stdout_text)
    trimmed_stderr = trim_output(stderr_text)
    return {
        "command": "npm run --ignore-scripts " + name,
        "exitCode": exit_code,
        "signal": signal_name,
        "durationMs": int((time.monotonic() - started) * 1000),
        "error": error,
        "stdout": trimmed_stdout["text"],
        "stderr": trimmed_stderr["text"],
        "outputTruncated": trimmed_stdout["truncated"] or trimmed_stderr["truncated"],
    }


def execute_script(root, name, script, repository_fingerprint):
    result = _run_npm_script(root, name)
    passed = result["error"] is None and result["exitCode"] == 0
    return {
        "name": name,
        "configuredCommand": script,
        **result,
        "repositoryFingerprint": repository_fingerprint,
        "outcome": "passed" if passed else "failed",
    }


def available_coverage(root):
    coverage = []
    for relative_path in COVERAGE_PATHS:
        path = root / relative_path
        if path.exists() and path.is_file():
            coverage.append({"path": relative_path, "sizeBytes": path.stat().st_size})
    return coverage


def build_report(root, options):
    head = current_head(root)
    baseline = commit_at(root, options["base"]) if options["base_specified"] else head
    scripts = package_scripts(root)
    available = [{"name": name, "command": command} for name, command in scripts.items()]
    unavailable = [name for name in options["requested"] if name not in scripts]
    selected = [] if unavailable else options["requested"]
    changed = changed_files(root, baseline)
    before = snapshot(root)
    executed = []
    for name in selected:
        check = execute_script(root, name, scripts[name], before)
        executed.append(check)
    after = snapshot(root) if selected else before
    unchanged_during_checks = before == after if selected else None
    all_passed = bool(executed) and all(check["outcome"] == "passed" for check in executed)

    status = "inventory_only"
    exit_code = 0
    if unavailable:
        status, exit_code = "selection_error", 2
    elif executed and not unchanged_during_checks:
        status, exit_code = "snapshot_changed", 1
    elif any(check["outcome"] != "passed" for check in executed):
        status, exit_code = "checks_failed", 1
    elif executed:
        status = "checks_passed"

    return {
        "report": {
            "schemaVersion": 1,
            "status": status,
            "assessment": "execution_evidence_only",
            "repository": {
                "root": str(root),
                "head": head,
                "baseline": baseline or "unborn repository",
                "changedFiles": changed,
                "diffStat": git(["diff", "--no-ext-diff", "--stat", baseline, "--"], root).strip() if baseline else None,
                "snapshot": {"before": before, "after": after, "unchangedDuringChecks": unchanged_during_checks},
            },
            "checks": {
                "availableScripts": available,
                "requested": options["requested"],
                "executed": executed,
                "notRequested": [item["name"] for item in available if item["name"] not in options["requested"]],
                "unavailable": unavailable,
                "allPassed": all_passed if executed else None,
            },
            "coverageEvidence": available_coverage(root),
            "limitations": [
                "The runner records command execution; it does not assess source correctness, test quality, architecture, or security.",
                "Only explicitly selected root npm scripts run; npm pre/post lifecycle scripts are disabled, but selected scripts may invoke other commands or have side effects.",
                "Coverage artifacts are listed by common path and are not interpreted.",
                "Command output may contain sensitive data, is truncated at 20,000 characters per stream, and is printed to stdout only.",
                "Commands have a 120-second timeout and 2 MB capture buffer; inspect error and truncation fields.",
                "The diff is summarized by changed paths and Git stat; inspect the actual patch separately.",
            ],
        },
        "exit_code": exit_code,
    }


def main(args):
    options = parse_arguments(args)
    if options["help"]:
        print(HELP)
        return 0
    root = repository_root(Path.cwd())
    result = build_report(root, options)
    print(json.dumps(result["report"], indent=2, ensure_ascii=False))
    return result["exit_code"]


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as error:
        print(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "status": "error",
                    "assessment": "execution_evidence_only",
                    "error": str(error),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        sys.exit(2)
