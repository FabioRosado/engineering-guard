import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const demoRoot = dirname(fileURLToPath(import.meta.url));
const testPath = join(demoRoot, 'test', 'discount-contract.test.mjs');
const variants = ['simple', 'overengineered'];

for (const variant of variants) {
  const implementation = join(demoRoot, variant, 'discount.mjs');
  const result = spawnSync(process.execPath, ['--test', '--test-reporter=tap', testPath], {
    cwd: demoRoot,
    encoding: 'utf8',
    env: { ...process.env, ENGINEERING_GUARD_DISCOUNT_IMPLEMENTATION: implementation },
  });
  const output = `${result.stdout}\n${result.stderr}`;

  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, `${variant} failed the shared behavior contract:\n${output}`);
  assert.match(output, /^# pass 3$/m, `${variant} did not execute all contract cases:\n${output}`);
  assert.match(output, /^# fail 0$/m, `${variant} failed the shared behavior contract:\n${output}`);
  process.stdout.write(`PASS: ${variant} implementation satisfies all three shared behavior cases.\n`);
}

process.stdout.write('Read both implementations to compare responsibility boundaries and indirection; line count is not a quality score.\n');
