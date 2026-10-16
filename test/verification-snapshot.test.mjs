import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  mkdtempSync,
  mkdirSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const snapshotPath = join(projectRoot, 'scripts', 'verification-snapshot.mjs');
const temporaryRoot = mkdtempSync(join(tmpdir(), 'engineering-guard-snapshot-'));
const fixtureRoot = join(temporaryRoot, 'fixture');
mkdirSync(join(fixtureRoot, 'src'), { recursive: true });
spawnSync('git', ['init', '--quiet', fixtureRoot], { encoding: 'utf8' });
writeFileSync(join(fixtureRoot, 'src', 'handler.mjs'), 'export const value = 1;\n');

test.after(() => rmSync(temporaryRoot, { recursive: true, force: true }));

function checkSnapshot(expected) {
  const result = spawnSync(process.execPath, [snapshotPath, ...(expected ? [expected] : [])], {
    cwd: fixtureRoot,
    encoding: 'utf8',
  });
  assert.equal(result.error, undefined, result.error?.message);
  const output = result.stdout.trim() ? JSON.parse(result.stdout) : null;
  return { ...result, output };
}

test('verification evidence is explicitly missing until a fingerprint is supplied', () => {
  const missing = checkSnapshot();
  assert.equal(missing.status, 0);
  assert.equal(missing.output.status, 'missing');
  assert.match(missing.output.fingerprint, /^[a-f0-9]{64}$/);

  const current = checkSnapshot(missing.output.fingerprint);
  assert.equal(current.status, 0);
  assert.equal(current.output.status, 'current');
});

test('a source edit, addition, or deletion makes an earlier verification receipt stale', () => {
  const initial = checkSnapshot().output.fingerprint;
  writeFileSync(join(fixtureRoot, 'src', 'handler.mjs'), 'export const value = 2;\n');
  const afterEdit = checkSnapshot(initial);
  assert.equal(afterEdit.status, 1);
  assert.equal(afterEdit.output.status, 'stale');

  writeFileSync(join(fixtureRoot, 'src', 'new-handler.mjs'), 'export const added = true;\n');
  const afterAdd = checkSnapshot(afterEdit.output.fingerprint);
  assert.equal(afterAdd.status, 1);
  assert.equal(afterAdd.output.status, 'stale');

  unlinkSync(join(fixtureRoot, 'src', 'handler.mjs'));
  const afterDelete = checkSnapshot(afterAdd.output.fingerprint);
  assert.equal(afterDelete.status, 1);
  assert.equal(afterDelete.output.status, 'stale');
});

test('a working tree without a commit can still be fingerprinted', () => {
  const result = spawnSync('git', ['rev-parse', '--verify', 'HEAD'], { cwd: fixtureRoot, encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.match(checkSnapshot().output.fingerprint, /^[a-f0-9]{64}$/);
});
