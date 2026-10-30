import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const ID = 'a'.repeat(24);
const ADMIN = { id: 'b'.repeat(24), isAdmin: true };
function load(path, modules = {}) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: id => id in modules ? modules[id] : id.endsWith('/privacy-policy') ? load('../lib/privacy-policy.ts') : require(id), Date, URL, Request, Response });
  return exports;
}
const { readOfferConfirmation } = load('../lib/offer-confirmation.ts');
const { verificationSummary } = load('../lib/verification.ts');
const valid = (changes = {}) => ({ status: 'CONFIRMED', employer_contact: 'hr@example.com', source_url: 'https://example.com/contact', offer_reference: 'OFFER-123',
  job_title: 'Tester', confirmed_at: '2020-01-01T10:00:00Z', note: 'HR confirmed the offer reference, recruiter authority and employment terms.',
  independentContact: true, recruiterConfirmed: true, termsConfirmed: true, ...changes });
function store({ conflict = false, scamStatus = 'UNREVIEWED' } = {}) {
  const row = { id: ID, companyName: 'Example Ltd', score: 80, riskLevel: 'HIGH', scamStatus, reviewVersion: 0, reviewHistory: [] };
  const recorder = load('../lib/record-offer-confirmation.ts', { './prisma': { prisma: { report: {
    findUnique: async () => row,
    updateMany: async ({ data }) => { if (conflict) return { count: 0 }; Object.assign(row, data); return { count: 1 }; },
  } } } });
  return { ...recorder, row };
}

test('a reviewer can record confirmation with evidence while keeping the scan risk unchanged', async () => {
  const service = store();
  const confirmation = await service.recordOfferConfirmation(ID, valid(), ADMIN);
  assert.equal(confirmation.status, 'CONFIRMED');
  assert.equal(service.row.reviewVersion, 1);
  assert.equal(service.row.reviewHistory[0].reviewerId, ADMIN.id);
  assert.equal(service.row.score, 80);
  assert.equal(service.row.riskLevel, 'HIGH');
  assert.equal(readOfferConfirmation(service.row.reviewHistory).status, 'CONFIRMED');
});
test('ordinary users, incomplete evidence and unsafe contact URLs cannot establish confirmation', async () => {
  for (const [body, user] of [[valid(), { ...ADMIN, isAdmin: false }], [valid({ independentContact: false }), ADMIN],
    [valid({ recruiterConfirmed: false }), ADMIN], [valid({ termsConfirmed: false }), ADMIN], [valid({ offer_reference: '' }), ADMIN],
    [valid({ source_url: 'https://user:password@example.com/' }), ADMIN], [valid({ confirmed_at: '2099-01-01' }), ADMIN]]) {
    const service = store();
    await assert.rejects(service.recordOfferConfirmation(ID, body, user));
    assert.equal(service.row.reviewHistory.length, 0);
  }
});
test('concurrent reviews and confirmed scam decisions prevent a contradictory confirmation', async () => {
  for (const options of [{ conflict: true }, { scamStatus: 'CONFIRMED_SCAM' }]) {
    const service = store(options);
    await assert.rejects(service.recordOfferConfirmation(ID, valid(), ADMIN));
    assert.equal(service.row.reviewHistory.length, 0);
  }
});
test('revocation and later scam confirmation invalidate earlier employer confirmation permanently', async () => {
  const service = store();
  await service.recordOfferConfirmation(ID, valid(), ADMIN);
  const original = [...service.row.reviewHistory];
  assert.equal(readOfferConfirmation([...original, { action: 'CONFIRM_SCAM' }, { action: 'CLEAR' }]), null);
  await service.recordOfferConfirmation(ID, valid({ status: 'REVOKED' }), ADMIN);
  assert.equal(readOfferConfirmation(service.row.reviewHistory).status, 'REVOKED');
  assert.equal(readOfferConfirmation(original, 'CONFIRMED_SCAM'), null);
  assert.equal(readOfferConfirmation([{ action: 'RECORD_OFFER_CONFIRMATION', reviewerId: 'model', confirmation: valid() }]), null);
});
test('low risk, missing evidence, conflicts and employer confirmation stay separate', () => {
  const report = { risk_level: 'LOW', score: 0, source_checks: [] };
  const initial = verificationSummary(report);
  assert.equal(initial.level, 'LIMITED');
  assert.equal(initial.resolved, 0);
  report.source_checks = [{ check: 'employer', status: 'MATCHED' }, { check: 'website', status: 'MISMATCH' }];
  const partial = verificationSummary(report);
  assert.equal(partial.level, 'PARTIAL');
  assert.equal(partial.resolved, 2);
  assert.equal(partial.items.find(item => item.id === 'offer').status, 'UNVERIFIED');
  assert.equal(report.score, 0);
});
test('confirmation API requires an admin, same origin and report access before writing evidence', async () => {
  for (const [user, origin, paid] of [[null, 'https://example.com', true], [{ isAdmin: false }, 'https://example.com', true],
    [ADMIN, 'https://attacker.example', true], [ADMIN, null, true], [ADMIN, 'https://example.com', false], [ADMIN, 'https://example.com', true]]) {
    let writes = 0;
    const route = load('../app/api/offer-confirmation/route.ts', {
      '@/lib/session': { getCurrentUser: async () => user }, '@/lib/prisma': { isDatabaseConfigured: () => true },
      '@/lib/reports': { isObjectId: () => true }, '@/lib/payments': { canDownload: async () => paid },
      '@/lib/record-offer-confirmation': { ConfirmationInputError: class extends Error {}, ConfirmationConflict: class extends Error {}, recordOfferConfirmation: async () => { writes++; return valid(); } },
    });
    const headers = { 'Content-Type': 'application/json', ...(origin ? { Origin: origin } : {}) };
    const response = await route.POST(new Request('https://example.com/api/offer-confirmation', { method: 'POST', headers, body: JSON.stringify({ id: ID, ...valid() }) }));
    const accepted = Boolean(user?.isAdmin && origin === 'https://example.com' && paid);
    assert.equal(response.status, accepted ? 200 : 403);
    assert.equal(writes, accepted ? 1 : 0);
  }
});
