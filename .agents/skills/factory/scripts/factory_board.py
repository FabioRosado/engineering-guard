"""State machine and only writer of .factory/board.json for the Engineering Guard factory.

The orchestrator (whichever agent session runs the factory skill) calls this script
instead of editing board.json by hand. Every command validates the job files the
agents were expected to write, so the loop rules live in one tested place:

  spec -> spec-review -(human approve-spec)-> build -> test-audit -> review -> build ...
       -> stride-review -> quality-gate -> approver -> needs-human

Run from anywhere inside the target Git repository. Output is JSON on stdout; a
rule violation exits 2 with {"error": ...} so the orchestrator can react.
"""

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
QUALITY_GATE_SCRIPT = SKILL_ROOT / "scripts" / "quality_gate.py"
PRESETS_FILE = SKILL_ROOT / "presets.json"
ROLES_DIRECTORY = SKILL_ROOT / "roles"

FACTORY_DIRECTORY_NAME = ".factory"
REVIEWERS = ("security", "ux", "ui", "code", "architecture")
# Only UX, UI and architecture can be "not applicable": every change has code and a security
# surface, so N/A from those reviewers would let a round pass with nothing reviewed. A small
# fix has no architecture to compare, so architecture may be N/A (decision D36).
# BLOCKED means the reviewer could not assess the change at all (decision D46). It is distinct
# from CHANGES, which asks the builder to fix something: a blocked review has nothing for the
# builder to act on, so the job goes to the human, as a blocked builder does.
ALLOWED_VERDICTS = {
    "tests": ("PASS", "CHANGES", "BLOCKED"),
    "security": ("PASS", "CHANGES", "BLOCKED"),
    "code": ("PASS", "CHANGES", "BLOCKED"),
    "ux": ("PASS", "CHANGES", "N/A", "BLOCKED"),
    "ui": ("PASS", "CHANGES", "N/A", "BLOCKED"),
    "architecture": ("PASS", "CHANGES", "N/A", "BLOCKED"),
    "stride": ("PASS", "CHANGES", "BLOCKED"),
}
# Roles whose CHANGES verdict must cite at least one CRITICAL/HIGH finding (decision
# SD1 in decisions/stride-threat-model.md): a MEDIUM/LOW/hardening-only report should
# pass with notes instead of spending a review round, because every actionable finding
# previously blocked a round regardless of severity.
SEVERITY_GATED_ROLES = {"security", "stride"}
SEVERITY_LINE = re.compile(r"^SEVERITY:\s*(CRITICAL|HIGH|MEDIUM|LOW|INFO)\s*$", re.MULTILINE)
BLOCKING_SEVERITIES = {"CRITICAL", "HIGH"}
# Per build attempt (initial build or human rework). Test-audit rebuilds have their own
# budget so weak tests cannot use up the review rounds; after either budget the job
# moves on and the approver escalates with whatever findings remain.
REVIEW_ROUNDS_PER_ATTEMPT = 2
TEST_REBUILDS_PER_ATTEMPT = 1
# The quality gate runs once per job after STRIDE (decision D27) to keep the build/test loop
# short. Fixable findings get this many extra build rounds before the job moves on to the
# approver with the remainder carried as warnings (decision D28).
GATE_FIXES_PER_ATTEMPT = 1
SPEC_STATUS_LINE = re.compile(r"^\*\*Status:\*\*.*$", re.MULTILINE)
# Anchored to the spec's own field line so a quoted draft or prose mention does not match.
UI_IMPACT_NO = re.compile(r"^\W*UI impact\W*no\b", re.IGNORECASE | re.MULTILINE)
ARCHITECTURE_IMPACT_NO = re.compile(r"^\W*Architecture impact\W*no\b", re.IGNORECASE | re.MULTILINE)
# Any line that starts with an impact label, whatever it says. The spec's own field is the first
# such line, so a later line in another section that happens to begin the same way (for example
# under "User-facing surface") must not be able to overrule it.
UI_IMPACT_LINE = re.compile(r"^\W*UI impact\b.*$", re.IGNORECASE | re.MULTILINE)
ARCHITECTURE_IMPACT_LINE = re.compile(r"^\W*Architecture impact\b.*$", re.IGNORECASE | re.MULTILINE)
# The handover is the living, builder-updated home of the diagrams: spec.md is frozen once
# approved, so it cannot track a build that changes shape (decision D33).
HANDOVER_FILE = "handover.md"
# Deliberately loose: it only decides whether a handover MIGHT hold a diagram, so a false positive
# costs one validator run and a false negative would skip validation. What actually counts as a
# diagram is decided by the validator, which uses the same markdown lexer as the dashboard; a strict
# pattern here once disagreed with it on ~~~ fences, "Mermaid", longer fences and fences in quotes.
MAYBE_DIAGRAM = re.compile(r"(```|~~~)[^\n]*mermaid", re.IGNORECASE)
DIAGRAM_VALIDATOR = SKILL_ROOT / "validator" / "check_mermaid.mjs"
DIAGRAM_VALIDATOR_TIMEOUT_SECONDS = 120
# Files whose change can affect what a user sees; any of them keeps the UI review on.
USER_FACING_SUFFIXES = (
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".js", ".jsx", ".ts", ".tsx",
    ".vue", ".svelte", ".astro", ".erb", ".jinja", ".j2", ".hbs", ".svg", ".png", ".jpg",
    ".jpeg", ".gif", ".webp", ".ico",
)
# Which file each role writes its findings into, for the cross-round ledger. Order is the
# order findings are read within a round.
FINDING_FILES = (
    ("tests", "test-audit.md"),
    ("security", "review-security.md"),
    ("ux", "review-ux.md"),
    ("ui", "review-ui.md"),
    ("code", "review-code.md"),
    ("architecture", "review-architecture.md"),
    ("stride", "review-stride.md"),
)
# The one accepted shape of a job's GitHub issue link. Mirrored by githubIssueLink in ui/src/lib/jobs.js.
GITHUB_ISSUE_URL = re.compile(
    r"https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/(?!\.{1,2}/)[A-Za-z0-9._-]{1,100}/issues/[1-9][0-9]{0,9}"
)
BLOCKED_HEADER = re.compile(r"^BLOCKED\b")
VERDICT_HEADER = re.compile(r"^VERDICT:\s*(PASS|CHANGES|N/A|BLOCKED)\s*$")
# One line per finding, written by the reviewer (decision D41). The id is assigned and reused by
# the reviewer rather than hashed from the prose: real findings are long and reworded between
# rounds, so a content hash would change every round. The id prefix names the role that raised
# it, which is how the board enforces that only that role may close it (decision D47).
FINDING_LINE = re.compile(
    r"^FINDING:\s*(?P<id>[a-z]+-\d+)\s*\|\s*"
    r"SEVERITY:\s*(?P<severity>CRITICAL|HIGH|MEDIUM|LOW|INFO)\s*\|\s*"
    r"LOCATION:\s*(?P<location>\S+)\s*\|\s*"
    r"STATUS:\s*(?P<status>open|closed|disputed)\s*$",
    re.MULTILINE,
)
# Anything starting FINDING: that FINDING_LINE rejects is reported rather than silently ignored,
# because a mistyped line would otherwise make a finding vanish from the unresolved list.
FINDING_PREFIX = re.compile(r"^FINDING:", re.MULTILINE)
DECISION_HEADER = re.compile(r"^ESCALATE\b")
TERMINAL_STAGES = ("abandoned",)
# Full ordered pipeline, including human-gate and terminal stages, for display
# surfaces (dashboards) that need every stage rather than just ACTIVE_STAGES.
# Keep in sync with ui/src/lib/jobs.js's STAGES array and HUMAN_STAGES set, and with
# decisions/central-factory-dashboard.md's documented column order — this is the
# single Python source those lists are derived from.
PIPELINE_STAGES = (
    ("spec", "Spec"),
    ("spec-review", "Spec Review"),
    ("build", "Build"),
    ("test-audit", "Test Audit"),
    ("review", "Review"),
    ("stride-review", "STRIDE"),
    ("quality-gate", "Quality Gate"),
    ("approver", "Approver"),
    ("needs-human", "Needs Human"),
    ("abandoned", "Abandoned"),
)
HUMAN_GATE_STAGES = ("spec-review", "needs-human")
SUPPORTED_CLIS = ("claude", "codex", "kilo")
STAGE_TIERS = {
    "spec": "expensive",
    "build": "expensive",
    "tests": "cheap",
    "security": "expensive",
    "ux": "cheap",
    "ui": "cheap",
    "code": "cheap",
    # Comparing a proposed architecture with the built one is structural reasoning, which
    # cheap models do poorly, so this reviewer runs on the expensive tier.
    "architecture": "expensive",
    "stride": "expensive",
    "approver": "expensive",
}
ACTIVE_STAGES = ("build", "test-audit", "review", "stride-review", "quality-gate", "approver")
# Only the builder changes the implementation; every other role writes just its report.
EDITING_ROLES = {"builder"}
ROLE_STAGES = {
    "spec-writer": "spec",
    "builder": "build",
    "test-auditor": "tests",
    "review-security": "security",
    "review-ux": "ux",
    "review-ui": "ui",
    "review-code": "code",
    "review-architecture": "architecture",
    "review-stride": "stride",
    "approver": "approver",
}
# Bind to loopback: specs and security reviews can describe unfixed vulnerabilities.
# The dashboard is the central server's Svelte app (decision D31); there is no per-repository mode.
DASHBOARD_COMMAND = "npm run dashboard"
BACKLOG_TEMPLATE = """# Factory backlog

One feature per line. `next` takes the first unchecked item.

- [ ] Example: describe a feature here
"""

# Central factory server configuration
CENTRAL_FACTORY_HOST = "127.0.0.1"
CENTRAL_FACTORY_PORT = 5173
CENTRAL_FACTORY_SYNC_PATH = "/api/jobs/sync"
CENTRAL_FACTORY_PUSH_TIMEOUT = 2  # seconds


class FactoryError(Exception):
    """A factory rule was violated; the message tells the orchestrator what is missing."""


def _collect_job_files(job_directory):
    """Collect all markdown files from a job directory with their content.
    
    Returns a dict mapping relative file paths to their content.
    """
    files = {}
    if not job_directory.exists():
        return files
    
    for file_path in sorted(job_directory.rglob("*.md")):
        try:
            relative_path = file_path.relative_to(job_directory)
            content = file_path.read_text(encoding="utf-8")
            files[str(relative_path)] = content
        except Exception as e:
            print(f"Warning: failed to read {file_path}: {e}", file=sys.stderr)
    
    return files


def _push_to_central_server(board, job, repository_root):
    """Push job state to central factory server (non-blocking).
    
    Collects all markdown files from the job directory and sends them to the
    central server at CENTRAL_FACTORY_SYNC_PATH. Network failures are logged but
    do not block factory progress (best-effort notification).
    """
    if os.environ.get("FACTORY_DISABLE_CENTRAL_SYNC"):
        # Tests and throwaway repos must not pollute the real dashboard store.
        return
    try:
        job_directory = repository_root / FACTORY_DIRECTORY_NAME / "jobs" / job["id"]
        files = _collect_job_files(job_directory)
        
        # Prepare payload: repository context + job state + markdown files
        payload = {
            "repository": Path(repository_root).name,
            "repo_path": str(repository_root),
            "worktree_path": str(repository_root),
            "job": {
                **{k: v for k, v in job.items() if k != "files"},  # Exclude old files list
                "files": files,
            },
        }
        
        body = json.dumps(payload).encode("utf-8")
        # http.client only speaks HTTP, so the push cannot be redirected to a file: or other
        # scheme the way urllib.request.urlopen could; the host and port are fixed constants.
        connection = http.client.HTTPConnection(
            CENTRAL_FACTORY_HOST, CENTRAL_FACTORY_PORT, timeout=CENTRAL_FACTORY_PUSH_TIMEOUT
        )
        try:
            connection.request(
                "POST", CENTRAL_FACTORY_SYNC_PATH, body=body, headers={"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            response.read()
            if response.status == 200:
                print(f"Central server: synced job {job['id']}", file=sys.stderr)
            else:
                print(f"Central server: sync returned {response.status}", file=sys.stderr)
        except (OSError, http.client.HTTPException) as e:
            # Non-blocking: central server unavailable or unreachable (socket.timeout is an OSError)
            print(f"Central server: push failed (will continue): {type(e).__name__}", file=sys.stderr)
        finally:
            connection.close()
    except Exception as e:
        # Catch any unexpected errors and log without blocking
        print(f"Central server: push error (will continue): {e}", file=sys.stderr)


def run_git(repository_root, *arguments):
    result = subprocess.run(
        ["git", *arguments], cwd=repository_root, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise FactoryError(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def find_repository_root():
    try:
        output = run_git(Path.cwd(), "rev-parse", "--show-toplevel")
    except FactoryError as error:
        raise FactoryError("run the factory inside a Git repository") from error
    return Path(output.strip())


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Factory:
    def __init__(self, repository_root):
        self.repository_root = repository_root
        self.directory = repository_root / FACTORY_DIRECTORY_NAME
        self.board_path = self.directory / "board.json"
        self.config_path = self.directory / "config.json"
        self.backlog_path = self.directory / "backlog.md"

    # ----- persistence -------------------------------------------------

    def ensure_initialized(self):
        """Create .factory/ and keep it out of Git without touching tracked files.

        Factory output is local developer tooling (decision D10), so it is excluded
        through .git/info/exclude rather than the target repository's .gitignore.
        """
        self.directory.mkdir(exist_ok=True)
        (self.directory / "jobs").mkdir(exist_ok=True)
        if not self.board_path.exists():
            self.write_json(self.board_path, {"jobs": []})
        if not self.backlog_path.exists():
            self.backlog_path.write_text(BACKLOG_TEMPLATE, encoding="utf-8")
        # init, models and new pass through here, and `new` is how every run starts, so a config
        # written before a stage existed is repaired before the orchestrator reads its models,
        # on any CLI, not only when install-claude runs.
        if self.config_path.exists():
            self.backfill_missing_stages(json.loads(self.config_path.read_text(encoding="utf-8")))

        git_directory = Path(run_git(self.repository_root, "rev-parse", "--git-common-dir").strip())
        if not git_directory.is_absolute():
            git_directory = self.repository_root / git_directory
        exclude_path = git_directory / "info" / "exclude"
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        entry = f"/{FACTORY_DIRECTORY_NAME}/"
        if entry not in existing.splitlines():
            separator = "" if existing.endswith("\n") or not existing else "\n"
            exclude_path.write_text(f"{existing}{separator}{entry}\n", encoding="utf-8")

    @staticmethod
    def write_json(path, data):
        # Write-then-rename so the polling dashboard never reads a half-written file.
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)

    def load_board(self):
        if not self.board_path.exists():
            raise FactoryError("factory not initialized: run `init` first")
        return json.loads(self.board_path.read_text(encoding="utf-8"))

    def find_job(self, board, job_id):
        for job in board["jobs"]:
            if job["id"] == job_id:
                # Jobs created before per-attempt budgets carried a round_limit instead.
                job.pop("round_limit", None)
                job.setdefault("attempt", new_attempt())
                # Jobs created before the stride-review stage have no field for it yet.
                job.setdefault("stride", None)
                # Jobs created before the quality gate have no gate state yet.
                job.setdefault("quality_gate", None)
                job.setdefault("accepted_tamper", {})
                job["attempt"].setdefault("gate_fixes", 0)
                return job
        raise FactoryError(f"unknown job {job_id}")

    def job_directory(self, job_id):
        return self.directory / "jobs" / job_id

    def save(self, board, job, push=True):
        """Persist the board after refreshing the job's file index for the dashboard."""
        directory = self.job_directory(job["id"])
        job["files"] = sorted(
            str(path.relative_to(directory)) for path in directory.rglob("*.md")
        )
        job["updated"] = utc_now()
        self.record_stage_event(job)
        self.write_json(self.board_path, board)
        if push:
            # Push job state to central factory server (non-blocking). The central
            # server itself archives by importing this module, and pushing from
            # inside that request would deadlock its single-threaded loop.
            _push_to_central_server(board, job, self.repository_root)

    @staticmethod
    def record_stage_event(job):
        """Append a timestamped event when the job's (stage, round) differs from the last one.

        `save` is the single place every transition passes through, so comparing here covers all
        of them without touching each stage change. The round is part of the identity because a
        rebuild re-enters a stage name the job has already visited. The dashboard derives its run
        statistics from these events (decisions/factory-workspace.md, D54); they measure when the
        board saw a transition, not how long an agent computed. A job created before events
        existed starts recording from its current stage: history the board never saw is not
        invented.
        """
        events = job.setdefault("events", [])
        if events and (events[-1]["stage"], events[-1]["round"]) == (job["stage"], job["round"]):
            return
        events.append({"stage": job["stage"], "round": job["round"], "at": job["updated"]})

    @staticmethod
    def require_stage(job, *allowed):
        if job["stage"] not in allowed:
            raise FactoryError(
                f"job {job['id']} is in stage '{job['stage']}', expected one of {list(allowed)}"
            )

    def require_file(self, job_id, relative_path):
        path = self.job_directory(job_id) / relative_path
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            raise FactoryError(f"missing or empty {path.relative_to(self.repository_root)}")
        return path

    # ----- worktree guards ---------------------------------------------

    @staticmethod
    def require_no_other_active_job(board, job_id):
        # All builds share one uncommitted worktree (decision D9), so a second active
        # job would mix its edits into the first job's review diff.
        active = [
            other["id"] for other in board["jobs"]
            if other["id"] != job_id and other["stage"] in ACTIVE_STAGES
        ]
        if active:
            raise FactoryError(f"another job is building in this worktree: {active}")

    def dirty_paths(self):
        """Uncommitted paths outside .factory/ (which is excluded from Git anyway).

        -z output keeps paths unquoted and puts a rename's source in its own entry,
        so "old -> new" never reaches the caller as one bogus path.
        """
        output = run_git(self.repository_root, "status", "--porcelain", "-z", "--untracked-files=all")
        entries = output.split("\0")
        paths = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if not entry:
                continue
            status, path = entry[:2], entry[3:]
            paths.append(path)
            if "R" in status or "C" in status:
                index += 1  # the next entry is the rename/copy source
        return [path for path in paths if not path.startswith(f"{FACTORY_DIRECTORY_NAME}/")]

    def untracked_paths(self):
        output = run_git(self.repository_root, "ls-files", "--others", "--exclude-standard", "-z")
        return [path for path in output.split("\0") if path]

    def write_change_snapshot(self, job):
        """Freeze the change under review into round-N/ so every auditor and reviewer
        sees the same diff, untracked files included, and each round leaves a record.
        """
        round_directory = self.job_directory(job["id"]) / f"round-{job['round']}"
        round_directory.mkdir(exist_ok=True)
        # Patches carry file contents in whatever encoding the repo uses, so they are
        # handled as bytes; decoding them could crash build-done on non-UTF-8 files.
        tracked_patch = subprocess.run(
            ["git", "diff", "--binary", job["base"]],
            cwd=self.repository_root, capture_output=True,
        )
        if tracked_patch.returncode != 0:
            raise FactoryError(f"git diff {job['base']} failed: {tracked_patch.stderr.decode(errors='replace').strip()}")
        patch = tracked_patch.stdout
        tracked_files = run_git(self.repository_root, "diff", "--name-only", "-z", job["base"]).split("\0")
        untracked = self.untracked_paths()
        for path in untracked:
            # --no-index exits 1 when the files differ, which is always the case here.
            result = subprocess.run(
                ["git", "diff", "--no-index", "--binary", "--", os.devnull, path],
                cwd=self.repository_root, capture_output=True,
            )
            if result.returncode not in (0, 1):
                raise FactoryError(
                    f"cannot snapshot untracked file {path}: {result.stderr.decode(errors='replace').strip()}"
                )
            patch += result.stdout
        (round_directory / "change.patch").write_bytes(patch)
        changed = sorted({path for path in tracked_files if path} | set(untracked))
        (round_directory / "files.txt").write_text("".join(f"{path}\n" for path in changed), encoding="utf-8")
        return changed

    def head(self):
        return run_git(self.repository_root, "rev-parse", "HEAD").strip()

    def head_warnings(self, job):
        # Reviewers diff the worktree against the HEAD recorded at build start; if the
        # human commits mid-job that diff silently shrinks, so surface it.
        if job.get("base") and job["base"] != self.head():
            return [f"HEAD moved since build started (base {job['base'][:12]}); review diffs may be incomplete"]
        return []

    def check_diagrams(self, job_id):
        """Return (error, warning) for the mermaid blocks in the job's handover.

        An invalid diagram is a rule violation the orchestrator must send back to the
        agent. A validator that cannot run (no Node, packages not installed, unsupported
        Node) is only a warning: the factory must keep working on machines that never
        installed the optional packages (decision D37). A handover with no hint of a
        diagram never reaches the validator, so it needs nothing installed.
        """
        handover = self.job_directory(job_id) / HANDOVER_FILE
        if not handover.is_file():
            return None, None
        if not MAYBE_DIAGRAM.search(handover.read_text(encoding="utf-8")):
            return None, None
        node = shutil.which("node")
        if node is None:
            return None, f"{HANDOVER_FILE} diagrams were not validated: node is not installed"
        try:
            result = subprocess.run(
                [node, str(DIAGRAM_VALIDATOR), str(handover)],
                capture_output=True, text=True, timeout=DIAGRAM_VALIDATOR_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return None, f"{HANDOVER_FILE} diagrams were not validated: the validator timed out"
        try:
            report = json.loads(result.stdout)
        except ValueError:
            # Not JSON means the script itself broke (for example an old Node that cannot
            # parse it), which is an unavailable validator, not evidence about the diagrams.
            detail = (result.stderr.strip().splitlines() or ["no output"])[-1]
            return None, f"{HANDOVER_FILE} diagrams were not validated: validator failed ({detail})"
        if "unavailable" in report:
            return None, f"{HANDOVER_FILE} diagrams were not validated: {report['unavailable']}"
        broken = [diagram for diagram in report["diagrams"] if not diagram["valid"]]
        if not broken:
            return None, None
        details = "; ".join(
            f"diagram {diagram['index']} (line {diagram['line']}): {diagram['error'].splitlines()[0]}"
            for diagram in broken
        )
        return f"{HANDOVER_FILE} has {len(broken)} invalid mermaid diagram(s): {details}", None

    def require_valid_diagrams(self, job_id):
        """Raise on an invalid diagram; return a warning when validation was not possible."""
        error, warning = self.check_diagrams(job_id)
        if error:
            raise FactoryError(error)
        return warning

    def handover_fingerprint(self, job_id):
        handover = self.job_directory(job_id) / HANDOVER_FILE
        if not handover.is_file():
            return None
        return hashlib.sha256(handover.read_bytes()).hexdigest()

    def stale_handover_warning(self, job, changed_files):
        """Warn when code moved on a later round but the handover did not.

        This is a staleness signal, not a claim that the diagrams are right or wrong: the
        board cannot judge content. It compares the handover's fingerprint with the one
        recorded after the previous build, so a builder that never touched it is caught
        even though the file still exists and still parses.
        """
        fingerprint = self.handover_fingerprint(job["id"])
        previous = job.get("handover_fingerprint")
        job["handover_fingerprint"] = fingerprint
        if fingerprint is None or previous is None or fingerprint != previous:
            return None
        if not changed_files:
            return None
        return (
            f"{HANDOVER_FILE} was not updated in round {job['round']} although code changed; "
            "its diagrams may no longer match the implementation"
        )

    # ----- commands -----------------------------------------------------

    def init(self):
        self.ensure_initialized()
        return {"factory": str(self.directory), "dashboard": DASHBOARD_COMMAND}

    def models(self, choice, cli):
        self.ensure_initialized()
        if cli not in SUPPORTED_CLIS:
            raise FactoryError(f"unknown cli '{cli}', expected one of {list(SUPPORTED_CLIS)}")
        presets = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        if len(choice) == 1:
            name = choice[0]
            if name not in presets:
                raise FactoryError(f"unknown preset '{name}', available: {sorted(presets)}")
            per_cli = presets[name]["models"]
            if cli not in per_cli:
                raise FactoryError(
                    f"preset '{name}' is not available on {cli}; it supports {sorted(per_cli)}"
                )
            expensive, cheap = per_cli[cli]["expensive"], per_cli[cli]["cheap"]
        elif len(choice) == 2:
            name = "custom"
            expensive, cheap = choice
        else:
            raise FactoryError("usage: models <preset> | models <expensive> <cheap>")
        tiers = {"expensive": expensive, "cheap": cheap}
        config = {
            "preset": name,
            "cli": cli,
            "expensive": expensive,
            "cheap": cheap,
            "stages": {stage: tiers[tier] for stage, tier in STAGE_TIERS.items()},
        }
        self.write_json(self.config_path, config)
        return config

    def backfill_missing_stages(self, config):
        """Add stages introduced after this config was written, using the tier models it already holds.

        `models` is the only writer of `stages`, so a config from before a new stage (for example
        architecture) lacks that key. Re-running `models` is not required for an upgrade: the stage's
        tier says which of the user's two chosen models it should use. The file is rewritten so the
        orchestrator, which reads `stages.<stage>` from it, sees the same value.
        """
        stages = config.setdefault("stages", {})
        missing = [stage for stage in STAGE_TIERS if stage not in stages]
        if not missing:
            return config
        for stage in missing:
            tier = STAGE_TIERS[stage]
            if tier not in config:
                raise FactoryError(f"model config has no '{tier}' model; run `models <preset>` again")
            stages[stage] = config[tier]
        self.write_json(self.config_path, config)
        return config

    def new(self, title, from_backlog, issue_url=None):
        self.ensure_initialized()
        if issue_url is not None and not GITHUB_ISSUE_URL.fullmatch(issue_url):
            raise FactoryError(
                "--issue must be a GitHub issue URL like https://github.com/<owner>/<repo>/issues/<number>"
            )
        if from_backlog:
            title = self.take_backlog_item()
        if not title or not title.strip():
            raise FactoryError("a feature description is required")
        board = self.load_board()
        number = max((int(job["id"].split("-", 1)[0]) for job in board["jobs"]), default=0) + 1
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-") or "job"
        job_id = f"{number:03d}-{slug}"
        self.job_directory(job_id).mkdir(parents=True)
        job = {
            "id": job_id,
            "title": title.strip(),
            "stage": "spec",
            "round": 0,
            "attempt": new_attempt(),
            "base": None,
            "test_audit": None,
            "reviews": {},
            "stride": None,
            "quality_gate": None,
            "accepted_tamper": {},
            "history": [],
            "models": {},
            "warnings": [],
            "created": utc_now(),
        }
        if issue_url is not None:
            job["issue_url"] = issue_url
        board["jobs"].append(job)
        self.save(board, job)
        return job

    def take_backlog_item(self):
        lines = self.backlog_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*[-*]\s*)\[ \]\s*(.+)$", line)
            if match:
                lines[index] = f"{match.group(1)}[x] {match.group(2)}"
                self.backlog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return match.group(2)
        raise FactoryError("backlog has no unchecked items")

    def spec_written(self, job_id):
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "spec")
        # feature.md holds the human's verbatim request; without it the spec was
        # written from the orchestrator's paraphrase, not what the human asked.
        self.require_file(job_id, "feature.md")
        self.require_file(job_id, "prompt.md")
        self.require_file(job_id, "spec.md")
        # Validated before the stage moves, so a broken proposal diagram never reaches the human.
        diagram_warning = self.require_valid_diagrams(job_id)
        job["warnings"] = [diagram_warning] if diagram_warning else []
        job["stage"] = "spec-review"
        self.save(board, job)
        return job

    def spec_feedback(self, job_id, note):
        """Persist human spec feedback as a file, because agents read files, not the chat."""
        if not note.strip():
            raise FactoryError("spec-feedback needs a note for the spec-writer")
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "spec-review")
        directory = self.job_directory(job_id)
        number = len(list(directory.glob("spec-feedback-*.md"))) + 1
        path = directory / f"spec-feedback-{number}.md"
        path.write_text(f"# Human spec feedback {number}\n\n{note.strip()}\n", encoding="utf-8")
        job["stage"] = "spec"
        self.save(board, job)
        return {"job": job, "feedback": str(path.relative_to(self.repository_root))}

    def approve_spec(self, job_id):
        """Human gate (D6). Also the point where the build baseline is fixed (D9)."""
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "spec-review")
        dirty = self.dirty_paths()
        if dirty:
            raise FactoryError(
                "worktree has uncommitted changes outside .factory/; commit or stash them "
                f"so reviewers only see factory work: {dirty[:10]}"
            )
        self.require_no_other_active_job(board, job_id)
        self.mark_spec_approved(job_id)
        job["base"] = self.head()
        job["stage"] = "build"
        job["round"] = 1
        job["attempt"] = new_attempt()
        self.save(board, job)
        return job

    def mark_spec_approved(self, job_id):
        """Record the human's approval inside spec.md itself.

        Builders apply the implement skill, which treats a "Proposed" spec as
        unapproved and refuses to build. Agents read files, not the board, so the
        approval must be visible in the file they are given.
        """
        path = self.require_file(job_id, "spec.md")
        text = path.read_text(encoding="utf-8")
        approved = f"**Status:** Approved by the human via `approve-spec` on {utc_now()} — ready to implement"
        if SPEC_STATUS_LINE.search(text):
            text = SPEC_STATUS_LINE.sub(lambda _: approved, text, count=1)
        else:
            text = f"{approved}\n\n{text}"
        path.write_text(text, encoding="utf-8")

    def build_done(self, job_id):
        """Hand a build to the test audit, unless the builder produced nothing.

        A builder that cannot proceed writes build.md starting with BLOCKED; the job
        goes straight to the human rather than spending review rounds on no change.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "build")
        build_report = self.require_file(job_id, "build.md")
        first_line = first_content_line(build_report.read_text(encoding="utf-8"))
        if BLOCKED_HEADER.match(first_line):
            job["stage"] = "needs-human"
            # "fixing" describes a gate-fix round that has now ended without reaching the gate;
            # leaving it would send the next build straight back to the gate (see rework).
            job["quality_gate"] = None
            job["warnings"] = self.head_warnings(job) + [f"builder blocked in round {job['round']}: {first_line}"]
            self.save(board, job)
            return job
        if not self.dirty_paths() and self.head() == job["base"]:
            raise FactoryError(
                "builder produced no changes since the base commit; re-spawn the builder, "
                "or have it start build.md with BLOCKED: <reason> if it cannot proceed"
            )
        # Validated before the snapshot and stage change: an invalid diagram sends the job back
        # to the builder to fix, with nothing recorded for this round.
        diagram_warning = self.require_valid_diagrams(job_id)
        job["changed_files"] = self.write_change_snapshot(job)
        job["warnings"] = self.head_warnings(job)
        for message in (diagram_warning, self.stale_handover_warning(job, job["changed_files"])):
            if message:
                job["warnings"].append(message)
        if job["quality_gate"] == "fixing":
            # A gate-fix round only repairs what the gate reported, so it returns to the gate
            # instead of repeating tests and reviews (decision D27). The reviews therefore
            # predate this edit; the approver is told so through the job's gate_fix_rounds.
            job["stage"] = "quality-gate"
            self.save(board, job)
            return job
        job["stage"] = "test-audit"
        job["test_audit"] = "pending"
        job["reviews"] = {}
        self.save(board, job)
        return job

    def test_audit_done(self, job_id):
        """Gate the reviewers on test quality (decision D11).

        Weak tests are cheaper to fix before five reviewers spend a round on them,
        so CHANGES sends the job straight back to the builder. Those rebuilds have
        their own small budget so they never consume the review rounds; once it is
        spent the reviewers still run and the unresolved audit is carried as a
        warning to the approver and the human.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "test-audit")
        path = self.require_file(job_id, f"round-{job['round']}/test-audit.md")
        verdict, problem = check_verdict_file(path.read_text(encoding="utf-8"), "tests")
        if problem:
            raise FactoryError(f"{path.relative_to(self.repository_root)}: {problem}")
        job["test_audit"] = verdict
        job["warnings"] = self.head_warnings(job)
        job["warnings"] += self.refresh_findings(job)
        if verdict == "BLOCKED":
            return self.block_for_human(board, job, "tests", path)
        attempt = job["attempt"]
        if verdict == "CHANGES" and attempt["test_rebuilds"] < TEST_REBUILDS_PER_ATTEMPT:
            attempt["test_rebuilds"] += 1
            job["history"].append({"round": job["round"], "test_audit": verdict, "reviews": {}})
            job["round"] += 1
            job["stage"] = "build"
            self.save(board, job)
            return {"job": job, "next": "rebuild"}

        if verdict == "CHANGES":
            job["warnings"].append(f"test audit still requests changes after round {job['round']}")
        job["stage"] = "review"
        job["reviews"] = {reviewer: "pending" for reviewer in REVIEWERS}
        auto_not_applicable = self.write_automatic_not_applicable_reviews(job)
        for reviewer in auto_not_applicable:
            job["reviews"][reviewer] = "N/A"
        self.save(board, job)
        return {
            "job": job,
            "next": "review",
            "spawn": [reviewer for reviewer in REVIEWERS if reviewer not in auto_not_applicable],
        }

    def write_automatic_not_applicable_reviews(self, job):
        """Skip reviewers that could only answer N/A and return their names.

        UI (decision D5): both conditions the UI role uses must hold: the approved spec
        says `UI impact: no` and no changed file can affect what a user sees. UX is
        never skipped: CLI output and messages in any source file are UX, and file
        extensions cannot detect that.

        Architecture (decision D36): the spec says `Architecture impact: no` and the
        handover holds no diagram. Requiring both ties the skip to evidence, so a builder
        that drew a diagram anyway still gets it reviewed.

        Each skip is decided on its own; one reviewer staying on must not keep another on.
        """
        spec = self.require_file(job["id"], "spec.md").read_text(encoding="utf-8")
        round_directory = self.job_directory(job["id"]) / f"round-{job['round']}"
        skipped = []

        user_facing = [
            path for path in job.get("changed_files", [])
            if path.lower().endswith(USER_FACING_SUFFIXES)
        ]
        if spec_field_says_no(spec, UI_IMPACT_LINE, UI_IMPACT_NO) and not user_facing:
            (round_directory / "review-ui.md").write_text(
                "VERDICT: N/A\n"
                "Written by factory_board.py: the spec says `UI impact: no` and no changed "
                "file is visual (see files.txt).\n",
                encoding="utf-8",
            )
            skipped.append("ui")

        handover = self.job_directory(job["id"]) / HANDOVER_FILE
        # Skipping a review on a wrong "no diagram" would hide a change, so anything that might be a
        # diagram keeps the reviewer on; only a handover with no hint of one is skipped.
        has_diagram = handover.is_file() and MAYBE_DIAGRAM.search(handover.read_text(encoding="utf-8"))
        if spec_field_says_no(spec, ARCHITECTURE_IMPACT_LINE, ARCHITECTURE_IMPACT_NO) and not has_diagram:
            (round_directory / "review-architecture.md").write_text(
                "VERDICT: N/A\n"
                "Written by factory_board.py: the spec says `Architecture impact: no` and "
                f"{HANDOVER_FILE} contains no diagram.\n",
                encoding="utf-8",
            )
            skipped.append("architecture")
        return skipped

    def block_for_human(self, board, job, role, path):
        """Send the job to the human because a reviewer could not assess the change (D46).

        Mirrors a blocked builder (build_done): no further rounds are spent, because there is
        nothing for the builder to fix. The reason is the text under the verdict line, copied
        into a warning so the human sees it on the card without opening the file.
        """
        reason = path.read_text(encoding="utf-8").strip().split("\n", 1)[1].strip().splitlines()[0]
        job["stage"] = "needs-human"
        # A blocked gate-fix round must not leave "fixing" behind (see rework and build_done).
        job["quality_gate"] = None
        job["warnings"].append(f"{role} review blocked in round {job['round']}: {reason}")
        job["history"].append({"round": job["round"], "blocked": role, "reason": reason})
        self.save(board, job)
        return {"job": job, "next": "needs-human"}

    def derive_findings(self, job):
        """Rebuild the job's finding ledger from every round's review files.

        Derived rather than stored incrementally: the files are the source of truth, so a
        repeated or interrupted command can never leave the ledger out of step with them.
        Returns (ledger, notices). Notices are warnings about reviewer behaviour, never
        errors, because the id convention is followed by an LLM and is not yet measured
        (decision record, verification: ID-reuse measurement).

        A job with no FINDING lines at all gets an empty ledger and no notices, so jobs
        and reviews written before this format existed behave exactly as they did.
        """
        job_directory = self.job_directory(job["id"])
        ledger = {}
        notices = []
        round_numbers = sorted(
            int(path.name.split("-", 1)[1]) for path in job_directory.glob("round-*") if path.is_dir()
        )
        previous_open = set()
        for round_number in round_numbers:
            round_directory = job_directory / f"round-{round_number}"
            raised_this_round = set()
            closed_this_round = set()
            for role, filename in FINDING_FILES:
                path = round_directory / filename
                if not path.is_file():
                    continue
                for finding in parse_findings(path.read_text(encoding="utf-8")):
                    identifier = finding["id"]
                    raised_this_round.add(identifier)
                    entry = ledger.setdefault(identifier, {
                        "role": role, "severity": finding["severity"],
                        "location": finding["location"], "first_round": round_number,
                        "status": finding["status"], "reopened": False,
                    })
                    if finding["status"] == "open" and entry["status"] == "closed":
                        # Closed in an earlier round and open again: the oscillation signal.
                        entry["reopened"] = True
                        notices.append(f"finding {identifier} was closed and re-raised in round {round_number}")
                    if finding["status"] == "closed":
                        closed_this_round.add(identifier)
                    entry.update(
                        severity=finding["severity"], location=finding["location"],
                        status=finding["status"], last_round=round_number,
                    )
            # A finding that was open last round and is neither restated nor closed was dropped
            # without a word. Only warn for roles that ran this round: an N/A or skipped
            # reviewer legitimately restates nothing.
            for identifier in sorted(previous_open - raised_this_round - closed_this_round):
                if self.role_ran_in_round(round_directory, ledger[identifier]["role"]):
                    notices.append(
                        f"finding {identifier} was open in the previous round but round "
                        f"{round_number} neither restates nor closes it"
                    )
                    # Keep it open: silence is not a fix.
            previous_open = {
                identifier for identifier, entry in ledger.items() if entry["status"] != "closed"
            }
        return ledger, notices

    @staticmethod
    def role_ran_in_round(round_directory, role):
        filename = dict(FINDING_FILES)[role]
        path = round_directory / filename
        if not path.is_file():
            return False
        verdict = VERDICT_HEADER.match(first_content_line(path.read_text(encoding="utf-8")))
        return bool(verdict) and verdict.group(1) != "N/A"

    def refresh_findings(self, job):
        """Store the ledger and its unresolved list on the job, returning notices to warn on."""
        ledger, notices = self.derive_findings(job)
        job["findings"] = ledger
        job["unresolved"] = sorted(
            identifier for identifier, entry in ledger.items() if entry["status"] != "closed"
        )
        return notices

    def read_reviews(self, job):
        round_directory = self.job_directory(job["id"]) / f"round-{job['round']}"
        reviews = {}
        invalid = {}
        for reviewer in REVIEWERS:
            path = round_directory / f"review-{reviewer}.md"
            if not path.is_file():
                # A job that entered review before the architecture reviewer existed never had
                # it spawned, so waiting on it would strand the job. New jobs always record all
                # reviewers in test_audit_done, so a missing key identifies the older job.
                # The N/A is written as a file rather than only returned: round-status saves the
                # verdict into the job, which would add the key and make the next (documented as
                # repeatable) call read the missing file as pending again.
                if reviewer == "architecture" and reviewer not in job.get("reviews", {}):
                    path.write_text(
                        "VERDICT: N/A\n"
                        "Written by factory_board.py: this round started before the architecture "
                        "reviewer existed, so none was spawned.\n",
                        encoding="utf-8",
                    )
                else:
                    reviews[reviewer] = "pending"
                    continue
            verdict, problem = check_verdict_file(path.read_text(encoding="utf-8"), reviewer)
            if problem:
                reviews[reviewer] = "invalid"
                invalid[str(path.relative_to(self.repository_root))] = problem
            else:
                reviews[reviewer] = verdict
        return reviews, invalid

    def round_status(self, job_id):
        """Current review round progress; never changes the stage, so safe to repeat.

        It still saves per-reviewer verdicts so the dashboard shows the round live.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "review")
        reviews, invalid = self.read_reviews(job)
        job["reviews"] = reviews
        self.refresh_findings(job)
        self.save(board, job)
        complete = all(verdict not in ("pending", "invalid") for verdict in reviews.values())
        return {
            "reviews": reviews,
            "complete": complete,
            "invalid": invalid,
            "next": "close-round" if complete else "wait",
            "warnings": self.head_warnings(job),
        }

    def close_round(self, job_id):
        """WAIT FOR ALL: the round closes only when every reviewer file is valid.

        Closing advances the job: back to build when changes are requested and
        review rounds remain in this attempt, otherwise on to the whole-repo STRIDE
        sweep (stride-review), which runs once per job rather than once per round.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "review")
        reviews, invalid = self.read_reviews(job)
        waiting = [reviewer for reviewer, verdict in reviews.items() if verdict in ("pending", "invalid")]
        if waiting:
            raise FactoryError(f"round {job['round']} is not complete; waiting on {waiting}; invalid: {invalid}")
        job["reviews"] = reviews
        job["warnings"] = self.head_warnings(job)
        if job["test_audit"] == "CHANGES":
            job["warnings"].append(f"test audit still requests changes after round {job['round']}")
        job["warnings"] += self.refresh_findings(job)
        job["history"].append(
            {"round": job["round"], "test_audit": job["test_audit"], "reviews": dict(reviews)}
        )
        blocked = [reviewer for reviewer, verdict in reviews.items() if verdict == "BLOCKED"]
        if blocked:
            # No rebuild: a reviewer that could not assess left nothing for the builder to fix.
            path = self.job_directory(job_id) / f"round-{job['round']}" / f"review-{blocked[0]}.md"
            return self.block_for_human(board, job, blocked[0], path)
        attempt = job["attempt"]
        attempt["review_rounds"] += 1
        if "CHANGES" in reviews.values() and attempt["review_rounds"] < REVIEW_ROUNDS_PER_ATTEMPT:
            job["round"] += 1
            job["stage"] = "build"
            next_action = "rebuild"
        else:
            job["stage"] = "stride-review"
            job["stride"] = "pending"
            next_action = "stride-review"
        self.save(board, job)
        return {"job": job, "next": next_action}

    def stride_review_done(self, job_id):
        """Whole-repo STRIDE sweep, gating the approver (decisions SD5-SD7).

        Unlike security/ux/ui/code/architecture, STRIDE evaluates the job's full accumulated diff
        against a persisted, whole-repo trust-zone profile rather than one round's
        diff, so it runs once per job here rather than once per review round. A
        CHANGES verdict (a new or newly-confirmed CRITICAL/HIGH threat touching the
        changed component) sends the job back to the builder and consumes the same
        review-round budget as the other five reviewers, so the two mechanisms
        cannot together exceed the attempt's total review-round allowance.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "stride-review")
        path = self.require_file(job_id, f"round-{job['round']}/review-stride.md")
        verdict, problem = check_verdict_file(path.read_text(encoding="utf-8"), "stride")
        if problem:
            raise FactoryError(f"{path.relative_to(self.repository_root)}: {problem}")
        job["stride"] = verdict
        job["warnings"] = self.head_warnings(job)
        job["warnings"] += self.refresh_findings(job)
        if verdict == "BLOCKED":
            return self.block_for_human(board, job, "stride", path)
        attempt = job["attempt"]
        if verdict == "CHANGES" and attempt["review_rounds"] < REVIEW_ROUNDS_PER_ATTEMPT:
            attempt["review_rounds"] += 1
            job["history"].append({"round": job["round"], "stride": verdict})
            job["round"] += 1
            job["stage"] = "build"
            self.save(board, job)
            return {"job": job, "next": "rebuild"}

        if verdict == "CHANGES":
            job["warnings"].append(f"STRIDE review still requests changes after round {job['round']}")
        job["history"].append({"round": job["round"], "stride": verdict})
        job["stage"] = "quality-gate"
        job["quality_gate"] = "pending"
        self.save(board, job)
        return {"job": job, "next": "quality-gate"}

    def quality_gate_done(self, job_id):
        """Run the deterministic quality gate itself (decisions D27, D28).

        The board runs the script, not an agent, so the gate cannot be skipped or
        have its result rewritten by an LLM. Outcomes:
          - pass or warn: on to the approver;
          - fixable findings and a fix round left: back to the builder once;
          - fixable findings and no round left: on to the approver, findings carried
            as warnings so the human sees them;
          - unresolved tamper entries: never sent to the builder (only the human can
            accept a loosened check), carried to the approver for the human.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "quality-gate")
        report = self.run_quality_gate(job)
        job["warnings"] = self.head_warnings(job)
        summary = report["summary"]
        fixable = bool(report["findings"] or summary["failedChecks"])
        job["quality_gate"] = report["status"]
        job["history"].append({"round": job["round"], "quality_gate": report["status"]})
        for message in self.gate_warnings(report):
            job["warnings"].append(message)

        attempt = job["attempt"]
        if fixable and attempt["gate_fixes"] < GATE_FIXES_PER_ATTEMPT:
            attempt["gate_fixes"] += 1
            job["gate_fix_rounds"] = job.get("gate_fix_rounds", 0) + 1
            job["round"] += 1
            job["quality_gate"] = "fixing"
            job["stage"] = "build"
            self.save(board, job)
            return {"job": job, "next": "rebuild", "report": report}

        if fixable:
            job["warnings"].append("quality gate still reports findings after the gate-fix round")
        if summary["unresolvedTamper"]:
            job["warnings"].append(
                "quality gate: loosened checks need your decision: "
                f"{len(summary['unresolvedTamper'])} unresolved tamper entries (accept-suppression)"
            )
        job["stage"] = "approver"
        self.save(board, job)
        return {"job": job, "next": "approver", "report": report}

    def run_quality_gate(self, job):
        """Run quality_gate.py against the job's base and keep the report with the round."""
        round_directory = self.job_directory(job["id"]) / f"round-{job['round']}"
        round_directory.mkdir(exist_ok=True)
        report_path = round_directory / "quality-gate.json"
        accepted_path = round_directory / ".accepted-tamper.json"
        accepted_path.write_text(json.dumps(sorted(job["accepted_tamper"])), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(QUALITY_GATE_SCRIPT), "--base", job["base"],
             "--accepted", str(accepted_path), "--output", str(report_path)],
            cwd=self.repository_root, capture_output=True, text=True,
        )
        accepted_path.unlink(missing_ok=True)
        try:
            report = json.loads(result.stdout)
        except ValueError as error:
            raise FactoryError(f"quality gate produced no report: {result.stderr.strip() or error}") from error
        if report.get("status") == "error":
            # A broken gate must stop the job: treating it as a pass would hide every finding.
            raise FactoryError(f"quality gate could not run: {report.get('error')}")
        self.write_gate_markdown(job, report, round_directory)
        return report

    @staticmethod
    def gate_warnings(report):
        messages = []
        for tool in report["summary"]["skippedTools"]:
            messages.append(f"quality gate: {tool} did not run (not installed); see round report for the install hint")
        if report["summary"]["warnings"]:
            messages.append(f"quality gate: {report['summary']['warnings']} naming warning(s) to address in build.md")
        return messages

    def write_gate_markdown(self, job, report, round_directory):
        """A readable copy of the report, so it appears in the dashboard and to the next builder."""
        lines = [f"# Quality gate: {report['status']}", ""]
        for title, entries in (("Findings (must be fixed)", report["findings"]),
                               ("Warnings (address each in build.md)", report["warnings"])):
            lines.append(f"## {title}")
            lines += [f"- `{e['id']}` {e['file']}:{e['line']} {e['rule']}: {e['message']}" for e in entries] or ["None"]
            lines.append("")
        lines.append("## Tamper (loosened checks; only the human can accept these)")
        lines += [
            f"- `{e['id']}` {e['file']}:{e['line']} {e['rule']}: {e['message']}"
            f" [{'accepted' if e['accepted'] else 'UNRESOLVED'}]"
            for e in report["tamper"]
        ] or ["None"]
        lines += ["", "## Checks"]
        for check in report["checks"]:
            lines.append(f"- {check['name']}: {check['status']}"
                         + (f" ({check['message']})" if check.get("message") else ""))
            # A failed check must say why, or the human and the next builder cannot act on it.
            if check["status"] == "fail" and check.get("output"):
                lines += ["", "  ```text", *[f"  {line}" for line in check["output"].splitlines()], "  ```", ""]
        (round_directory / "quality-gate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def accept_suppression(self, job_id, entry_id, reason):
        """Record the human's acceptance of one loosened check (decision D24).

        Only the human runs this; the orchestrator instructions forbid agents from it,
        as with approve-spec. The board cannot tell who ran it, so that rule is
        enforced by instruction, which the decision record lists as a known limit.
        """
        if not reason.strip():
            raise FactoryError("accept-suppression needs a reason")
        board = self.load_board()
        job = self.find_job(board, job_id)
        known = self.known_tamper_ids(job)
        if entry_id not in known:
            raise FactoryError(f"unknown tamper entry {entry_id}; known: {sorted(known)}")
        job["accepted_tamper"][entry_id] = {"reason": reason.strip(), "accepted_at": utc_now()}
        self.save(board, job)
        return job

    def known_tamper_ids(self, job):
        ids = set()
        for report_path in (self.job_directory(job["id"])).glob("round-*/quality-gate.json"):
            try:
                ids |= {entry["id"] for entry in json.loads(report_path.read_text(encoding="utf-8"))["tamper"]}
            except (ValueError, KeyError):
                continue
        return ids

    def decision(self, job_id):
        """Humans give final approval, so the only accepted decision is ESCALATE."""
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "approver")
        path = self.require_file(job_id, "decision.md")
        first_line = first_content_line(path.read_text(encoding="utf-8"))
        if not DECISION_HEADER.match(first_line):
            raise FactoryError(
                "decision.md must start with ESCALATE; the factory never approves on its own"
            )
        # The approver finalises the handover, so it is checked once more before the human reads it.
        diagram_warning = self.require_valid_diagrams(job_id)
        if diagram_warning:
            job["warnings"].append(diagram_warning)
        # Name what is still open so the human sees the findings, not only that "a review still
        # requests changes". Empty for jobs that predate structured findings.
        self.refresh_findings(job)
        if job["unresolved"]:
            job["warnings"].append("unresolved findings: " + ", ".join(job["unresolved"]))
        job["stage"] = "needs-human"
        self.save(board, job)
        return job

    def rework(self, job_id, note):
        if not note.strip():
            raise FactoryError("rework needs a note for the builder")
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "needs-human")
        self.require_no_other_active_job(board, job_id)
        # A rework is the human asking for implementation, so it also confirms approval
        # (and repairs jobs approved before approve-spec recorded it in spec.md).
        self.mark_spec_approved(job_id)
        job["round"] += 1
        job["attempt"] = new_attempt()
        # A rework is new implementation work and must go back through tests and reviews, so it
        # must never inherit the gate-fix shortcut build_done takes while quality_gate is "fixing".
        # Today only a BLOCKED gate-fix build can reach needs-human in that state and it clears the
        # flag itself; this keeps the invariant at the point where it matters, whatever route led here.
        job["quality_gate"] = None
        note_path = self.job_directory(job_id) / f"rework-{job['round']}.md"
        note_path.write_text(f"# Human rework note (before round {job['round']})\n\n{note.strip()}\n", encoding="utf-8")
        job["stage"] = "build"
        job["warnings"] = self.head_warnings(job)
        self.save(board, job)
        return job

    def _close(self, job_id, reason, history_key, push=True, allowed_stages=None):
        if not reason.strip():
            raise FactoryError(f"{history_key.split('_')[0]} needs a reason")
        board = self.load_board()
        job = self.find_job(board, job_id)
        if job["stage"] in TERMINAL_STAGES:
            raise FactoryError(f"job {job_id} is already {job['stage']}")
        if allowed_stages:
            self.require_stage(job, *allowed_stages)
        label = history_key.split("_")[0]
        job["history"].append({"round": job["round"], history_key: job["stage"], "reason": reason.strip()})
        job["stage"] = "abandoned"
        job["warnings"] = [f"{label}: {reason.strip()}"]
        self.save(board, job, push=push)
        return job

    def abandon(self, job_id, reason, push=True):
        """Close a job for good so an interrupted run cannot block every later build.

        The one-active-job rule (D9) otherwise leaves a crashed job holding the
        worktree with no way out except hand-editing board.json. Code changes in the
        worktree are left untouched: the human decides whether to keep them.
        """
        return self._close(job_id, reason, "abandoned_from", push=push)

    def archive(self, job_id, reason="approved", push=True):
        """Close an approved job and move it to the Archive tab.

        Approval is the human saying the work is ready to commit, so the job no
        longer needs to sit in needs-human. It shares the terminal `abandoned`
        stage (the dashboard's archive bucket) but records `archived_from` in
        history so an approval is distinguishable from a crash cleanup.
        """
        return self._close(
            job_id, reason or "approved", "archived_from", push=push, allowed_stages=("needs-human",)
        )

    def resume(self, job_id):
        """Tell a fresh orchestrator session what to do next for an interrupted job."""
        board = self.load_board()
        job = self.find_job(board, job_id)
        round_folder = f".factory/jobs/{job_id}/round-{job['round']}/"
        stage = job["stage"]
        if stage == "review":
            reviews, invalid = self.read_reviews(job)
            missing = [reviewer for reviewer, verdict in reviews.items() if verdict in ("pending", "invalid")]
            action = (
                f"spawn reviewers {missing} for {round_folder}, then close-round"
                if missing else "close-round"
            )
        else:
            action = {
                "spec": "spawn spec-writer (it reads feature.md and any spec-feedback-*.md), then spec-written",
                "spec-review": "stop: the human reads spec.md and runs approve-spec or gives spec feedback",
                "build": f"spawn a fresh builder for round {job['round']}, then build-done",
                "test-audit": f"spawn test-auditor for {round_folder}, then test-audit-done",
                "stride-review": f"spawn the stride reviewer for {round_folder}, then stride-review-done",
                "quality-gate": "run quality-gate-done (the board runs the gate itself; no agent)",
                "approver": "spawn approver, then decision",
                "needs-human": "stop: the human reads decision.md and runs approve or rework",
                "abandoned": "nothing: the job is closed (archived or abandoned)",
            }[stage]
            if stage == "needs-human" and not (self.job_directory(job_id) / "decision.md").is_file():
                # A blocked builder or reviewer parks the job before the approver ever runs, so
                # there is no decision.md to read; the reason is in the job's warnings.
                action = (
                    "stop: the job was blocked before the approver ran, so there is no decision.md; "
                    "the human reads the blocked warning and runs rework (or abandon)"
                )
        return {"job": job, "next": action, "warnings": self.head_warnings(job)}

    def record_model(self, job_id, stage, model):
        if stage not in STAGE_TIERS:
            raise FactoryError(f"unknown stage '{stage}', expected one of {list(STAGE_TIERS)}")
        board = self.load_board()
        job = self.find_job(board, job_id)
        job["models"][stage] = model
        self.save(board, job)
        return job

    def show(self, job_id):
        board = self.load_board()
        if job_id:
            return self.find_job(board, job_id)
        return board

    def install_claude(self, claude_home):
        """Install the factory into Claude Code's user directory, outside the target repo.

        Claude Code does not read .agents/skills and pins subagent models in
        frontmatter, so this writes absolute-path pointers to the shared skill and
        role files (decision D1) and must be re-run after `models --cli claude`.
        """
        if not self.config_path.exists():
            raise FactoryError("no model config: run `models <preset> --cli claude` first")
        config = self.backfill_missing_stages(json.loads(self.config_path.read_text(encoding="utf-8")))
        if config.get("cli") != "claude":
            raise FactoryError(
                f"model config was written for {config.get('cli')}; "
                "run `models <preset> --cli claude` so Claude gets model names it understands"
            )
        written = []
        skill_pointer = claude_home / "skills" / "engineering-guard-factory" / "SKILL.md"
        skill_pointer.parent.mkdir(parents=True, exist_ok=True)
        skill_pointer.write_text(
            "---\n"
            "name: engineering-guard-factory\n"
            f"description: {read_skill_description()}\n"
            "---\n"
            f"Read and follow {SKILL_ROOT / 'SKILL.md'} exactly. Resolve its relative paths "
            f"against {SKILL_ROOT}. You are in Claude Code: pass `--cli claude` to `models` "
            "and use the `eg-*` subagents.\n",
            encoding="utf-8",
        )
        written.append(str(skill_pointer))

        agents_directory = claude_home / "agents"
        agents_directory.mkdir(parents=True, exist_ok=True)
        for role, stage in ROLE_STAGES.items():
            tools = "Read, Grep, Glob, Bash, Write"
            if role in EDITING_ROLES:
                tools += ", Edit"
            wrapper = agents_directory / f"eg-{role}.md"
            wrapper.write_text(
                "---\n"
                f"name: eg-{role}\n"
                f"description: Engineering Guard factory {role} stage. Used only by the factory orchestrator.\n"
                f"tools: {tools}\n"
                f"model: {config['stages'][stage]}\n"
                "---\n"
                f"Read and follow {ROLES_DIRECTORY / (role + '.md')} exactly. "
                "The orchestrator's prompt gives you the job folder.\n",
                encoding="utf-8",
            )
            written.append(str(wrapper))
        return {"written": written}


def read_skill_description():
    for line in (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip()
    raise FactoryError("factory SKILL.md has no description")


def spec_field_says_no(spec, field_line, says_no):
    """True when the first occurrence of this impact label in the spec says "no".

    Only the first labelled line counts: a later line that merely begins with the same words
    (prose under another section) must not turn a "yes" into a skipped review.

    The "no" is matched from the label's own position onward, not on the label line alone,
    because specs also use a heading form (`## UI impact`, a blank line, then `no`) and the
    original pattern accepted it by letting its non-word run span the newlines.
    """
    first = field_line.search(spec)
    return bool(first and says_no.match(spec, first.start()))


def first_content_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def new_attempt():
    return {"review_rounds": 0, "test_rebuilds": 0, "gate_fixes": 0}


def check_verdict_file(text, role):
    """Return (verdict, problem); problem is None when the file is acceptable for role."""
    allowed = ALLOWED_VERDICTS[role]
    expected = " or ".join(f"VERDICT: {verdict}" for verdict in allowed)
    match = VERDICT_HEADER.match(first_content_line(text))
    if not match or match.group(1) not in allowed:
        return None, f"must start with {expected}"
    verdict = match.group(1)
    # A bare CHANGES would send the builder back with nothing to fix.
    body = text.strip().split("\n", 1)[1].strip() if "\n" in text.strip() else ""
    if verdict == "CHANGES" and not body:
        return None, "VERDICT: CHANGES needs at least one finding below the verdict line"
    # A blocked review hands the job to a human, who needs to know what could not be assessed.
    if verdict == "BLOCKED" and not body:
        return None, "VERDICT: BLOCKED needs a reason below the verdict line"
    problem = check_finding_lines(body, role)
    if problem:
        return None, problem
    if verdict == "CHANGES" and role in SEVERITY_GATED_ROLES:
        # Severity floor (decision SD1): a round should only be sent back to the builder
        # for a CRITICAL/HIGH finding. MEDIUM/LOW/hardening-only findings previously
        # blocked a round the same way a CRITICAL did, because only the verdict header
        # was ever checked; reviewers now report those under PASS instead.
        # Severity may be a standalone line (the original form) or part of a FINDING line, so a
        # reviewer following the structured format is not made to write the severity twice. Only
        # open findings count: a closed or disputed one is not a reason to send the round back.
        severities = set(SEVERITY_LINE.findall(body))
        severities |= {f["severity"] for f in parse_findings(body) if f["status"] == "open"}
        if not severities & BLOCKING_SEVERITIES:
            return None, (
                "VERDICT: CHANGES requires a finding with 'SEVERITY: CRITICAL' or "
                "'SEVERITY: HIGH'; report MEDIUM/LOW/INFO findings under VERDICT: PASS instead"
            )
    return verdict, None


def check_finding_lines(body, role):
    """Return a problem string when a FINDING line is malformed or names another role's id.

    The role is the reviewer whose file this is. Requiring the id prefix to match it is what
    stops one reviewer from raising or closing another's finding (decision D47).
    """
    declared = FINDING_PREFIX.findall(body)
    parsed = list(FINDING_LINE.finditer(body))
    if len(declared) != len(parsed):
        return (
            "a FINDING line is malformed; expected "
            "'FINDING: <role>-<n> | SEVERITY: <level> | LOCATION: <path[:line]|none> | "
            "STATUS: open|closed|disputed'"
        )
    for finding in parsed:
        prefix = finding.group("id").rsplit("-", 1)[0]
        if prefix != role:
            return (
                f"finding {finding.group('id')} belongs to '{prefix}', not '{role}'; "
                f"a role may only raise or close findings whose id starts '{role}-'"
            )
    return None


def parse_findings(text):
    """Return the structured findings in one review file, in file order."""
    return [
        {
            "id": match.group("id"),
            "severity": match.group("severity"),
            "location": match.group("location"),
            "status": match.group("status"),
        }
        for match in FINDING_LINE.finditer(text)
    ]


def build_parser():
    parser = argparse.ArgumentParser(description="Engineering Guard factory board.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    models = commands.add_parser("models")
    models.add_argument("choice", nargs="+", help="<preset> or <expensive> <cheap>")
    models.add_argument("--cli", required=True, choices=SUPPORTED_CLIS)
    new = commands.add_parser("new")
    new.add_argument("title", nargs="?")
    new.add_argument("--from-backlog", action="store_true")
    new.add_argument("--issue", help="https://github.com/<owner>/<repo>/issues/<number>")
    for name in (
        "spec-written", "approve-spec", "build-done", "test-audit-done",
        "round-status", "close-round", "stride-review-done", "quality-gate-done", "decision", "resume",
    ):
        commands.add_parser(name).add_argument("job_id")
    for name, text in (("rework", "note"), ("spec-feedback", "note"), ("abandon", "reason")):
        parser_for_note = commands.add_parser(name)
        parser_for_note.add_argument("job_id")
        parser_for_note.add_argument(text)
    accept = commands.add_parser("accept-suppression")
    accept.add_argument("job_id")
    accept.add_argument("entry_id")
    accept.add_argument("reason")
    archive = commands.add_parser("archive")
    archive.add_argument("job_id")
    archive.add_argument("reason", nargs="?", default="approved")
    record = commands.add_parser("record-model")
    record.add_argument("job_id")
    record.add_argument("stage")
    record.add_argument("model")
    show = commands.add_parser("show")
    show.add_argument("job_id", nargs="?")
    install = commands.add_parser("install-claude")
    install.add_argument("--claude-home", type=Path, default=Path.home() / ".claude")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    try:
        factory = Factory(find_repository_root())
        command = arguments.command
        if command == "init":
            result = factory.init()
        elif command == "models":
            result = factory.models(arguments.choice, arguments.cli)
        elif command == "new":
            result = factory.new(arguments.title, arguments.from_backlog, arguments.issue)
        elif command == "spec-written":
            result = factory.spec_written(arguments.job_id)
        elif command == "approve-spec":
            result = factory.approve_spec(arguments.job_id)
        elif command == "build-done":
            result = factory.build_done(arguments.job_id)
        elif command == "test-audit-done":
            result = factory.test_audit_done(arguments.job_id)
        elif command == "round-status":
            result = factory.round_status(arguments.job_id)
        elif command == "close-round":
            result = factory.close_round(arguments.job_id)
        elif command == "stride-review-done":
            result = factory.stride_review_done(arguments.job_id)
        elif command == "quality-gate-done":
            result = factory.quality_gate_done(arguments.job_id)
        elif command == "accept-suppression":
            result = factory.accept_suppression(arguments.job_id, arguments.entry_id, arguments.reason)
        elif command == "decision":
            result = factory.decision(arguments.job_id)
        elif command == "rework":
            result = factory.rework(arguments.job_id, arguments.note)
        elif command == "spec-feedback":
            result = factory.spec_feedback(arguments.job_id, arguments.note)
        elif command == "abandon":
            result = factory.abandon(arguments.job_id, arguments.reason)
        elif command == "archive":
            result = factory.archive(arguments.job_id, arguments.reason)
        elif command == "resume":
            result = factory.resume(arguments.job_id)
        elif command == "record-model":
            result = factory.record_model(arguments.job_id, arguments.stage, arguments.model)
        elif command == "show":
            result = factory.show(arguments.job_id)
        else:
            result = factory.install_claude(arguments.claude_home)
    except FactoryError as error:
        print(json.dumps({"error": str(error)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
