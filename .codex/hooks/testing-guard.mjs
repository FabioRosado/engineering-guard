import { createHash } from 'node:crypto';
import {
  chmodSync,
  mkdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const policyPaths = {
  testing: join(projectRoot, 'policies', 'testing-policy.md'),
  engineering: join(projectRoot, 'policies', 'engineering-policy.md'),
};
const policyLabels = { testing: 'testing', engineering: 'engineering' };
const userIdentity = String(process.getuid?.() ?? process.env.USERPROFILE ?? process.env.HOME ?? 'user');
const stateNamespace = createHash('sha256').update(userIdentity).digest('hex').slice(0, 16);
const stateDirectory = join(tmpdir(), `engineering-guard-${stateNamespace}`);
const javascriptTestExtension = String.raw`(?:[cm]?js|jsx|[cm]?ts|tsx)`;
const productionCodeExtension = String.raw`(?:[cm]?[jt]sx?|py|go|rs|java|kt|kts|c|h|cc|cpp|hpp|cs|rb|php|swift|scala|sh|bash|zsh|sql|ex|exs|clj|cljs|cljc|dart|lua|pl|pm|r|vue|svelte|astro)`;

function normalizePath(filePath) {
  const normalized = String(filePath).replaceAll('\\', '/').replace(/\/{2,}/g, '/');
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized;
}

function isTestFile(filePath) {
  if (typeof filePath !== 'string' || !filePath) return false;

  const normalized = normalizePath(filePath);
  return (
    /(?:^|\/)test[^/]*\.py$/i.test(normalized) ||
    /_test\.py$/i.test(normalized) ||
    new RegExp(String.raw`\.(?:test|spec)\.${javascriptTestExtension}$`, 'i').test(normalized) ||
    new RegExp(String.raw`\/__tests__\/.*\.${javascriptTestExtension}$`, 'i').test(normalized)
  );
}

function isProductionCodeFile(filePath) {
  if (typeof filePath !== 'string' || !filePath || isTestFile(filePath)) return false;
  return new RegExp(String.raw`\.${productionCodeExtension}$`, 'i').test(normalizePath(filePath));
}

function shellPathCandidates(command) {
  const quotedOrPlainTokens = command.match(/"[^"\n]*"|'[^'\n]*'|[^\s;|&<>]+/g) ?? [];
  return quotedOrPlainTokens.flatMap((token) => {
    const unquoted = token.replace(/^("|')(.*)\1$/, '$2').replace(/^[([{,]+|[)\]},;]+$/g, '');
    const nestedQuotedTokens = unquoted.match(/"[^"\n]*"|'[^'\n]*'/g) ?? [];
    return [unquoted, ...nestedQuotedTokens.map((nested) => nested.slice(1, -1))]
      .flatMap((candidate) => [candidate, candidate.split('=').at(-1)]);
  });
}

function hasShellRedirection(command) {
  let quote = null;
  let escaped = false;

  for (let index = 0; index < command.length; index += 1) {
    const character = command[index];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (character === '\\' && quote !== "'") {
      escaped = true;
      continue;
    }
    if (quote) {
      if (character === quote) quote = null;
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      continue;
    }
    if (character === '>' && command[index + 1] !== '=') return true;
  }

  return false;
}

function isLikelyShellWrite(command) {
  const fileCommands = /\b(?:tee|touch|cp|mv|install|rm|unlink|del|rmdir|sed\s+-i\S*|perl\s+-i\S*)\b/i;
  const languageFileWrites = /\b(?:writeFile(?:Sync)?|appendFile(?:Sync)?)\s*\(|\bopen\s*\([^,]+,\s*["'][wa]|\.(?:write_text|write_bytes|unlink)\s*\(/i;

  return hasShellRedirection(command) || fileCommands.test(command) || languageFileWrites.test(command);
}

function patchFilePaths(command) {
  return [...command.matchAll(/^\*\*\*\s+(?:(?:Update|Add|Delete) File:|Move to:)\s*(.+?)\s*$/gm)]
    .map((match) => match[1]);
}

function targetPaths(event) {
  const command = event.tool_input?.command;
  if (typeof command !== 'string') return [];
  if (event.tool_name === 'apply_patch') return patchFilePaths(command);
  if (event.tool_name === 'Bash' && isLikelyShellWrite(command)) return shellPathCandidates(command);
  return [];
}

function policyContents(name) {
  return readFileSync(policyPaths[name], 'utf8');
}

function policyDigest(contents) {
  return createHash('sha256').update(contents).digest('hex');
}

function sessionStatePath(sessionId) {
  const sessionHash = createHash('sha256').update(sessionId).digest('hex');
  return join(stateDirectory, `${sessionHash}.json`);
}

function readAcknowledgements(sessionId) {
  let serializedState;
  try {
    serializedState = readFileSync(sessionStatePath(sessionId), 'utf8');
  } catch (error) {
    if (error.code === 'ENOENT') return {};
    throw error;
  }

  try {
    const state = JSON.parse(serializedState);
    // Keep sessions opened by the original Testing Guard compatible.
    return state.policies ?? (state.policy_digest ? { testing: state.policy_digest } : {});
  } catch {
    return {};
  }
}

function saveAcknowledgements(sessionId, policies) {
  mkdirSync(stateDirectory, { recursive: true, mode: 0o700 });
  chmodSync(stateDirectory, 0o700);
  writeFileSync(sessionStatePath(sessionId), JSON.stringify({ policies }), { mode: 0o600 });
}

function output(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function policyContext(name, contents) {
  const label = name === 'testing' ? 'testing' : 'engineering';
  return `Engineering Guard ${label} policy. Apply these requirements before changing ${name === 'testing' ? 'tests' : 'production code'}:\n\n${contents}`;
}

function handleSessionStart(event) {
  try {
    const testingPolicy = policyContents('testing');
    const contexts = [policyContext('testing', testingPolicy)];

    if (typeof event.session_id === 'string' && event.session_id) {
      const acknowledgements = readAcknowledgements(event.session_id);
      acknowledgements.testing = policyDigest(testingPolicy);

      if (acknowledgements.engineering) {
        const engineeringPolicy = policyContents('engineering');
        acknowledgements.engineering = policyDigest(engineeringPolicy);
        contexts.push(policyContext('engineering', engineeringPolicy));
      }

      saveAcknowledgements(event.session_id, acknowledgements);
    }

    output({
      hookSpecificOutput: {
        hookEventName: 'SessionStart',
        additionalContext: contexts.join('\n\n---\n\n'),
      },
    });
  } catch {
    output({ systemMessage: 'Engineering Guard could not load or record a policy. Affected file changes may be blocked until the policy and session temp directory are available.' });
  }
}

function handlePolicyWrite(event, policyNames) {
  if (!policyNames.length) return;

  const sessionId = event.session_id;
  if (typeof sessionId !== 'string' || !sessionId) {
    let additionalContext = '';
    try {
      additionalContext = policyNames
        .map((name) => policyContext(name, policyContents(name)))
        .join('\n\n---\n\n');
    } catch {}
    output({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: 'Codex did not provide a session_id, so Engineering Guard cannot record policy delivery. Reopen the session before retrying this file change.',
        ...(additionalContext ? { additionalContext } : {}),
      },
    });
    return;
  }

  try {
    const acknowledgements = readAcknowledgements(sessionId);
    const pendingPolicies = policyNames.flatMap((name) => {
      const contents = policyContents(name);
      const digest = policyDigest(contents);
      return acknowledgements[name] === digest ? [] : [{ name, contents, digest }];
    });

    if (!pendingPolicies.length) return;

    for (const { name, digest } of pendingPolicies) acknowledgements[name] = digest;
    // Record before denying so one combined retry can proceed without a repeat block.
    saveAcknowledgements(sessionId, acknowledgements);

    const policyNamesText = pendingPolicies.map(({ name }) => `${policyLabels[name]} policy`).join(' and ');
    output({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: `The Engineering Guard ${policyNamesText} ${pendingPolicies.length === 1 ? 'is' : 'are'} now available in context. Review ${pendingPolicies.length === 1 ? 'it' : 'them'}, then retry this file change once.`,
        additionalContext: pendingPolicies
          .map(({ name, contents }) => policyContext(name, contents))
          .join('\n\n---\n\n'),
      },
    });
  } catch {
    output({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: 'Engineering Guard could not load its policy or record this session. Do not retry until the policy and session temp directory are available.',
      },
    });
  }
}

function handleEvent(event) {
  if (!event || typeof event !== 'object' || Array.isArray(event)) return;

  if (event.hook_event_name === 'SessionStart') {
    handleSessionStart(event);
    return;
  }

  if (event.hook_event_name === 'SessionEnd') {
    if (typeof event.session_id === 'string' && event.session_id) {
      try {
        unlinkSync(sessionStatePath(event.session_id));
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
    }
    return;
  }

  if (event.hook_event_name !== 'PreToolUse') return;

  const paths = targetPaths(event);
  const policyNames = [];
  if (paths.some(isTestFile)) policyNames.push('testing');
  if (paths.some(isProductionCodeFile)) policyNames.push('engineering');
  handlePolicyWrite(event, policyNames);
}

try {
  handleEvent(JSON.parse(readFileSync(0, 'utf8')));
} catch {
  // Malformed events have no safe target to classify, so preserve normal Codex handling.
}
