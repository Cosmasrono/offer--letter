import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
function load(path, modules, globals = {}) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: id => id in modules ? modules[id] : id.endsWith('/privacy-policy') ? load('../lib/privacy-policy.ts', {}) : require(id),
    Response, Request, File, FormData, Date, AbortSignal, console: { error() {} }, ...globals });
  return exports;
}

function settingsRoute(user, backendResponse = { records: 1, fresh: true }) {
  const calls = [];
  const route = load('../app/api/verification/nea/route.ts', {
    '@/lib/backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({ 'X-Api-Key': 'test-key' }) },
    '@/lib/session': { getCurrentUser: async () => user },
  }, { fetch: async (url, options) => { calls.push({ url, options }); return Response.json(backendResponse); } });
  return { ...route, calls };
}

function upload(date = '2026-01-01T00:00:00Z') {
  const body = new FormData();
  body.set('file', new File(['agency_name,licence_number,expiry_date,status'], 'nea.csv'));
  body.set('retrieved_at', date);
  return new Request('https://example.test/api/verification/nea', { method: 'POST', body });
}

test('registry maintenance rejects guests and ordinary accounts before contacting the backend', async () => {
  for (const user of [null, { id: 'user', isAdmin: false }]) {
    const route = settingsRoute(user);
    assert.equal((await route.GET()).status, 403);
    assert.equal((await route.POST(upload())).status, 403);
    assert.equal(route.calls.length, 0);
  }
});

test('an administrator can read and import registry data through the authenticated backend connection', async () => {
  const route = settingsRoute({ id: 'admin', isAdmin: true });
  const status = await route.GET();
  assert.equal(status.status, 200);
  assert.match(status.headers.get('cache-control'), /no-store/);
  assert.equal(route.calls[0].options.headers['X-Api-Key'], 'test-key');
  const result = await route.POST(upload());
  assert.equal(result.status, 200);
  const request = route.calls.at(-1);
  assert.equal(request.options.method, 'POST');
  assert.ok(request.options.body.get('file') instanceof File);
  assert.equal(request.options.body.get('retrieved_at'), '2026-01-01T00:00:00.000Z');
});

test('bad dates and future dates cannot be submitted as registry evidence', async () => {
  const route = settingsRoute({ id: 'admin', isAdmin: true });
  for (const date of ['invalid', '2099-01-01T00:00:00Z']) assert.equal((await route.POST(upload(date))).status, 400);
  assert.equal(route.calls.length, 0);
});

test('source evidence survives saving and loading; old reports default to no evidence', async () => {
  let stored;
  const { saveReport: save, toAnalysisReport } = load('../lib/reports.ts', {
    './scam-memory': load('../lib/scam-memory.ts', { './scam-status': load('../lib/scam-status.ts', {}) }),
    './scam-status': load('../lib/scam-status.ts', {}),
    './offer-confirmation': load('../lib/offer-confirmation.ts', {}),
    './prisma': { prisma: { report: { create: async ({ data }) => { stored = data; return { id: 'a'.repeat(24) }; } } } },
    './session': { canViewReport: () => true },
  });
  const saveReport = report => save(report, null, undefined, { consentVersion: '2026-10-29', consentedAt: new Date(), memoryConsent: true, managementTokenHash: 'a'.repeat(64), expiresAt: new Date(Date.now() + 30 * 86400000) });
  const check = { check: 'employer', status: 'MATCHED', subject: 'Example', source_name: 'Companies House',
    source_url: 'https://find-and-update.company-information.service.gov.uk/company/12345678', checked_at: '2026-01-01T00:00:00Z', detail: 'A matching registry record does not authenticate the letter.' };
  await saveReport({ risk_level: 'LOW', findings: [], checks_not_run: [], entities: {}, source_checks: [check] });
  assert.equal(stored.sourceChecks[0].source_name, 'Companies House');
  assert.equal(toAnalysisReport({ ...stored, id: 'a'.repeat(24) }).source_checks[0].detail, check.detail);
  const website = { ...check, check: 'website', status: 'MISMATCH', source_name: 'Public website content',
    checked_pages: ['https://example.com/contact'], comparisons: [{ field: 'Company number', letter_value: '12345678', source_value: '87654321', status: 'MISMATCH', detail: 'Confirm the company numbers.' }] };
  await saveReport({ risk_level: 'MEDIUM', findings: [], checks_not_run: [], entities: {}, source_checks: [website] });
  const loaded = toAnalysisReport({ ...stored, id: 'a'.repeat(24) });
  assert.equal(loaded.source_checks[0].comparisons[0].source_value, '87654321');
  assert.equal(loaded.source_checks[0].checked_pages[0], 'https://example.com/contact');
  delete stored.sourceChecks;
  assert.equal(toAnalysisReport(stored).source_checks.length, 0);
});
