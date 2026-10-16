import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import {
  copyFileSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const hookPath = join(projectRoot, '.codex', 'hooks', 'testing-guard.mjs');
const hookConfigPath = join(projectRoot, '.codex', 'hooks.json');
const policies = {
  testing: readFileSync(join(projectRoot, 'policies', 'testing-policy.md'), 'utf8'),
  engineering: readFileSync(join(projectRoot, 'policies', 'engineering-policy.md'), 'utf8'),
};
const skills = [
  ['research', 'engineering-guard-research'],
  ['implement', 'engineering-guard-implement'],
  ['testing', 'engineering-guard-testing'],
  ['verify', 'engineering-guard-verify'],
  ['better-prompt', 'engineering-guard-better-prompt'],
  ['align', 'engineering-guard-align'],
  ['security', 'engineering-guard-security'],
];
const baseTempDirectory = mkdtempSync(join(tmpdir(), 'engineering-guard-test-'));

test.after(() => rmSync(baseTempDirectory, { recursive: true, force: true }));

function runHook(event, { scriptPath = hookPath, stateRoot = baseTempDirectory, prepareStateRoot = true } = {}) {
  if (prepareStateRoot) mkdirSync(stateRoot, { recursive: true });
  const result = spawnSync(process.execPath, [scriptPath], {
    encoding: 'utf8',
    env: { ...process.env, TMP: stateRoot, TEMP: stateRoot, TMPDIR: stateRoot },
    input: JSON.stringify(event),
  });
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, result.stderr);
  return result.stdout.trim() ? JSON.parse(result.stdout) : null;
}

function sessionEvent(hookEventName, sessionId, extra = {}) {
  return {
    session_id: sessionId,
    transcript_path: null,
    cwd: projectRoot,
    hook_event_name: hookEventName,
    permission_mode: 'default',
    ...extra,
  };
}

function toolEvent(toolName, command, sessionId = 'test-session') {
  return {
    ...sessionEvent('PreToolUse', sessionId),
    turn_id: 'turn-123',
    tool_name: toolName,
    tool_use_id: 'call-456',
    tool_input: { command },
  };
}

const testPatch = `*** Begin Patch\n*** Add File: tests/test_checkout.py\n+print("test")\n*** End Patch`;
const sourcePatch = `*** Begin Patch\n*** Update File: src/checkout.py\n-print(1)\n+print(2)\n*** End Patch`;
const productionPatch = `*** Begin Patch\n*** Update File: src/checkout.cjs\n-old\n+new\n*** End Patch`;

test('SessionStart keeps the existing testing-policy delivery and does not load engineering policy by default', () => {
  const started = runHook(sessionEvent('SessionStart', 'startup-session', { source: 'startup' }));
  const context = started.hookSpecificOutput.additionalContext;

  assert.equal(started.hookSpecificOutput.hookEventName, 'SessionStart');
  assert.ok(context.includes(policies.testing));
  assert.ok(!context.includes(policies.engineering));
  assert.equal(runHook(toolEvent('apply_patch', testPatch, 'startup-session')), null);
});

test('a missed SessionStart blocks one genuine test-file edit and a retry uses normal Codex handling', () => {
  const firstAttempt = runHook(toolEvent('apply_patch', testPatch, 'first-test-session'));
  assert.equal(firstAttempt.hookSpecificOutput.hookEventName, 'PreToolUse');
  assert.equal(firstAttempt.hookSpecificOutput.permissionDecision, 'deny');
  assert.ok(firstAttempt.hookSpecificOutput.additionalContext.includes(policies.testing));
  assert.match(firstAttempt.hookSpecificOutput.permissionDecisionReason, /retry this file change once/);
  assert.equal(runHook(toolEvent('apply_patch', testPatch, 'first-test-session')), null);
});

test('apply_patch production writes receive engineering policy once while Bash reads and unrelated tools are untouched', () => {
  const firstAttempt = runHook(toolEvent('apply_patch', productionPatch, 'source-session'));
  assert.equal(firstAttempt.hookSpecificOutput.permissionDecision, 'deny');
  assert.ok(firstAttempt.hookSpecificOutput.additionalContext.includes(policies.engineering));
  assert.equal(runHook(toolEvent('apply_patch', productionPatch, 'source-session')), null);

  assert.equal(runHook(toolEvent('Bash', 'node src/checkout.cjs')), null);
  const unrelated = {
    ...sessionEvent('PreToolUse', 'unrelated-session'),
    tool_name: 'mcp__filesystem__write_file',
    tool_use_id: 'call-mcp',
    tool_input: { path: 'src/checkout.cjs', contents: 'new' },
  };
  assert.equal(runHook(unrelated), null);
  assert.equal(runHook(toolEvent('some_other_tool', productionPatch)), null);
});

test('Bash uses Codex tool_input.command for source and test writes, but not for ordinary commands', () => {
  const sourceWrite = toolEvent('Bash', "node -e \"require('fs').writeFileSync('src/checkout.cjs', 'new')\"", 'bash-source-session');
  const sourceDenied = runHook(sourceWrite);
  assert.equal(sourceDenied.hookSpecificOutput.permissionDecision, 'deny');
  assert.ok(sourceDenied.hookSpecificOutput.additionalContext.includes(policies.engineering));

  const testWrite = toolEvent('Bash', "cat > 'tests/test_checkout.py' <<'EOF'\nprint('test')\nEOF", 'bash-test-session');
  const testDenied = runHook(testWrite);
  assert.equal(testDenied.hookSpecificOutput.permissionDecision, 'deny');
  assert.ok(testDenied.hookSpecificOutput.additionalContext.includes(policies.testing));

  assert.equal(runHook(toolEvent('Bash', 'pytest tests/test_checkout.py', 'bash-test-session')), null);
});

test('a mixed production-and-test patch supplies both missing policies in one denial', () => {
  const mixedPatch = `*** Begin Patch\n*** Update File: src/checkout.cjs\n-old\n+new\n*** Add File: tests/checkout.test.cjs\n+assert.ok(true)\n*** End Patch`;
  const denied = runHook(toolEvent('apply_patch', mixedPatch, 'mixed-session'));

  assert.equal(denied.hookSpecificOutput.permissionDecision, 'deny');
  assert.ok(denied.hookSpecificOutput.additionalContext.includes(policies.testing));
  assert.ok(denied.hookSpecificOutput.additionalContext.includes(policies.engineering));
  assert.equal(runHook(toolEvent('apply_patch', mixedPatch, 'mixed-session')), null);
});

test('recognized test file patterns keep the existing Python and JavaScript/TypeScript gate', () => {
  const cases = [
    toolEvent('Bash', `python -c "open('tests/orders_test.py', 'w').write('x')"`),
    toolEvent('Bash', `node -e "require('fs').writeFileSync('src/checkout.test.ts', 'x')"`),
    toolEvent('apply_patch', `*** Begin Patch Patch\n*** Update File: src/__tests__/checkout.jsx\n-old\n+new\n*** End Patch`),
  ];

  for (const [index, event] of cases.entries()) {
    event.session_id = `naming-pattern-${index}`;
    assert.equal(runHook(event).hookSpecificOutput.permissionDecision, 'deny');
  }
});

test('SessionStart after compaction restores testing and previously delivered engineering policy only', () => {
  const sessionId = 'compact-session';
  runHook(sessionEvent('SessionStart', sessionId, { source: 'startup' }));
  assert.equal(runHook(toolEvent('apply_patch', productionPatch, sessionId)).hookSpecificOutput.permissionDecision, 'deny');
  assert.equal(runHook(toolEvent('apply_patch', productionPatch, sessionId)), null);

  const compacted = runHook(sessionEvent('SessionStart', sessionId, { source: 'compact' }));
  assert.ok(compacted.hookSpecificOutput.additionalContext.includes(policies.testing));
  assert.ok(compacted.hookSpecificOutput.additionalContext.includes(policies.engineering));
});

test('policy edits invalidate session acknowledgements and updated policy is delivered before a retry', () => {
  const tempProject = mkdtempSync(join(baseTempDirectory, 'changed-policy-'));
  const copiedHook = join(tempProject, '.codex', 'hooks', 'testing-guard.mjs');
  const copiedPolicies = {
    testing: join(tempProject, 'policies', 'testing-policy.md'),
    engineering: join(tempProject, 'policies', 'engineering-policy.md'),
  };
  mkdirSync(dirname(copiedHook), { recursive: true });
  mkdirSync(dirname(copiedPolicies.testing), { recursive: true });
  copyFileSync(hookPath, copiedHook);
  copyFileSync(join(projectRoot, 'policies', 'testing-policy.md'), copiedPolicies.testing);
  copyFileSync(join(projectRoot, 'policies', 'engineering-policy.md'), copiedPolicies.engineering);

  const stateRoot = join(baseTempDirectory, 'changed-policy-state');
  const options = { scriptPath: copiedHook, stateRoot };
  const sessionId = 'changed-policy-session';
  runHook(sessionEvent('SessionStart', sessionId, { source: 'startup' }), options);
  const initialSourceWrite = runHook(toolEvent('apply_patch', productionPatch, sessionId), options);
  assert.ok(initialSourceWrite.hookSpecificOutput.additionalContext.includes(policies.engineering));
  assert.equal(runHook(toolEvent('apply_patch', productionPatch, sessionId), options), null);

  const revisedEngineeringPolicy = `${policies.engineering}\nUpdated engineering policy.\n`;
  writeFileSync(copiedPolicies.engineering, revisedEngineeringPolicy);
  const staleEngineeringAck = runHook(toolEvent('apply_patch', productionPatch, sessionId), options);
  assert.equal(staleEngineeringAck.hookSpecificOutput.permissionDecision, 'deny');
  assert.ok(staleEngineeringAck.hookSpecificOutput.additionalContext.includes('Updated engineering policy.'));
  assert.equal(runHook(toolEvent('apply_patch', productionPatch, sessionId), options), null);

  const revisedTestingPolicy = `${policies.testing}\nUpdated testing policy.\n`;
  writeFileSync(copiedPolicies.testing, revisedTestingPolicy);
  const staleTestingAck = runHook(toolEvent('apply_patch', testPatch, sessionId), options);
  assert.equal(staleTestingAck.hookSpecificOutput.permissionDecision, 'deny');
  assert.ok(staleTestingAck.hookSpecificOutput.additionalContext.includes('Updated testing policy.'));
  assert.equal(runHook(toolEvent('apply_patch', testPatch, sessionId), options), null);
});

test('session state is isolated, removed on SessionEnd, and unidentified writes fail closed', () => {
  const sessionA = 'session-a';
  runHook(sessionEvent('SessionStart', sessionA, { source: 'startup' }));
  assert.equal(runHook(toolEvent('apply_patch', testPatch, sessionA)), null);

  const sessionB = runHook(toolEvent('apply_patch', testPatch, 'session-b'));
  assert.equal(sessionB.hookSpecificOutput.permissionDecision, 'deny');

  runHook(sessionEvent('SessionEnd', sessionA, { reason: 'other' }));
  const stateNamespace = createHash('sha256')
    .update(String(process.getuid?.() ?? process.env.USERPROFILE ?? process.env.HOME ?? 'user'))
    .digest('hex')
    .slice(0, 16);
  const sessionHash = createHash('sha256').update(sessionA).digest('hex');
  assert.throws(() => readFileSync(join(baseTempDirectory, `engineering-guard-${stateNamespace}`, `${sessionHash}.json`)));

  const unidentifiedWrite = runHook(toolEvent('apply_patch', testPatch, null));
  assert.equal(unidentifiedWrite.hookSpecificOutput.permissionDecision, 'deny');
  assert.match(unidentifiedWrite.hookSpecificOutput.permissionDecisionReason, /did not provide a session_id/);
});

test('policy or state-storage failures deny a recognized write without asking for repeated retries', () => {
  const unavailableTempPath = join(baseTempDirectory, 'temp-path-is-a-file');
  writeFileSync(unavailableTempPath, 'not a directory');
  const options = { stateRoot: unavailableTempPath, prepareStateRoot: false };

  const start = runHook(sessionEvent('SessionStart', 'state-error-session', { source: 'startup' }), options);
  assert.match(start.systemMessage, /could not load or record a policy/);

  const denied = runHook(toolEvent('Bash', 'cat > tests/test_checkout.py', 'state-error-session'), options);
  assert.equal(denied.hookSpecificOutput.permissionDecision, 'deny');
  assert.match(denied.hookSpecificOutput.permissionDecisionReason, /Do not retry until/);
});

test('Codex hook config and all seven skills use repository-local discovery paths without a Stop hook', () => {
  const config = JSON.parse(readFileSync(hookConfigPath, 'utf8'));
  const preToolMatchers = config.hooks.PreToolUse.map((group) => group.matcher);

  assert.ok(config.hooks.SessionStart && config.hooks.PreToolUse && config.hooks.SessionEnd);
  assert.ok(preToolMatchers.some((matcher) => new RegExp(matcher).test('Bash')));
  assert.ok(preToolMatchers.some((matcher) => new RegExp(matcher).test('apply_patch')));
  assert.ok(!config.hooks.Stop);

  for (const [directory, name] of skills) {
    const path = join(projectRoot, '.agents', 'skills', directory, 'SKILL.md');
    assert.match(readFileSync(path, 'utf8'), new RegExp(`^name: ${name}$`, 'm'));
  }
});

test('malformed hook input leaves Codex handling untouched', () => {
  const malformed = spawnSync(process.execPath, [hookPath], { encoding: 'utf8', input: '{not-json' });
  assert.equal(malformed.status, 0);
  assert.equal(malformed.stdout, '');
});
