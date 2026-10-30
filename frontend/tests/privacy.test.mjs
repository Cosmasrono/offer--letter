import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
function load(path, modules = {}, globals = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: id => id in modules ? modules[id] : require(id), Date, Buffer, Response, Request, URL, process, ...globals });
  return exports;
}
const policy = load('../lib/privacy-policy.ts');
const ID = 'a'.repeat(24);
const TOKEN = 'b'.repeat(64);
const OWNER = { id: 'owner', isAdmin: false };
function storage({ token = TOKEN, failIndex = false } = {}) {
  let row;
  let deleted = 0;
  let commands = 0;
  const privacy = load('../lib/report-privacy.ts', {
    'server-only': {}, './privacy-policy': policy,
    'next/headers': { cookies: async () => ({ get: () => token ? { value: token } : undefined }) },
    './prisma': { prisma: {
      $runCommandRaw: async command => { commands++; assert.equal(command.createIndexes, 'Report'); assert.equal(command.indexes[0].expireAfterSeconds, 0); if (failIndex) throw new Error('unavailable'); },
      report: { findUnique: async () => row, deleteMany: async ({ where }) => { if (!row || row.id !== where.id || row.userId !== where.userId) return { count: 0 }; deleted++; row = null; return { count: 1 }; } },
    } },
  });
  return { ...privacy, set report(value) { row = value; }, get deleted() { return deleted; }, get commands() { return commands; } };
}

test('guest deletion requires the submitting browser secret; links and admin roles cannot substitute', async () => {
  const original = storage();
  const report = { id: ID, userId: null, managementTokenHash: original.hashManagementToken(TOKEN), expiresAt: policy.reportExpiry() };
  for (const token of ['', 'c'.repeat(64), 'not-a-valid-token']) {
    const stranger = storage({ token }); stranger.report = report;
    assert.equal(await stranger.deleteOwnReport(ID, { id: 'admin', isAdmin: true }), false);
    assert.equal(stranger.deleted, 0);
  }
  original.report = report;
  assert.equal(await original.deleteOwnReport(ID, null), true);
  assert.equal(original.deleted, 1);
});

test('account owners can delete unpaid reports; other users and unrelated admins cannot', async () => {
  const store = storage();
  store.report = { id: ID, userId: OWNER.id, expiresAt: policy.reportExpiry() };
  assert.equal(await store.deleteOwnReport(ID, null), false);
  assert.equal(await store.deleteOwnReport(ID, { id: 'admin', isAdmin: true }), false);
  assert.equal(await store.deleteOwnReport(ID, OWNER), true);
  assert.equal(await store.deleteOwnReport(ID, OWNER), false);
});

test('expiry stops access at the boundary and preserves legacy reports', async () => {
  const now = new Date('2026-10-29T00:00:00Z');
  assert.equal(policy.reportExpiry(now).toISOString(), '2026-11-28T00:00:00.000Z');
  assert.equal(policy.isReportExpired({ expiresAt: now }, now), true);
  assert.equal(policy.isReportExpired({ expiresAt: new Date(now.getTime() + 1) }, now), false);
  assert.equal(policy.isReportExpired({}, now), false);
  const session = load('../lib/session.ts', { 'server-only': {}, 'next/headers': {}, react: { cache: fn => fn }, './prisma': {}, './privacy-policy': policy });
  assert.equal(session.canViewReport({ userId: null, expiresAt: new Date(0) }, { isAdmin: true }), false);
  assert.equal(session.canViewReport({ userId: OWNER.id }, OWNER), true);
});

test('retention index is installed once, failures reject and remain retryable', async () => {
  const ready = storage();
  await Promise.all([ready.ensureReportRetention(), ready.ensureReportRetention()]);
  assert.equal(ready.commands, 1);
  const failure = storage({ failIndex: true });
  await assert.rejects(failure.ensureReportRetention(), /retention/);
  await assert.rejects(failure.ensureReportRetention(), /retention/);
  assert.equal(failure.commands, 2);
});

test('deletion API rejects foreign origins and malformed IDs before calling storage', async () => {
  let writes = 0;
  const route = load('../app/api/report-privacy/route.ts', {
    '@/lib/prisma': { isDatabaseConfigured: () => true }, '@/lib/reports': { isObjectId: id => /^[a-f0-9]{24}$/.test(id) },
    '@/lib/session': { getCurrentUser: async () => OWNER }, '@/lib/report-privacy': { deleteOwnReport: async () => { writes++; return true; } },
  });
  const request = (origin, id) => new Request('https://example.test/api/report-privacy', { method: 'DELETE', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
  assert.equal((await route.DELETE(request('https://attacker.test', ID))).status, 403);
  assert.equal((await route.DELETE(request('https://example.test', 'bad'))).status, 404);
  assert.equal(writes, 0);
  const response = await route.DELETE(request('https://example.test', ID));
  assert.equal(response.status, 200);
  assert.equal(writes, 1);
  assert.match(response.headers.get('cache-control'), /no-store/);
});

test('paid tokens and development free access cannot restore missing or expired reports', async () => {
  for (const report of [null, { expiresAt: new Date(0) }]) {
    let paymentReads = 0;
    const payments = load('../lib/payments.ts', {
      './prisma': { prisma: { report: { findUnique: async () => report }, payment: { findFirst: async () => { paymentReads++; return { id: ID }; } } } },
      './session': {}, './payhero': {}, './privacy-policy': policy,
    }, { process: { env: { NODE_ENV: 'development', FREE_REPORT_TESTING: 'true' } } });
    assert.equal(await payments.canDownload(ID, 'f'.repeat(48), OWNER), false);
    assert.equal(paymentReads, 0);
  }
});
