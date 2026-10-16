import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const implementation = process.env.ENGINEERING_GUARD_USER_RECORDS;
if (!implementation) throw new Error('Set ENGINEERING_GUARD_USER_RECORDS to a fixture implementation.');
const { getUserRecord } = await import(pathToFileURL(implementation).href);
const records = new Map([
  ['record-alice', { id: 'record-alice', ownerId: 'alice', email: 'alice@example.test' }],
  ['record-bob', { id: 'record-bob', ownerId: 'bob', email: 'bob@example.test' }],
]);

test('an authenticated owner can read their own record', () => {
  assert.deepEqual(
    getUserRecord({ principalId: 'alice', recordId: 'record-alice' }, records),
    { status: 200, body: { id: 'record-alice', ownerId: 'alice', email: 'alice@example.test' } },
  );
});

test('a user cannot read another user record by changing the record ID', () => {
  assert.deepEqual(
    getUserRecord({ principalId: 'alice', recordId: 'record-bob' }, records),
    { status: 404, body: null },
  );
});

test('an unauthenticated request is rejected', () => {
  assert.deepEqual(
    getUserRecord({ principalId: null, recordId: 'record-alice' }, records),
    { status: 401, body: null },
  );
});
