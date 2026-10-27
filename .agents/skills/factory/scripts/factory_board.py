"""State machine and only writer of .factory/board.json for the Engineering Guard factory.

The orchestrator (whichever agent session runs the factory skill) calls this script
instead of editing board.json by hand. Every command validates the job files the
agents were expected to write, so the loop rules live in one tested place:

  spec -> spec-review -(human approve-spec)-> build -> test-audit -> review -> build ... -> approver -> needs-human

Run from anywhere inside the target Git repository. Output is JSON on stdout; a
rule violation exits 2 with {"error": ...} so the orchestrator can react.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PRESETS_FILE = SKILL_ROOT / "presets.json"
DASHBOARD_TEMPLATE = SKILL_ROOT / "assets" / "dashboard.html"
ROLES_DIRECTORY = SKILL_ROOT / "roles"

FACTORY_DIRECTORY_NAME = ".factory"
REVIEWERS = ("security", "ux", "ui", "code")
VERDICTS = ("PASS", "CHANGES", "N/A")
# Two review rounds per build attempt (initial build or human rework); after that
# the approver escalates with whatever findings remain instead of looping forever.
ROUNDS_PER_ATTEMPT = 2
SPEC_STATUS_LINE = re.compile(r"^\*\*Status:\*\*.*$", re.MULTILINE)
BLOCKED_HEADER = re.compile(r"^BLOCKED\b")
VERDICT_HEADER = re.compile(r"^VERDICT:\s*(PASS|CHANGES|N/A)\s*$")
DECISION_HEADER = re.compile(r"^ESCALATE\b")
SUPPORTED_CLIS = ("claude", "codex", "kilo")
STAGE_TIERS = {
    "spec": "expensive",
    "build": "expensive",
    "tests": "cheap",
    "security": "expensive",
    "ux": "cheap",
    "ui": "cheap",
    "code": "cheap",
    "approver": "expensive",
}
ACTIVE_STAGES = ("build", "test-audit", "review", "approver")
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
    "approver": "approver",
}
# Bind to loopback: specs and security reviews can describe unfixed vulnerabilities.
DASHBOARD_COMMAND = "python3 -m http.server 8000 --bind 127.0.0.1 -d .factory"
BACKLOG_TEMPLATE = """# Factory backlog

One feature per line. `next` takes the first unchecked item.

- [ ] Example: describe a feature here
"""


class FactoryError(Exception):
    """A factory rule was violated; the message tells the orchestrator what is missing."""


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
        # Always refresh the dashboard so skill upgrades reach existing factories.
        dashboard = self.directory / "dashboard.html"
        dashboard.write_text(DASHBOARD_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")

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
                return job
        raise FactoryError(f"unknown job {job_id}")

    def job_directory(self, job_id):
        return self.directory / "jobs" / job_id

    def save(self, board, job):
        """Persist the board after refreshing the job's file index for the dashboard."""
        directory = self.job_directory(job["id"])
        job["files"] = sorted(
            str(path.relative_to(directory)) for path in directory.rglob("*.md")
        )
        job["updated"] = utc_now()
        self.write_json(self.board_path, board)

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
        """Uncommitted paths outside .factory/ (which is excluded from Git anyway)."""
        output = run_git(self.repository_root, "status", "--porcelain", "--untracked-files=all")
        paths = [line[3:] for line in output.splitlines() if line.strip()]
        return [path for path in paths if not path.startswith(f"{FACTORY_DIRECTORY_NAME}/")]

    def head(self):
        return run_git(self.repository_root, "rev-parse", "HEAD").strip()

    def head_warnings(self, job):
        # Reviewers diff the worktree against the HEAD recorded at build start; if the
        # human commits mid-job that diff silently shrinks, so surface it.
        if job.get("base") and job["base"] != self.head():
            return [f"HEAD moved since build started (base {job['base'][:12]}); review diffs may be incomplete"]
        return []

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

    def new(self, title, from_backlog):
        self.ensure_initialized()
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
            "round_limit": 0,
            "base": None,
            "test_audit": None,
            "reviews": {},
            "history": [],
            "models": {},
            "warnings": [],
            "created": utc_now(),
        }
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
        job["stage"] = "spec-review"
        self.save(board, job)
        return job

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
        job["round_limit"] = ROUNDS_PER_ATTEMPT
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
            job["warnings"] = self.head_warnings(job) + [f"builder blocked in round {job['round']}: {first_line}"]
            self.save(board, job)
            return job
        if not self.dirty_paths() and self.head() == job["base"]:
            raise FactoryError(
                "builder produced no changes since the base commit; re-spawn the builder, "
                "or have it start build.md with BLOCKED: <reason> if it cannot proceed"
            )
        (self.job_directory(job_id) / f"round-{job['round']}").mkdir(exist_ok=True)
        job["stage"] = "test-audit"
        job["test_audit"] = "pending"
        job["reviews"] = {}
        job["warnings"] = self.head_warnings(job)
        self.save(board, job)
        return job

    def test_audit_done(self, job_id):
        """Gate the reviewers on test quality (decision D11).

        Weak tests are cheaper to fix before four reviewers spend a round on them,
        so CHANGES sends the job straight back to the builder. It uses the same
        round budget as reviews; at the limit the reviewers still run and the
        unresolved audit is carried as a warning to the approver and the human.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "test-audit")
        path = self.require_file(job_id, f"round-{job['round']}/test-audit.md")
        verdict = parse_verdict(path.read_text(encoding="utf-8"))
        if verdict not in ("PASS", "CHANGES"):
            raise FactoryError(
                f"{path.relative_to(self.repository_root)} must start with VERDICT: PASS or VERDICT: CHANGES"
            )
        job["test_audit"] = verdict
        job["warnings"] = self.head_warnings(job)
        if verdict == "CHANGES" and job["round"] < job["round_limit"]:
            job["history"].append({"round": job["round"], "test_audit": verdict, "reviews": {}})
            job["round"] += 1
            job["stage"] = "build"
            next_action = "rebuild"
        else:
            if verdict == "CHANGES":
                job["warnings"].append(f"test audit still requests changes after round {job['round']}")
            job["stage"] = "review"
            job["reviews"] = {reviewer: "pending" for reviewer in REVIEWERS}
            next_action = "review"
        self.save(board, job)
        return {"job": job, "next": next_action}

    def round_status(self, job_id):
        """WAIT FOR ALL: the round completes only when every reviewer file is valid.

        On completion this also advances the job: back to build when changes are
        requested and rounds remain, otherwise on to the approver.
        """
        board = self.load_board()
        job = self.find_job(board, job_id)
        self.require_stage(job, "review")
        round_directory = self.job_directory(job_id) / f"round-{job['round']}"
        reviews = {}
        invalid = []
        for reviewer in REVIEWERS:
            path = round_directory / f"review-{reviewer}.md"
            if not path.is_file():
                reviews[reviewer] = "pending"
                continue
            verdict = parse_verdict(path.read_text(encoding="utf-8"))
            if verdict is None:
                reviews[reviewer] = "invalid"
                invalid.append(str(path.relative_to(self.repository_root)))
            else:
                reviews[reviewer] = verdict
        job["reviews"] = reviews
        job["warnings"] = self.head_warnings(job)
        if job["test_audit"] == "CHANGES":
            job["warnings"].append(f"test audit still requests changes after round {job['round']}")

        complete = all(verdict in VERDICTS for verdict in reviews.values())
        next_action = "wait"
        if complete:
            job["history"].append(
                {"round": job["round"], "test_audit": job["test_audit"], "reviews": dict(reviews)}
            )
            if "CHANGES" in reviews.values() and job["round"] < job["round_limit"]:
                job["round"] += 1
                job["stage"] = "build"
                next_action = "rebuild"
            else:
                job["stage"] = "approver"
                next_action = "approver"
        self.save(board, job)
        return {"job": job, "complete": complete, "next": next_action, "invalid": invalid}

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
        job["round_limit"] = job["round"] + ROUNDS_PER_ATTEMPT - 1
        note_path = self.job_directory(job_id) / f"rework-{job['round']}.md"
        note_path.write_text(f"# Human rework note (before round {job['round']})\n\n{note.strip()}\n", encoding="utf-8")
        job["stage"] = "build"
        job["warnings"] = self.head_warnings(job)
        self.save(board, job)
        return job

    def record_model(self, job_id, stage, model):
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
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
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


def first_content_line(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def parse_verdict(text):
    match = VERDICT_HEADER.match(first_content_line(text))
    return match.group(1) if match else None


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
    for name in ("spec-written", "approve-spec", "build-done", "test-audit-done", "round-status", "decision"):
        commands.add_parser(name).add_argument("job_id")
    rework = commands.add_parser("rework")
    rework.add_argument("job_id")
    rework.add_argument("note")
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
            result = factory.new(arguments.title, arguments.from_backlog)
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
        elif command == "decision":
            result = factory.decision(arguments.job_id)
        elif command == "rework":
            result = factory.rework(arguments.job_id, arguments.note)
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
