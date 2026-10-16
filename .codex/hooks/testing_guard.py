import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATHS = {
    "testing": PROJECT_ROOT / "policies" / "testing-policy.md",
    "engineering": PROJECT_ROOT / "policies" / "engineering-policy.md",
}
POLICY_LABELS = {"testing": "testing", "engineering": "engineering"}
USER_IDENTITY = str(
    os.getuid()
    if hasattr(os, "getuid")
    else os.environ.get("USERPROFILE") or os.environ.get("HOME") or "user"
)
STATE_NAMESPACE = hashlib.sha256(USER_IDENTITY.encode()).hexdigest()[:16]
TEMP_ROOT = (
    Path(os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir())
    if os.name == "nt"
    else Path(os.environ.get("TMPDIR") or tempfile.gettempdir())
)
STATE_DIRECTORY = TEMP_ROOT / f"engineering-guard-{STATE_NAMESPACE}"
JAVASCRIPT_TEST_EXTENSION = r"(?:[cm]?js|jsx|[cm]?ts|tsx)"
PRODUCTION_CODE_EXTENSIONS = set(
    "js jsx ts tsx cjs mjs cts mts py go rs java kt kts c h cc cpp hpp cs rb php swift scala sh bash zsh sql ex exs clj cljs cljc dart lua pl pm r vue svelte astro".split()
)


def normalize_path(file_path):
    normalized = re.sub(r"/{2,}", "/", str(file_path).replace("\\", "/"))
    return normalized.lower() if os.name == "nt" else normalized


def is_test_file(file_path):
    if not isinstance(file_path, str) or not file_path:
        return False

    normalized = normalize_path(file_path)
    return any(
        re.search(pattern, normalized, re.IGNORECASE)
        for pattern in (
            r"(?:^|/)test[^/]*\.py$",
            r"_test\.py$",
            rf"\.(?:test|spec)\.{JAVASCRIPT_TEST_EXTENSION}$",
            rf"/__tests__/.*\.{JAVASCRIPT_TEST_EXTENSION}$",
        )
    )


def is_production_code_file(file_path):
    if not isinstance(file_path, str) or not file_path or is_test_file(file_path):
        return False
    filename = normalize_path(file_path).rsplit("/", 1)[-1]
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return extension in PRODUCTION_CODE_EXTENSIONS


def shell_path_candidates(command):
    tokens = re.findall(r'"[^"\n]*"|\'[^\'\n]*\'|[^\s;|&<>]+', command)
    candidates = []
    for token in tokens:
        unquoted = token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'" else token
        unquoted = re.sub(r"^[([{,]+|[)\]},;]+$", "", unquoted)
        nested = re.findall(r'"[^"\n]*"|\'[^\'\n]*\'', unquoted)
        for candidate in (unquoted, *(part[1:-1] for part in nested)):
            candidates.extend((candidate, candidate.split("=")[-1]))
    return candidates


def has_shell_redirection(command):
    quote = None
    escaped = False

    for index, character in enumerate(command):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in "\"'":
            quote = character
            continue
        if character == ">" and (index + 1 >= len(command) or command[index + 1] != "="):
            return True

    return False


def is_likely_shell_write(command):
    file_commands = re.compile(
        r"\b(?:tee|touch|cp|mv|install|rm|unlink|del|rmdir|sed\s+-i\S*|perl\s+-i\S*)\b",
        re.IGNORECASE,
    )
    language_file_writes = re.compile(
        r"\b(?:writeFile(?:Sync)?|appendFile(?:Sync)?)\s*\(|\bopen\s*\([^,]+,\s*['\"][wa]|\.(?:write_text|write_bytes|unlink)\s*\(",
        re.IGNORECASE,
    )
    return has_shell_redirection(command) or bool(file_commands.search(command)) or bool(language_file_writes.search(command))


def patch_file_paths(command):
    pattern = r"^\*\*\*\s+(?:(?:Update|Add|Delete) File:|Move to:)\s*(.+?)\s*$"
    return re.findall(pattern, command, re.MULTILINE)


def target_paths(event):
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return []
    if event.get("tool_name") == "apply_patch":
        return patch_file_paths(command)
    if event.get("tool_name") == "Bash" and is_likely_shell_write(command):
        return shell_path_candidates(command)
    return []


def policy_contents(name):
    return POLICY_PATHS[name].read_text(encoding="utf-8")


def policy_digest(contents):
    return hashlib.sha256(contents.encode("utf-8")).hexdigest()


def session_state_path(session_id):
    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return STATE_DIRECTORY / f"{session_hash}.json"


def read_acknowledgements(session_id):
    try:
        serialized_state = session_state_path(session_id).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}

    try:
        state = json.loads(serialized_state)
        policies = state.get("policies")
        if policies is not None:
            return policies if isinstance(policies, dict) else {}
        return {"testing": state["policy_digest"]} if state.get("policy_digest") else {}
    except (AttributeError, json.JSONDecodeError, TypeError):
        return {}


def save_acknowledgements(session_id, policies):
    STATE_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE_DIRECTORY.chmod(0o700)
    path = session_state_path(session_id)
    path.write_text(json.dumps({"policies": policies}), encoding="utf-8")
    path.chmod(0o600)


def output(value):
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")


def policy_context(name, contents):
    label = "testing" if name == "testing" else "engineering"
    target = "tests" if name == "testing" else "production code"
    return f"Engineering Guard {label} policy. Apply these requirements before changing {target}:\n\n{contents}"


def handle_session_start(event):
    try:
        testing_policy = policy_contents("testing")
        contexts = [policy_context("testing", testing_policy)]

        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id:
            acknowledgements = read_acknowledgements(session_id)
            acknowledgements["testing"] = policy_digest(testing_policy)

            if acknowledgements.get("engineering"):
                engineering_policy = policy_contents("engineering")
                acknowledgements["engineering"] = policy_digest(engineering_policy)
                contexts.append(policy_context("engineering", engineering_policy))

            save_acknowledgements(session_id, acknowledgements)

        output(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n\n---\n\n".join(contexts),
                }
            }
        )
    except Exception:
        output(
            {
                "systemMessage": "Engineering Guard could not load or record a policy. Affected file changes may be blocked until the policy and session temp directory are available."
            }
        )


def handle_policy_write(event, policy_names):
    if not policy_names:
        return

    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        additional_context = ""
        try:
            additional_context = "\n\n---\n\n".join(
                policy_context(name, policy_contents(name)) for name in policy_names
            )
        except Exception:
            pass
        result = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Codex did not provide a session_id, so Engineering Guard cannot record policy delivery. Reopen the session before retrying this file change.",
        }
        if additional_context:
            result["additionalContext"] = additional_context
        output({"hookSpecificOutput": result})
        return

    try:
        acknowledgements = read_acknowledgements(session_id)
        pending_policies = []
        for name in policy_names:
            contents = policy_contents(name)
            digest = policy_digest(contents)
            if acknowledgements.get(name) != digest:
                pending_policies.append((name, contents, digest))

        if not pending_policies:
            return

        for name, _, digest in pending_policies:
            acknowledgements[name] = digest
        # Record before denying so one combined retry can proceed without a repeat block.
        save_acknowledgements(session_id, acknowledgements)

        policy_names_text = " and ".join(f"{POLICY_LABELS[name]} policy" for name, _, _ in pending_policies)
        is_single = len(pending_policies) == 1
        output(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"The Engineering Guard {policy_names_text} {'is' if is_single else 'are'} now available in context. "
                        f"Review {'it' if is_single else 'them'}, then retry this file change once."
                    ),
                    "additionalContext": "\n\n---\n\n".join(
                        policy_context(name, contents) for name, contents, _ in pending_policies
                    ),
                }
            }
        )
    except Exception:
        output(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Engineering Guard could not load its policy or record this session. Do not retry until the policy and session temp directory are available.",
                }
            }
        )


def handle_event(event):
    if not isinstance(event, dict):
        return

    event_name = event.get("hook_event_name")
    if event_name == "SessionStart":
        handle_session_start(event)
        return

    if event_name == "SessionEnd":
        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id:
            try:
                session_state_path(session_id).unlink()
            except FileNotFoundError:
                pass
        return

    if event_name != "PreToolUse":
        return

    paths = target_paths(event)
    policy_names = []
    if any(is_test_file(path) for path in paths):
        policy_names.append("testing")
    if any(is_production_code_file(path) for path in paths):
        policy_names.append("engineering")
    handle_policy_write(event, policy_names)


try:
    handle_event(json.loads(sys.stdin.read()))
except Exception:
    # Malformed events have no safe target to classify, so preserve normal Codex handling.
    pass
