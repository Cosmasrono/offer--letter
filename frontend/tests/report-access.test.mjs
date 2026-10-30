import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const ID = 'a'.repeat(24);
const TOKEN = 'b'.repeat(48);
const PRIVATE = 'PRIVATE FINDINGS MUST STAY SERVER SIDE';
function loadSource(path, modules, suffix = '', globals = {}) {
  const source = readFileSync(new URL(path, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const exports = {};
  vm.runInNewContext(code + suffix, {
    exports, require: id => id in modules ? modules[id] : id.endsWith('/privacy-policy') ? loadSource('../lib/privacy-policy.ts', {}) : require(id),
    Response, Request, File, FormData, URL, process, Buffer, console: { error() {} }, ...globals,
  });
  return exports;
}
function loadScan({ database = true, saved = ID, text = 'Readable letter', backendUp = true, upstreamStatus = 200, credit = null, claim = true, retention = true } = {}) {
  const calls = { analysed: 0, claimed: 0, privacy: null, cookies: [] };
  // Supply fetch separately because it is a global in the route.
  const source = readFileSync(new URL('../app/api/analyze/route.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 } }).outputText;
  const exports = {};
  const modules = {
    '@/lib/visa-upload': loadSource('../lib/visa-upload.ts', {}),
    'next/headers': { cookies: async () => ({ set: (...args) => calls.cookies.push(args) }) },
    '@/lib/privacy-policy': loadSource('../lib/privacy-policy.ts', {}),
    '@/lib/report-privacy': { ensureReportRetention: async () => { if (!retention) throw new Error('unavailable'); }, managementToken: async () => 'c'.repeat(64), hashManagementToken: () => 'd'.repeat(64) },
    '@/lib/backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({}) },
    '@/lib/payments': { findCheckCredit: async () => credit, spendCheckCredit: async () => { calls.claimed++; return claim; } },
    '@/lib/prisma': { isDatabaseConfigured: () => database },
    '@/lib/session': { getCurrentUser: async () => null },
    '@/lib/reports': { applyCommunityReports: async r => r, saveReport: async (_r, _u, _b, privacy) => { calls.privacy = privacy; return saved; } },
    '@/lib/memory-assessment': { explainMemoryMatches: async r => r },
  };
  vm.runInNewContext(code, { exports, require: id => modules[id], Response, File, FormData, process, console: { error() {} }, fetch: async () => {
    calls.analysed++;
    if (!backendUp) throw new Error('offline');
    return Response.json({ text_excerpt: text, summary: PRIVATE, findings: [{ detail: PRIVATE }], warnings: [], checks_not_run: [], detail: PRIVATE }, { status: upstreamStatus });
  }});
  return { ...exports, calls };
}
function upload(legacy = false) {
  const form = new FormData();
  form.set('consentVersion', '2026-10-29');
  form.set('processingConsent', 'true');
  form.set('submissionAuthority', 'true');
  form.set('file', new File(['letter'], 'letter.txt'));
  if (legacy) { form.set('paymentId', ID); form.set('paymentToken', TOKEN); }
  return new Request('https://example.com/api/analyze', { method: 'POST', headers: { 'X-Consent-Version': '2026-10-29' }, body: form });
}

test('missing, stale and incomplete consent never forwards documents for analysis', async () => {
  for (const variant of ['header', 'version', 'processing', 'authority']) {
    const route = loadScan();
    const original = upload();
    const form = await original.formData();
    if (variant === 'version') form.set('consentVersion', 'old');
    if (variant === 'processing') form.delete('processingConsent');
    if (variant === 'authority') form.delete('submissionAuthority');
    const request = new Request(original.url, { method: 'POST', body: form, headers: variant === 'header' ? {} : { 'X-Consent-Version': '2026-10-29' } });
    assert.equal((await route.POST(request)).status, 400);
    assert.equal(route.calls.analysed, 0);
    assert.equal(route.calls.privacy, null);
  }
});

test('retention failure stops processing; successful scans record choices and a secure management cookie', async () => {
  const blocked = loadScan({ retention: false });
  assert.equal((await blocked.POST(upload())).status, 503);
  assert.equal(blocked.calls.analysed, 0);
  const route = loadScan();
  assert.equal((await route.POST(upload())).status, 200);
  assert.equal(route.calls.privacy.consentVersion, '2026-10-29');
  assert.equal(route.calls.privacy.memoryConsent, false);
  assert.equal(route.calls.privacy.expiresAt - route.calls.privacy.consentedAt, 30 * 86400000);
  assert.equal(route.calls.privacy.managementTokenHash, 'd'.repeat(64));
  assert.equal(route.calls.cookies[0][2].httpOnly, true);
  assert.equal(route.calls.cookies[0][2].sameSite, 'lax');
});

test('scan first: unpaid scans run but return only a locked report ID', async () => {
  const { POST, calls } = loadScan();
  const response = await POST(upload());
  assert.equal(response.status, 200);
  assert.equal(calls.analysed, 1);
  assert.deepEqual(await response.json(), { id: ID, report: null });
  assert.match(response.headers.get('cache-control'), /no-store/);
});
test('storage failures and upstream failures never expose findings', async () => {
  for (const options of [{ database: false }, { saved: null }, { backendUp: false }, { upstreamStatus: 400 }]) {
    const { POST } = loadScan(options);
    const response = await POST(upload());
    assert.ok(response.status >= 400);
    assert.equal((await response.text()).includes(PRIVATE), false);
  }
});
test('unreadable scans do not ask for payment or expose a report', async () => {
  const { POST, calls } = loadScan({ text: '' });
  const response = await POST(upload());
  assert.equal(response.status, 422);
  assert.match((await response.json()).error, /not been charged/);
  assert.equal(calls.claimed, 0);
});
test('unrecognized files are flagged before analysis and unreadable upstream files never expose a verdict', async () => {
  const route = loadScan();
  const form = new FormData();
  form.set('file', new File(['not supported'], 'offer.exe'));
  form.set('consentVersion', '2026-10-29'); form.set('processingConsent', 'true'); form.set('submissionAuthority', 'true');
  const response = await route.POST(new Request('https://example.com/api/analyze', { method: 'POST', body: form, headers: { 'X-Consent-Version': '2026-10-29' } }));
  assert.equal(response.status, 415);
  assert.equal((await response.json()).code, 'DOCUMENT_NOT_CHECKED');
  assert.equal(route.calls.analysed, 0);
  const corrupt = loadScan({ upstreamStatus: 422 });
  const flagged = await corrupt.POST(upload());
  const body = await flagged.json();
  assert.equal(body.code, 'DOCUMENT_NOT_CHECKED');
  assert.match(body.error, /Not checked/);
  assert.equal(JSON.stringify(body).includes(PRIVATE), false);
});
test('unused legacy payments unlock only if the one-time credit is successfully claimed', async () => {
  for (const claim of [true, false]) {
    const { POST } = loadScan({ credit: { id: ID, token: TOKEN }, claim });
    const body = await (await POST(upload(true))).json();
    assert.equal(body.report, null);
    assert.equal(body.token, claim ? TOKEN : undefined);
  }
});

function loadPayments({ payment = null, providerStatus = 'QUEUED', promptError = null, environment = null } = {}) {
  const calls = { provider: 0, markedPaid: 0, prompts: [] };
  let record = payment ? { createdAt: new Date(), lastCheckedAt: null, ...payment } : null;
  const prisma = { report: { findUnique: async () => ({ id: ID, userId: null }) }, payment: {
    count: async () => 0,
    create: async ({ data }) => (record = { id: ID, createdAt: new Date(), lastCheckedAt: null, ...data }),
    findFirst: async ({ where }) => {
      if (!record || record.status !== where.status || record.reportId !== where.reportId) return null;
      if (where.amount?.gt === 0 && !(record.amount > 0)) return null;
      if (where.downloadToken && record.downloadToken !== where.downloadToken) return null;
      if (where.userId && record.userId !== where.userId) return null;
      return record;
    },
    findUnique: async () => record,
    update: async ({ data }) => Object.assign(record, data),
    updateMany: async ({ data }) => { calls.markedPaid++; Object.assign(record, data); return { count: 1 }; },
  }};
  const payments = loadSource('../lib/payments.ts', {
    './prisma': { prisma }, './session': { canViewReport: () => true },
    './payhero': {
      PayHeroError: class extends Error {},
      isPayHeroConfigured: () => true,
      stkPush: async input => {
        calls.prompts.push(input);
        if (promptError) throw promptError;
        return { reference: 'TEST', checkoutRequestId: 'CHECK' };
      },
      transactionStatus: async () => { calls.provider++; return { status: providerStatus, receipt: 'TEST' }; },
    },
  }, '', environment ? { process: { env: { ...process.env, ...environment } } } : {});
  return { ...payments, calls, get record() { return record; } };
}
test('explicit development testing opens findings and PDFs without creating a payment or prompt', async () => {
  const payment = loadPayments({ environment: { NODE_ENV: 'development', FREE_REPORT_TESTING: 'true' } });
  assert.equal(payment.reportPriceKes(), 0);
  assert.equal(await payment.canDownload(ID, '', null), true);
  await assert.rejects(payment.startPayment(ID, '0712345678', null), /no payment is needed/);
  assert.equal(payment.record, null);
  assert.equal(payment.calls.prompts.length, 0);
});
test('free testing never bypasses production payment or activates without an explicit development flag', async () => {
  for (const [NODE_ENV, FREE_REPORT_TESTING] of [['production', 'true'], ['test', 'true'], ['development', 'false'], ['development', ''], ['', 'true']]) {
    const payment = loadPayments({ environment: { NODE_ENV, FREE_REPORT_TESTING, REPORT_PRICE_KES: '50' } });
    assert.equal(payment.reportPriceKes(), 50);
    assert.equal(await payment.canDownload(ID, '', null), false);
  }
});
test('missing, zero and invalid prices cannot enable free access', t => {
  const before = process.env.REPORT_PRICE_KES;
  t.after(() => { if (before === undefined) delete process.env.REPORT_PRICE_KES; else process.env.REPORT_PRICE_KES = before; });
  const { reportPriceKes } = loadPayments();
  for (const value of ['', '0', '-10', 'NaN', 'Infinity']) {
    process.env.REPORT_PRICE_KES = value;
    assert.equal(reportPriceKes(), 50);
  }
  process.env.REPORT_PRICE_KES = '75';
  assert.equal(reportPriceKes(), 75);
  process.env.REPORT_PRICE_KES = '1';
  assert.equal(reportPriceKes(), 1);
});

test('KES 1 payment success unlocks the report; failure keeps findings and PDF locked', async t => {
  const before = process.env.REPORT_PRICE_KES;
  t.after(() => { if (before === undefined) delete process.env.REPORT_PRICE_KES; else process.env.REPORT_PRICE_KES = before; });
  process.env.REPORT_PRICE_KES = '1';
  for (const providerStatus of ['FAILED', 'SUCCESS']) {
    const payment = loadPayments({ providerStatus });
    const started = await payment.startPayment(ID, '+254712345678', null);
    assert.equal(started.status, 'PENDING');
    assert.equal(payment.record.amount, 1);
    assert.equal(payment.calls.prompts[0].amount, 1);
    assert.equal(payment.calls.prompts[0].phone, '0712345678');
    assert.equal(await payment.canDownload(ID, TOKEN, null), false);

    const result = await payment.checkPayment(started.paymentId);
    assert.equal(result.status, providerStatus);
    if (providerStatus === 'SUCCESS') {
      assert.match(result.downloadToken, /^[a-f0-9]{48}$/);
      assert.equal(await payment.canDownload(ID, result.downloadToken, null), true);
    } else {
      assert.equal(result.downloadToken, undefined);
      assert.match(result.message, /cancelled or did not go through/);
      assert.equal(await payment.canDownload(ID, TOKEN, null), false);
    }
  }
});

test('a failed KES 1 prompt is recorded as failed and cannot unlock the report', async t => {
  const before = process.env.REPORT_PRICE_KES;
  t.after(() => { if (before === undefined) delete process.env.REPORT_PRICE_KES; else process.env.REPORT_PRICE_KES = before; });
  process.env.REPORT_PRICE_KES = '1';
  const payment = loadPayments({ promptError: new Error('Provider unavailable') });
  await assert.rejects(payment.startPayment(ID, '0712345678', null), /could not be sent/);
  assert.equal(payment.record.amount, 1);
  assert.equal(payment.record.status, 'FAILED');
  assert.equal(payment.record.downloadToken, undefined);
  assert.equal(await payment.canDownload(ID, TOKEN, null), false);
});
test('owners and admins cannot bypass payment; tokens must match a successful payment', async () => {
  for (const status of ['PENDING', 'FAILED', 'SUCCESS']) {
    const { canDownload } = loadPayments({ payment: { id: ID, reportId: ID, downloadToken: TOKEN, status, amount: 50, userId: 'owner' } });
    assert.equal(await canDownload(ID, TOKEN, null), status === 'SUCCESS');
    assert.equal(await canDownload(ID, '', { id: 'owner', isAdmin: false }), status === 'SUCCESS');
    assert.equal(await canDownload(ID, '', { id: 'admin', isAdmin: true }), false);
    assert.equal(await canDownload(ID, 'c'.repeat(48), null), false);
    assert.equal(await canDownload('d'.repeat(24), TOKEN, null), false);
  }
});
test('old zero-value payments cannot unlock findings or a PDF', async () => {
  const { canDownload } = loadPayments({ payment: { id: ID, reportId: ID, downloadToken: TOKEN, status: 'SUCCESS', amount: 0, userId: 'owner' } });
  assert.equal(await canDownload(ID, TOKEN, null), false);
  assert.equal(await canDownload(ID, '', { id: 'owner' }), false);
});
test('only provider-confirmed success creates an unlock token', async () => {
  for (const providerStatus of ['QUEUED', 'FAILED', 'SUCCESS']) {
    const { checkPayment, calls } = loadPayments({ payment: { id: ID, reportId: ID, status: 'PENDING', providerReference: 'TEST', purpose: 'REPORT' }, providerStatus });
    const result = await checkPayment(ID);
    assert.equal(calls.provider, 1);
    assert.equal(calls.markedPaid, providerStatus === 'SUCCESS' ? 1 : 0);
    assert.equal(Boolean(result.downloadToken), providerStatus === 'SUCCESS');
  }
});

function reportPage({ paid = false, allowed = true, user = null } = {}) {
  return loadSource('../app/report/[id]/page.tsx', {
    'next/link': { default: 'a' }, 'next/navigation': { notFound() { throw new Error('NOT_FOUND'); } },
    '@/components/ReportView': { ReportView: 'ReportView' }, '@/components/ReportPayment': { ReportPayment: 'ReportPayment' },
    '@/components/OfferConfirmationForm': { OfferConfirmationForm: 'OfferConfirmationForm' },
    '@/components/ReportPrivacy': { ReportPrivacy: 'ReportPrivacy' },
    '@/components/RecentReports': { RecentReports: 'RecentReports', RememberReportRisk: 'RememberReportRisk' },
    '@/components/UploadForm': { UploadForm: 'UploadForm' },
    '@/lib/report-privacy': { canManageReport: async () => false },
    '@/lib/payments': { canDownload: async () => paid, paymentsReady: () => true, reportPriceKes: () => 50 },
    '@/lib/prisma': { isDatabaseConfigured: () => true, prisma: { report: { findUnique: async () => ({ id: ID, summary: PRIVATE, findings: PRIVATE, createdAt: new Date() }) } } },
    '@/lib/reports': { isObjectId: () => true, toAnalysisReport: r => r },
    '@/lib/session': { canViewReport: () => allowed, getCurrentUser: async () => user },
  }, '\nexports.testSavedReport = SavedReport;');
}
test('unpaid report rendering passes no findings or score to the client payment popup', async () => {
  const { testSavedReport } = reportPage();
  const element = await testSavedReport({ params: Promise.resolve({ id: ID }), searchParams: Promise.resolve({}) });
  const payment = element.props.children[0];
  assert.equal(payment.type, 'ReportPayment');
  assert.equal(JSON.stringify(element).includes(PRIVATE), false);
  assert.equal(payment.props.reportId, ID);
});
test('paid report rendering receives findings only after server access succeeds', async () => {
  const { testSavedReport } = reportPage({ paid: true });
  const element = await testSavedReport({ params: Promise.resolve({ id: ID }), searchParams: Promise.resolve({ token: TOKEN }) });
  const view = element.props.children[0];
  assert.equal(view.type, 'ReportView');
  assert.equal(view.props.report.summary, PRIVATE);
});
test('private reports require their owner even with a paid token', async () => {
  const { testSavedReport } = reportPage({ paid: true, allowed: false });
  const element = await testSavedReport({ params: Promise.resolve({ id: ID }), searchParams: Promise.resolve({ token: TOKEN }) });
  assert.equal(JSON.stringify(element).includes(PRIVATE), false);
});
test('direct PDF requests cannot bypass the payment check', async () => {
  for (const paid of [false, true]) {
    const { GET } = loadSource('../app/api/report-pdf/route.ts', {
      '@/lib/backend': { BACKEND_URL: 'http://backend', backendHeaders: () => ({}) },
      '@/lib/payments': { canDownload: async () => paid },
      '@/lib/prisma': { isDatabaseConfigured: () => true, prisma: { report: { findUnique: async () => ({ createdAt: new Date() }) } } },
      '@/lib/reports': { isObjectId: () => true, toAnalysisReport: () => ({}) },
      '@/lib/session': { canViewReport: () => true, getCurrentUser: async () => null },
    }, '', { fetch: async () => new Response('PDF CONTENT', { headers: { 'Content-Type': 'application/pdf' } }) });
    const response = await GET(new Request(`https://example.com/api/report-pdf?id=${ID}`));
    assert.equal(response.status, paid ? 200 : 403);
  }
});
