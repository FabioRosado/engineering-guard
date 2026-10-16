// Models GET /api/records/:recordId after authentication middleware supplies principalId.
export function getUserRecord({ principalId, recordId }, records) {
  if (!principalId) return { status: 401, body: null };

  const record = records.get(recordId);
  if (!record || record.ownerId !== principalId) return { status: 404, body: null };

  return { status: 200, body: { id: record.id, ownerId: record.ownerId, email: record.email } };
}
