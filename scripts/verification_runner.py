import json
import os
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
CLEANUP_TIMEOUT_SECONDS = 5
TERMINATE_GRACE_SECONDS = 1
POLL_INTERVAL_SECONDS = 0.01
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


def _process_group_state(process_group_id):
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return "absent"
    except PermissionError:
        return "present"
    except OSError:
        return "unknown"
    return "present"


def _signal_process_group(process_group_id, requested_signal):
    try:
        os.killpg(process_group_id, requested_signal)
    except ProcessLookupError:
        return "absent"
    except OSError:
        return "failed"
    return "sent"


def _run_npm_script(root, name):
    interruption = {"signal": None}

    def remember_interruption(signum, _frame):
        if interruption["signal"] is None:
            interruption["signal"] = signum

    previous_handlers = {}
    try:
        # The child has its own session, so runner interrupts must enter bounded cleanup explicitly.
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, remember_interruption)
        return _run_npm_script_with_interrupt_state(root, name, interruption)
    finally:
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)


def _run_npm_script_with_interrupt_state(root, name, interruption):
    command = ["npm", "run", "--ignore-scripts", name]
    started = time.monotonic()
    error = None
    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()
    overflow_streams = set()
    lock = threading.Lock()
    is_posix = os.name == "posix"
    try:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=is_posix,
        )
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
            "cleanup": {
                "status": "not_needed",
                "directProcessReaped": None,
                "outputReadersStopped": True,
                "trackedProcessGroup": "not_observable",
                "terminationRequestsSent": [],
            },
        }

    readers = [
        threading.Thread(
            target=_capture_stream,
            args=(process.stdout, stdout, overflow, overflow_streams, "stdout", lock),
            daemon=True,
        ),
        threading.Thread(
            target=_capture_stream,
            args=(process.stderr, stderr, overflow, overflow_streams, "stderr", lock),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    command_deadline = started + TIMEOUT_SECONDS
    process_group_id = process.pid if is_posix else None
    cleanup_deadline = None
    cleanup_reason = None
    termination_sent_at = None
    force_kill_sent = False
    cleanup_signal_error = None
    process_group_status = "not_observable"
    termination_requests_sent = []

    while True:
        now = time.monotonic()
        return_code = process.poll()
        readers_stopped = all(not reader.is_alive() for reader in readers)

        if interruption["signal"] is not None and cleanup_deadline is None:
            signal_name = signal.Signals(interruption["signal"]).name
            error = {"code": "EINTR", "message": f"Command interrupted by {signal_name}"}
            cleanup_reason = "interrupted"
        elif overflow.is_set() and error is None:
            streams = ", ".join(sorted(overflow_streams))
            error = {"code": "ERR_CHILD_PROCESS_STDIO_MAXBUFFER", "message": f"{streams} exceeded the 2 MB capture limit"}
            cleanup_reason = "output_limit"
        elif return_code is None and now >= command_deadline and cleanup_deadline is None:
            error = {"code": "ETIMEDOUT", "message": f"Command timed out after {TIMEOUT_SECONDS} seconds"}
            cleanup_reason = "timeout"

        if cleanup_deadline is None and return_code is not None:
            if is_posix:
                process_group_status = _process_group_state(process_group_id)
                if process_group_status != "absent":
                    cleanup_reason = "remaining_process_group"
            if cleanup_reason is None and not readers_stopped:
                cleanup_reason = "reader_drain"
            if cleanup_reason is None:
                break

        if cleanup_reason is not None and cleanup_deadline is None:
            cleanup_deadline = now + CLEANUP_TIMEOUT_SECONDS
            if is_posix:
                process_group_status = _process_group_state(process_group_id)
                if process_group_status != "absent":
                    termination_result = _signal_process_group(process_group_id, signal.SIGTERM)
                    termination_sent_at = now
                    if termination_result == "sent":
                        termination_requests_sent.append("SIGTERM")
                    if termination_result == "failed":
                        cleanup_signal_error = "Could not send SIGTERM to the tracked process group"
            elif return_code is None:
                # shortcut: Windows stops only npm directly; add Job Object containment after Windows integration tests exist.
                try:
                    process.kill()
                    termination_requests_sent.append("process.kill")
                except OSError as exception:
                    cleanup_signal_error = str(exception)

        if cleanup_deadline is not None:
            now = time.monotonic()
            return_code = process.poll()
            readers_stopped = all(not reader.is_alive() for reader in readers)

            if is_posix:
                process_group_status = _process_group_state(process_group_id)
                if (
                    termination_sent_at is not None
                    and not force_kill_sent
                    and now >= termination_sent_at + min(TERMINATE_GRACE_SECONDS, CLEANUP_TIMEOUT_SECONDS / 2)
                    and now < cleanup_deadline
                    and process_group_status != "absent"
                ):
                    kill_result = _signal_process_group(process_group_id, signal.SIGKILL)
                    force_kill_sent = True
                    if kill_result == "sent":
                        termination_requests_sent.append("SIGKILL")
                    if kill_result == "failed":
                        cleanup_signal_error = "Could not send SIGKILL to the tracked process group"

                if return_code is not None and readers_stopped and process_group_status == "absent":
                    break
            elif return_code is not None and readers_stopped:
                break

            remaining = cleanup_deadline - time.monotonic()
            if remaining <= 0:
                break

            for reader in readers:
                remaining = cleanup_deadline - time.monotonic()
                if remaining <= 0:
                    break
                if reader.is_alive():
                    reader.join(timeout=min(POLL_INTERVAL_SECONDS, remaining))
            remaining = cleanup_deadline - time.monotonic()
            if remaining > 0 and all(reader.is_alive() for reader in readers):
                time.sleep(min(POLL_INTERVAL_SECONDS, remaining))
        else:
            time.sleep(POLL_INTERVAL_SECONDS)

    return_code = process.poll()
    direct_process_reaped = return_code is not None
    readers_stopped = all(not reader.is_alive() for reader in readers)
    if is_posix:
        process_group_status = _process_group_state(process_group_id)

    if cleanup_deadline is None:
        cleanup_status = "not_needed"
    elif is_posix:
        if not direct_process_reaped or not readers_stopped or process_group_status == "present":
            cleanup_status = "incomplete"
        elif process_group_status == "absent":
            cleanup_status = "complete"
        else:
            cleanup_status = "uncertain"
    elif not direct_process_reaped or not readers_stopped:
        cleanup_status = "incomplete"
    else:
        cleanup_status = "uncertain"

    cleanup = {
        "status": cleanup_status,
        "directProcessReaped": direct_process_reaped,
        "outputReadersStopped": readers_stopped,
        "trackedProcessGroup": process_group_status,
        "terminationRequestsSent": termination_requests_sent,
    }
    if cleanup_signal_error:
        cleanup["error"] = cleanup_signal_error

    exit_code = return_code if return_code is not None and return_code >= 0 else None
    signal_name = signal.Signals(-return_code).name if return_code is not None and return_code < 0 else None
    if readers_stopped:
        trimmed_stdout = trim_output(stdout.decode("utf-8", "replace"))
        trimmed_stderr = trim_output(stderr.decode("utf-8", "replace"))
        stdout_text = trimmed_stdout["text"]
        stderr_text = trimmed_stderr["text"]
        output_truncated = trimmed_stdout["truncated"] or trimmed_stderr["truncated"]
    else:
        stdout_text = ""
        stderr_text = ""
        output_truncated = True
    return {
        "command": "npm run --ignore-scripts " + name,
        "exitCode": exit_code,
        "signal": signal_name,
        "durationMs": int((time.monotonic() - started) * 1000),
        "error": error,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "outputTruncated": output_truncated,
        "cleanup": cleanup,
    }


def execute_script(root, name, script, repository_fingerprint):
    result = _run_npm_script(root, name)
    command_passed = result["error"] is None and result["exitCode"] == 0
    check_passed = command_passed and result["cleanup"]["status"] in ("not_needed", "complete")
    return {
        "name": name,
        "configuredCommand": script,
        **result,
        "repositoryFingerprint": repository_fingerprint,
        "commandOutcome": "passed" if command_passed else "failed",
        "outcome": "passed" if check_passed else "failed",
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
    cleanup_unresolved = any(check["cleanup"]["status"] in ("incomplete", "uncertain") for check in executed)
    after = snapshot(root) if selected and not cleanup_unresolved else (before if not selected else None)
    unchanged_during_checks = before == after if selected and not cleanup_unresolved else None
    all_passed = bool(executed) and all(check["outcome"] == "passed" for check in executed)

    status = "inventory_only"
    exit_code = 0
    if unavailable:
        status, exit_code = "selection_error", 2
    elif cleanup_unresolved:
        status, exit_code = "checks_failed", 1
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
                f"After timeout, output overflow, runner SIGINT/SIGTERM, or incomplete process/output shutdown, termination and reader shutdown share one {CLEANUP_TIMEOUT_SECONDS}-second monotonic deadline. Each selected command can take up to its command timeout plus this cleanup budget.",
                "Cleanup status describes observed scope: not_needed means cleanup was not triggered; on POSIX, complete means the direct process was reaped, readers stopped, and the tracked process group was absent. Neither establishes that descendants outside the group have terminated. Windows cleanup is best effort, and descendant termination is unconfirmed after a cleanup attempt.",
                "If cleanup is incomplete or uncertain, the after-snapshot is omitted and unchangedDuringChecks is null.",
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
