// Models GET /api/records/:recordId after authentication middleware supplies principalId.
export function getUserRecord({ principalId, recordId }, records) {
  if (!principalId) return { status: 401, body: null };

  const record = records.get(recordId);
  if (!record) return { status: 404, body: null };

  // Intentionally vulnerable: the authenticated user is not checked against the record owner.
  return { status: 200, body: { id: record.id, ownerId: record.ownerId, email: record.email } };
}
