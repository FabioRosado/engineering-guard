import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const fixtureRoot = dirname(fileURLToPath(import.meta.url));
const testPath = join(fixtureRoot, 'test', 'authorization.test.mjs');

function run(implementation) {
  return spawnSync(process.execPath, ['--test', '--test-reporter=tap', testPath], {
    encoding: 'utf8',
    env: { ...process.env, ENGINEERING_GUARD_USER_RECORDS: implementation },
  });
}

const vulnerable = run(join(fixtureRoot, 'vulnerable', 'user-records.mjs'));
const vulnerableOutput = `${vulnerable.stdout}\n${vulnerable.stderr}`;
assert.equal(vulnerable.error, undefined, vulnerable.error?.message);
assert.notEqual(vulnerable.status, 0, vulnerableOutput);
const failures = [...vulnerableOutput.matchAll(/^not ok \d+ - (.+)$/gm)].map((match) => match[1]);
assert.deepEqual(failures, ['a user cannot read another user record by changing the record ID'], vulnerableOutput);
assert.match(vulnerableOutput, /^# pass 2$/m);
assert.match(vulnerableOutput, /^# fail 1$/m);

const fixed = run(join(fixtureRoot, 'fixed', 'user-records.mjs'));
const fixedOutput = `${fixed.stdout}\n${fixed.stderr}`;
assert.equal(fixed.error, undefined, fixed.error?.message);
assert.equal(fixed.status, 0, fixedOutput);
assert.match(fixedOutput, /^# pass 3$/m);
assert.match(fixedOutput, /^# fail 0$/m);

process.stdout.write('PASS: the cross-user authorization regression fails on the vulnerable fixture.\n');
process.stdout.write('PASS: owner access and denial tests pass on the corrected fixture.\n');
