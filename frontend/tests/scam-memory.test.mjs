import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const ID = 'a'.repeat(24);
const ADMIN = { id: 'b'.repeat(24), isAdmin: true };
function load(path, modules = {}, globals = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: id => id in modules ? modules[id] : id.endsWith('/privacy-policy') ? load('../lib/privacy-policy.ts') : id.endsWith('/visa-upload') ? load('../lib/visa-upload.ts') : require(id),
    Date, Response, Request, File, FormData, URL, AbortSignal, process, console: { error() {} }, ...globals });
  return exports;
}
const helpers = load('../lib/scam-memory.ts');
const statuses = load('../lib/scam-status.ts');
const fingerprint = (value = 1) => ({ signature: Array(64).fill(value), bands: ['shared-band'] });
const report = (changes = {}) => ({ file_name: 'new.pdf', kind: 'letter', risk_level: 'LOW', score: 0,
  country: 'AE', country_name: 'UAE', company_name: 'Example Ltd', job_title: 'Tester', summary: 'Check directly.',
  findings: [], advice: [], verify_links: [], entities: { emails: ['scam@gmail.com'], phones: ['0712345678'], payment_accounts: [] },
  text_excerpt: 'CURRENT LETTER ONLY', extraction_method: 'plain-text', ai_used: false, warnings: [], checks_not_run: [],
  fingerprint: fingerprint(), ...changes });
const stored = (changes = {}) => ({ id: ID, scamStatus: 'CONFIRMED_SCAM', riskLevel: 'HIGH', score: 85, reviewVersion: 0,
  entities: report().entities, fingerprint: fingerprint(), memoryIndicatorKeys: helpers.memoryKeys(report().entities),
  memoryBands: ['shared-band'],
  memoryAutoEligible: false, createdAt: new Date(), summary: 'PRIVATE HISTORICAL LETTER', ...changes });

function matches(row, where) {
  return Object.entries(where).every(([key, expected]) => {
    if (key === 'AND') return expected.every(clause => matches(row, clause));
    if (key === 'OR') return expected.some(clause => matches(row, clause));
    if (expected && typeof expected === 'object') {
      if ('isSet' in expected) return Object.hasOwn(row, key) === expected.isSet;
      if ('in' in expected) return expected.in.includes(row[key]);
      if ('hasSome' in expected) return expected.hasSome.some(value => (row[key] ?? []).includes(value));
      if ('gt' in expected) return row[key] > expected.gt;
    }
    return row[key] === expected;
  });
}
function store(rows = [], { allowed = true, conflict = false } = {}) {
  const calls = { queries: [], writes: 0 };
  const prisma = { report: {
    findMany: async args => { calls.queries.push(args); return rows.filter(row => matches(row, args.where)).map(row => Object.fromEntries(Object.keys(args.select).map(key => [key, row[key]]))); },
    findUnique: async ({ where }) => rows.find(row => row.id === where.id) ?? null,
    updateMany: async ({ where, data }) => {
      if (conflict) return { count: 0 };
      let count = 0;
      for (const row of rows) if (matches(row, where)) { Object.assign(row, data); count++; calls.writes++; }
      return { count };
    },
    create: async ({ data }) => { const row = { ...data, id: String(rows.length + 1).padStart(24, '0'), createdAt: new Date() }; rows.push(row); return row; },
  } };
  const exports = load('../lib/reports.ts', { './prisma': { prisma }, './session': { canViewReport: () => allowed },
    './scam-memory': helpers, './scam-status': statuses, './offer-confirmation': load('../lib/offer-confirmation.ts') });
  return { ...exports, saveReport: (r, userId = null, baseline = undefined, memoryConsent = true) => exports.saveReport(r, userId, baseline, {
    consentVersion: '2026-10-29', consentedAt: new Date(), memoryConsent, managementTokenHash: 'a'.repeat(64), expiresAt: new Date(Date.now() + 30 * 86400000),
  }), rows, calls, prisma };
}

test('expired and opted-out source reports cannot contribute pattern matches', async () => {
  for (const changes of [{ expiresAt: new Date(Date.now() - 1000) }, { memoryConsent: false }]) {
    const memory = store([stored(changes)]);
    const result = await memory.applyCommunityReports(report());
    assert.equal(result.memory_matches.length, 0);
    assert.equal(result.risk_level, 'LOW');
  }
});

test('optional pattern sharing stays off through reporting and admin review', async () => {
  const memory = store();
  const id = await memory.saveReport(report({ risk_level: 'HIGH', score: 90 }), null, undefined, false);
  assert.equal(memory.rows[0].memoryIndicatorKeys.length, 0);
  assert.equal(memory.rows[0].memoryBands.length, 0);
  await memory.reportAsScam(id, null);
  await memory.reviewScam(id, 'CONFIRM_SCAM', 'Reviewed evidence', null, ADMIN);
  assert.equal(memory.rows[0].memoryConsent, false);
  assert.equal(memory.rows[0].memoryIndicatorKeys.length, 0);
  assert.equal(memory.rows[0].memoryBands.length, 0);
});

test('visa reports survive saving/loading but cannot become scam-memory sources', async () => {
  const memory = store();
  const visa = { details: { visa_number: '00123', passport_number: 'A00012' }, extracted_details: {}, comparisons: [], official_status: 'NOT_CHECKED' };
  const id = await memory.saveReport(report({ kind: 'visa', risk_level: 'HIGH', score: 90, visa }), null, undefined, true);
  const row = memory.rows[0];
  assert.equal(row.scamStatus, 'UNREVIEWED');
  assert.equal(row.memoryAutoEligible, false);
  assert.equal(row.memoryIndicatorKeys.length, 0);
  assert.equal(row.memoryBands.length, 0);
  assert.equal(memory.toAnalysisReport(row).kind, 'visa');
  assert.equal(memory.toAnalysisReport(row).visa.details.passport_number, 'A00012');
  await memory.reportAsScam(id, null);
  await memory.reviewScam(id, 'CONFIRM_SCAM', 'Reviewed independently', null, ADMIN);
  assert.equal(row.memoryIndicatorKeys.length, 0);
  assert.equal(row.memoryBands.length, 0);
});

test('confirmed scam wording and matching normalized contacts identify the reused letter', async () => {
  const memory = store([stored()]);
  const result = await memory.applyCommunityReports(report({ entities: { emails: [], phones: ['+254 712 345 678'], payment_accounts: [] } }));
  assert.equal(result.risk_level, 'HIGH');
  assert.equal(result.score, 60);
  assert.equal(result.memory_matches[0].status, 'CONFIRMED_SCAM');
  assert.equal(result.memory_matches[0].contact_and_template, true);
  assert.equal(JSON.stringify(result).includes('PRIVATE HISTORICAL LETTER'), false);
  assert.equal(memory.calls.queries[0].select.textExcerpt, undefined);
  assert.equal(memory.calls.queries[0].select.summary, undefined);
});

test('expired or unmatched sponsorship alone does not turn a historical document into an automatic scam-memory case', async () => {
  const memory = store();
  await memory.saveReport(report({ risk_level: 'HIGH', score: 60, findings: [{ id: 'cos_expired', points: 35, severity: 'high' },
    { id: 'sponsor_registry_not_found', points: 25, severity: 'high' }] }));
  assert.equal(memory.rows[0].memoryAutoEligible, false);
  assert.equal(memory.rows[0].scamStatus, 'UNREVIEWED');
  assert.equal(memory.rows[0].riskLevel, 'HIGH');
  await memory.saveReport(report({ risk_level: 'HIGH', score: 95, findings: [{ id: 'cos_expired', points: 35, severity: 'high' },
    { id: 'fee_request', points: 40, severity: 'critical' }] }));
  assert.equal(memory.rows[1].memoryAutoEligible, true);
});

test('a copied template without matching contacts warns but does not alone prove high risk', async () => {
  const memory = store([stored({ memoryIndicatorKeys: ['PHONE:254700000001'] })]);
  const result = await memory.applyCommunityReports(report({ entities: { emails: [], phones: [], payment_accounts: [] } }));
  assert.equal(result.risk_level, 'MEDIUM');
  assert.equal(result.memory_matches[0].contact_and_template, false);
});

test('contacts and wording from different historical cases are not combined into a strong match', async () => {
  const memory = store([stored({ fingerprint: fingerprint(2) }), stored({ id: 'c'.repeat(24), memoryIndicatorKeys: ['PHONE:254700000001'] })]);
  const result = await memory.applyCommunityReports(report());
  assert.equal(result.risk_level, 'MEDIUM');
  assert.equal(result.memory_matches[0].contact_and_template, false);
});

test('duplicate uploads do not become independent confirmations or increase the warning score', async () => {
  const one = await store([stored({ scamStatus: 'REPORTED_SCAM' })]).applyCommunityReports(report());
  const many = await store(Array.from({ length: 50 }, (_, i) => stored({ id: String(i), scamStatus: 'REPORTED_SCAM' }))).applyCommunityReports(report());
  assert.equal(one.score, many.score);
  assert.equal(many.memory_matches[0].case_count, 1);
  assert.equal(many.memory_matches[0].status, 'REPORTED_SCAM');
  assert.equal(many.risk_level, 'LOW');
});

test('memory-only high scores cannot feed back as independent automatic scam cases', async () => {
  const memory = store([stored()]);
  const enriched = await memory.applyCommunityReports(report());
  await memory.saveReport(enriched, null, { score: 0, riskLevel: 'LOW' });
  const saved = memory.rows.at(-1);
  assert.equal(saved.scamStatus, 'SUSPECTED_SCAM');
  assert.equal(saved.memoryAutoEligible, false);
  assert.equal(saved.baseScore, 0);
  assert.equal(saved.baseRiskLevel, 'LOW');
});

test('reporting a letter changes its status once while preserving its original scan result', async () => {
  const row = stored({ scamStatus: 'UNREVIEWED', riskLevel: 'LOW', score: 5 });
  const memory = store([row]);
  assert.equal(await memory.reportAsScam(ID, null), 'reported');
  assert.equal(await memory.reportAsScam(ID, null), 'already');
  assert.equal(row.scamStatus, 'REPORTED_SCAM');
  assert.equal(row.score, 5);
  assert.equal(memory.calls.writes, 1);
  assert.ok(row.memoryIndexedAt);
});

test('review decisions have an audit trail and clearing stops the case influencing later checks', async () => {
  const row = stored({ scamStatus: 'REPORTED_SCAM', userReportedAt: new Date() });
  const memory = store([row]);
  await memory.reviewScam(ID, 'CONFIRM_SCAM', 'Employer confirmed this offer was never issued.', 'https://example.test/evidence', ADMIN);
  assert.equal(row.scamStatus, 'CONFIRMED_SCAM');
  assert.equal(row.reviewHistory[0].from, 'REPORTED_SCAM');
  assert.equal(row.reviewHistory[0].reviewerId, ADMIN.id);
  assert.equal(row.score, 85);
  assert.equal((await memory.applyCommunityReports(report())).risk_level, 'HIGH');
  await memory.reviewScam(ID, 'CLEAR', 'Employer supplied evidence that the original complaint was mistaken.', null, ADMIN);
  assert.equal(row.scamStatus, 'CLEARED');
  assert.equal(row.reviewHistory.length, 2);
  const clean = await memory.applyCommunityReports(report());
  assert.equal(clean.memory_matches.length, 0);
  assert.equal(clean.score, 0);
  assert.equal(await memory.reportAsScam(ID, null), 'reviewed');
  assert.equal(row.scamStatus, 'CLEARED');
  await memory.reviewScam(ID, 'REOPEN', 'New evidence has arrived and the case needs investigation.', null, ADMIN);
  assert.equal(row.scamStatus, 'REPORTED_SCAM');
});

test('private reports and reviewed decisions cannot be changed by ordinary users or races', async () => {
  assert.equal(await store([stored()], { allowed: false }).reportAsScam(ID, null), 'missing');
  const memory = store([stored({ scamStatus: 'REPORTED_SCAM' })]);
  await assert.rejects(memory.reviewScam(ID, 'CONFIRM_SCAM', 'Evidence', null, { ...ADMIN, isAdmin: false }), /Administrator/);
  const racing = store([stored({ scamStatus: 'REPORTED_SCAM' })], { conflict: true });
  await assert.rejects(racing.reviewScam(ID, 'CLEAR', 'Evidence', null, ADMIN), /Another update/);
  assert.equal(racing.rows[0].reviewHistory, undefined);
});

test('corporate identities and shared paybills are not blacklisted; Kenyan phone formats agree', () => {
  const keys = helpers.memoryKeys({ emails: ['hr@real-company.test', 'SCAM@gmail.com'], phones: ['0712345678', '+254 712 345 678'], payment_accounts: ['paybill 247247', 'paybill 247247 account 778812'] });
  assert.equal(keys.filter(key => key.startsWith('PHONE:')).length, 1);
  assert.ok(keys.includes('EMAIL:scam@gmail.com'));
  assert.ok(keys.includes('PAYMENT:paybill 247247 account 778812'));
  assert.equal(keys.includes('PAYMENT:paybill 247247'), false);
  assert.equal(keys.some(key => key.includes('real-company')), false);
});

test('the admin review API requires role, same-origin requests and meaningful evidence', async () => {
  let user = null;
  let reviews = 0;
  const route = load('../app/api/scam-review/route.ts', {
    '@/lib/prisma': { isDatabaseConfigured: () => true, prisma: { report: { findUnique: async () => stored({ reviewHistory: [] }) } } },
    '@/lib/reports': { isObjectId: value => /^[a-f0-9]{24}$/.test(value), ReviewConflict: class extends Error {}, reviewScam: async () => { reviews++; return { scamStatus: 'CONFIRMED_SCAM' }; } },
    '@/lib/scam-status': statuses, '@/lib/session': { getCurrentUser: async () => user },
  });
  const request = (overrides = {}, origin = 'https://example.test') => new Request('https://example.test/api/scam-review', { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: origin }, body: JSON.stringify({ id: ID, action: 'CONFIRM_SCAM', note: 'Employer independently confirmed this offer is fraudulent.', ...overrides }) });
  assert.equal((await route.POST(request())).status, 403);
  user = { ...ADMIN, isAdmin: false };
  assert.equal((await route.GET(new Request('https://example.test/api/scam-review?id=' + ID))).status, 403);
  user = ADMIN;
  assert.equal((await route.POST(request({}, 'https://attacker.test'))).status, 403);
  assert.equal((await route.POST(request({ note: 'yes' }))).status, 400);
  assert.equal((await route.POST(request({ sourceUrl: 'javascript:alert(1)' }))).status, 400);
  assert.equal((await route.POST(request())).status, 200);
  assert.equal(reviews, 1);
  const history = await (await route.GET(new Request('https://example.test/api/scam-review?id=' + ID))).json();
  assert.equal(JSON.stringify(history).includes('PRIVATE HISTORICAL LETTER'), false);
});

test('AI context delivery cannot erase memory warnings when the provider is unavailable', async () => {
  const before = report({ score: 60, risk_level: 'HIGH', memory_matches: [{ status: 'CONFIRMED_SCAM', matching_details: ['PHONE:254712345678'], template_similarity: 1, case_count: 1 }] });
  const { explainMemoryMatches } = load('../lib/memory-assessment.ts', { './backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({}) } }, { fetch: async () => { throw new Error('offline'); } });
  const after = await explainMemoryMatches(before);
  assert.equal(after.score, 60);
  assert.equal(after.risk_level, 'HIGH');
  assert.equal(after.memory_matches.length, 1);
  assert.ok(after.warnings.length);
});

test('scan pipeline gives matching case evidence to AI, saves tracked status, and returns no unpaid findings', async () => {
  const memory = store([stored()]);
  const requests = [];
  const fetch = async (url, options) => {
    requests.push({ url, options });
    return url.endsWith('/analyze') ? Response.json(report()) : Response.json({ summary: 'CURRENT SCAN WITH CASE EVIDENCE', ai_used: true });
  };
  const assessment = load('../lib/memory-assessment.ts', { './backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({}) } }, { fetch });
  const route = load('../app/api/analyze/route.ts', {
    'next/headers': { cookies: async () => ({ set() {} }) },
    '@/lib/report-privacy': { ensureReportRetention: async () => {}, managementToken: async () => 'a'.repeat(64), hashManagementToken: () => 'b'.repeat(64) },
    '@/lib/backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({}) },
    '@/lib/payments': {}, '@/lib/prisma': { isDatabaseConfigured: () => true },
    '@/lib/session': { getCurrentUser: async () => null }, '@/lib/reports': memory,
    '@/lib/memory-assessment': assessment,
  }, { fetch });
  const body = new FormData();
  body.set('file', new File(['current-letter'], 'letter.txt'));
  body.set('consentVersion', '2026-10-29'); body.set('processingConsent', 'true'); body.set('submissionAuthority', 'true');
  const response = await route.POST(new Request('https://example.test/api/analyze', { method: 'POST', body, headers: { 'X-Consent-Version': '2026-10-29' } }));
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.report, null);
  assert.deepEqual(Object.keys(payload).sort(), ['id', 'report']);
  assert.equal(requests.length, 2);
  const context = JSON.parse(requests[1].options.body);
  assert.equal(context.memory_matches[0].status, 'CONFIRMED_SCAM');
  assert.equal(context.summary.includes('PRIVATE HISTORICAL LETTER'), false);
  const saved = memory.rows.at(-1);
  assert.equal(saved.scamStatus, 'SUSPECTED_SCAM');
  assert.equal(saved.memoryAutoEligible, false);
  assert.equal(saved.memoryMatches[0].status, 'CONFIRMED_SCAM');
  assert.equal(saved.summary, 'CURRENT SCAN WITH CASE EVIDENCE');
});
