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
  vm.runInNewContext(code, { exports, require: id => id in modules ? modules[id] : require(id), Response, Request, FormData, File, AbortSignal, process, console: { error() {} }, ...globals });
  return exports;
}
const policy = load('../lib/privacy-policy.ts');
const upload = load('../lib/visa-upload.ts');
const ID = 'a'.repeat(24);
function form() {
  const data = new FormData();
  data.set('country', 'QA'); data.set('kind', 'visa');
  data.set('consentVersion', policy.CONSENT_VERSION); data.set('processingConsent', 'true'); data.set('submissionAuthority', 'true');
  data.set('file', new File(['Synthetic visa'], 'visa.txt'));
  data.set('offerFile', new File(['Synthetic offer'], 'offer.txt'));
  return data;
}
const request = (data = form()) => new Request('https://example.test/api/visa-preview', { method: 'POST', headers: { 'X-Consent-Version': policy.CONSENT_VERSION }, body: data });

test('visa uploads reject unsupported countries, empty files and unsupported offer/visa types', () => {
  assert.equal(upload.validateVisaUpload(form()), null);
  for (const [key, value] of [['country', 'AE'], ['file', new File(['x'], 'visa.eml')], ['offerFile', new File([], 'empty.pdf')], ['offerFile', new File(['x'], 'script.exe')]]) {
    const data = form(); data.set(key, value);
    assert.ok(upload.validateVisaUpload(data));
  }
});

function previewRoute({ limited = false, retention = true, upstreamStatus = 200 } = {}) {
  const calls = [];
  const api = load('../app/api/visa-preview/route.ts', {
    '@/lib/privacy-policy': policy, '@/lib/visa-upload': upload,
    '@/lib/backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({ 'X-Api-Key': 'test-only' }) },
    '@/lib/prisma': { isDatabaseConfigured: () => true },
    '@/lib/report-privacy': { ensureReportRetention: async () => { if (!retention) throw new Error('unavailable'); } },
    '@/lib/rate-limit': { clientIp: async () => 'test-IP', isRateLimited: async () => limited, recordAttempt: async () => {} },
  }, { fetch: async (url, options) => { calls.push({ url, options }); return Response.json({ country: 'QA', details: { holder_name: 'TEST PERSON' }, findings: undefined }, { status: upstreamStatus }); } });
  return { ...api, calls };
}

test('preview rejects consent, retention and rate-limit failures before forwarding document contents', async () => {
  for (const variant of ['consent', 'retention', 'rate']) {
    const route = previewRoute({ limited: variant === 'rate', retention: variant !== 'retention' });
    const data = form(); if (variant === 'consent') data.delete('processingConsent');
    assert.equal((await route.POST(request(data))).status, variant === 'consent' ? 400 : variant === 'retention' ? 503 : 429);
    assert.equal(route.calls.length, 0);
  }
});

test('preview forwards the two documents privately and does not create an assessment', async () => {
  const route = previewRoute();
  const response = await route.POST(request());
  assert.equal(response.status, 200);
  assert.match(response.headers.get('cache-control'), /no-store/);
  assert.equal((await response.json()).details.holder_name, 'TEST PERSON');
  assert.equal(route.calls[0].url, 'http://backend/visa/preview');
  assert.equal(route.calls[0].options.body.get('offer_file').name, 'offer.txt');
  assert.equal(route.calls[0].options.headers['X-Api-Key'], 'test-only');
  const unreadable = previewRoute({ upstreamStatus: 422 });
  assert.equal((await unreadable.POST(request())).status, 422);
});

test('visa analysis requires reviewed fields, forwards them, and keeps findings locked without invoking scam memory', async () => {
  let analysed = 0;
  let saved;
  const route = load('../app/api/analyze/route.ts', {
    '@/lib/privacy-policy': policy, '@/lib/visa-upload': upload,
    '@/lib/backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({}) },
    '@/lib/payments': {}, '@/lib/prisma': { isDatabaseConfigured: () => true }, '@/lib/session': { getCurrentUser: async () => null },
    'next/headers': { cookies: async () => ({ set() {} }) },
    '@/lib/report-privacy': { ensureReportRetention: async () => {}, managementToken: async () => 'b'.repeat(64), hashManagementToken: () => 'c'.repeat(64) },
    '@/lib/reports': { applyCommunityReports: () => { throw new Error('Visa must not use community memory'); }, saveReport: async report => { saved = report; return ID; } },
    '@/lib/memory-assessment': { explainMemoryMatches: () => { throw new Error('Visa must not use AI memory'); } },
  }, { fetch: async (_url, options) => { analysed++; assert.equal(JSON.parse(options.body.get('visa_review')).reviewed, true); assert.ok(options.body.get('offer_file') instanceof File); return Response.json({ kind: 'visa', text_excerpt: 'private visa text', score: 90, risk_level: 'HIGH', visa: { official_status: 'NOT_CHECKED' } }); } });
  assert.equal((await route.POST(request())).status, 400);
  assert.equal(analysed, 0);
  const data = form(); data.set('visaReview', JSON.stringify({ reviewed: true, details: {}, offer_details: {} }));
  const response = await route.POST(request(data));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { id: ID, report: null });
  assert.equal(saved.kind, 'visa');
  assert.equal(saved.visa.official_status, 'NOT_CHECKED');
});

test('visa verification completeness can never report full government verification', () => {
  const { verificationSummary } = load('../lib/verification.ts');
  const summary = verificationSummary({ kind: 'visa', visa: { comparisons: [{ field: 'Holder name', status: 'MATCHED', detail: 'Values match only.' }] } });
  assert.equal(summary.level, 'PARTIAL');
  assert.equal(summary.items[0].status, 'UNVERIFIED');
  assert.equal(summary.items[0].id, 'government');
});
