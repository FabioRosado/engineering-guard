import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { lstatSync, readFileSync, readlinkSync } from 'node:fs';
import { resolve } from 'node:path';

function git(args, cwd, options = {}) {
  const result = spawnSync('git', args, { cwd, encoding: 'utf8', ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(result.stderr.trim() || `git ${args[0]} failed`);
  return result.stdout;
}

export function fingerprintWorkingTree(cwd = process.cwd()) {
  const root = git(['rev-parse', '--show-toplevel'], cwd).trim();
  const headResult = spawnSync('git', ['rev-parse', '--verify', 'HEAD'], { cwd: root, encoding: 'utf8' });
  if (headResult.error) throw headResult.error;
  const revision = headResult.status === 0 ? headResult.stdout.trim() : '(unborn)';
  const paths = git(['ls-files', '--cached', '--others', '--exclude-standard', '-z'], root)
    .split('\0')
    .filter(Boolean)
    .sort();
  const hash = createHash('sha256').update(`HEAD\0${revision}\0`);

  for (const path of paths) {
    const absolutePath = resolve(root, path);
    let stat;
    try {
      stat = lstatSync(absolutePath);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      hash.update(`${path}\0missing\0`);
      continue;
    }

    hash.update(`${path}\0${stat.mode & 0o777}\0`);
    if (stat.isSymbolicLink()) {
      const target = readlinkSync(absolutePath);
      hash.update(`symlink\0${target.length}\0${target}\0`);
    } else if (stat.isFile()) {
      const contents = readFileSync(absolutePath);
      hash.update(`file\0${contents.length}\0`).update(contents).update('\0');
    } else {
      throw new Error(`Cannot fingerprint non-file repository entry: ${path}`);
    }
  }

  return hash.digest('hex');
}

try {
  const [expected, ...extra] = process.argv.slice(2);
  if (extra.length || (expected && !/^[a-f0-9]{64}$/i.test(expected))) {
    throw new Error('Usage: node scripts/verification-snapshot.mjs [expected-sha256]');
  }

  const fingerprint = fingerprintWorkingTree();
  const status = !expected ? 'missing' : expected.toLowerCase() === fingerprint ? 'current' : 'stale';
  process.stdout.write(`${JSON.stringify({ status, fingerprint, ...(expected ? { expected } : {}) })}\n`);
  if (status === 'stale') process.exitCode = 1;
} catch (error) {
  process.stderr.write(`Unable to create verification snapshot: ${error.message}\n`);
  process.exitCode = 2;
}
