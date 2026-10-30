// Run against a local development server. Uses synthetic documents only; no AI calls or payments.
// PLAYWRIGHT_MODULE can point to a previously installed Playwright package.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { createHash, randomBytes } from 'node:crypto';
import { PrismaClient } from '@offer-checker/prisma-client-v2';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { loadEnvConfig } = createRequire(require.resolve('next/package.json'))('@next/env');
loadEnvConfig(process.cwd(), true, { info() {}, error() {} });
const baseURL = process.env.PRIVACY_TEST_URL || 'http://localhost:3000';
const prisma = new PrismaClient({ log: [] });
const ids = [];
const browser = await chromium.launch({ headless: true });
try {
  await mkdir('artifacts/privacy', { recursive: true });
  const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  const failures = [];
  page.on('pageerror', error => failures.push(error.message));
  await page.goto('/');
  await page.getByRole('heading', { name: 'Your document. Your choice.' }).waitFor();
  assert.equal(await page.getByLabel('Choose an offer letter file').count(), 0);
  const accept = page.getByRole('button', { name: 'Agree and continue' });
  assert.equal(await accept.isDisabled(), true);
  assert.equal(await page.getByRole('checkbox').count(), 3);
  assert.equal(await page.getByRole('checkbox').nth(2).isChecked(), false);
  await page.screenshot({ path: 'artifacts/privacy/consent-desktop.png', fullPage: true });
  await page.getByRole('checkbox').nth(0).check();
  assert.equal(await accept.isDisabled(), true);
  await page.getByRole('checkbox').nth(1).check();
  await accept.click();
  await page.getByLabel('Choose an offer letter file').setInputFiles({ name: 'synthetic-offer.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic test document. No personal information.') });
  let submitted = false;
  await page.route('**/api/analyze', async route => {
    submitted = true;
    assert.equal(route.request().headers()['x-consent-version'], '2026-10-29');
    const body = route.request().postData();
    assert.match(body, /name="processingConsent"\r\n\r\ntrue/);
    assert.match(body, /name="submissionAuthority"\r\n\r\ntrue/);
    assert.match(body, /name="memoryConsent"\r\n\r\nfalse/);
    await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Synthetic test: scanning is unavailable.' }) });
  });
  await page.getByRole('button', { name: 'Scan my letter' }).click();
  await page.getByRole('alert').filter({ hasText: 'Synthetic test' }).waitFor();
  assert.equal(submitted, true);
  await page.getByRole('button', { name: 'Review choices' }).click();
  assert.equal(await page.getByRole('checkbox').nth(0).isChecked(), false);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'artifacts/privacy/consent-mobile.png', fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.goto('/privacy');
  await page.getByRole('heading', { name: 'Privacy and your documents', exact: true }).waitFor();
  await page.screenshot({ path: 'artifacts/privacy/privacy-mobile.png', fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  const noConsent = await context.request.post('/api/analyze', { multipart: { file: { name: 'test.txt', mimeType: 'text/plain', buffer: Buffer.from('Synthetic document') } } });
  assert.equal(noConsent.status(), 400);
  console.log('Consent, optional sharing, server rejection, mobile layout and privacy page: passed.');

  if (process.argv.includes('--database')) {
    await prisma.$runCommandRaw({ createIndexes: 'Report', indexes: [{ key: { expiresAt: 1 }, name: 'Report_privacy_expiry', expireAfterSeconds: 0 }] });
    const indexes = await prisma.$runCommandRaw({ listIndexes: 'Report' });
    assert.ok(indexes.cursor.firstBatch.some(index => index.name === 'Report_privacy_expiry' && index.expireAfterSeconds === 0));
    const token = randomBytes(32).toString('hex');
    const fixture = expiresAt => ({ userId: null, fileName: 'privacy-smoke-test.txt', kind: 'letter', riskLevel: 'LOW', score: 0, summary: 'Synthetic privacy test only.', findings: [], advice: [], verifyLinks: [], entities: { emails: [], phones: [], urls: [], domains: [], money: [], fee_mentions: [], payment_accounts: [], company_name: null, job_title: null, agency_name: null, agency_licence: null }, textExcerpt: 'Synthetic test; no real personal information.', extractionMethod: 'plain-text', aiUsed: false, warnings: [], checksNotRun: [], consentVersion: '2026-10-29', consentedAt: new Date(), memoryConsent: false, managementTokenHash: createHash('sha256').update(token).digest('hex'), expiresAt });
    const current = await prisma.report.create({ data: fixture(new Date(Date.now() + 600000)) }); ids.push(current.id);
    const expired = await prisma.report.create({ data: fixture(new Date(Date.now() - 1000)) }); ids.push(expired.id);
    await context.addCookies([{ name: 'olc_report_management', value: token, url: baseURL, httpOnly: true, sameSite: 'Lax' }]);
    const stranger = await browser.newContext({ baseURL });
    const otherPage = await stranger.newPage();
    await otherPage.goto(`/report/${current.id}`);
    assert.equal(await otherPage.getByRole('button', { name: 'Delete this report', exact: true }).count(), 0);
    const reportResponse = await page.goto(`/report/${current.id}`);
    assert.equal(reportResponse.status(), 200, 'Synthetic report should load');
    await page.screenshot({ path: 'artifacts/privacy/report-management.png', fullPage: true });
    const modal = page.getByRole('dialog');
    if (await modal.isVisible()) await page.getByRole('button', { name: /close/i }).first().click();
    await page.getByRole('button', { name: 'Delete this report', exact: true }).click();
    await page.getByRole('button', { name: 'Keep report', exact: true }).click();
    assert.ok(await prisma.report.findUnique({ where: { id: current.id } }));
    await page.getByRole('button', { name: 'Delete this report', exact: true }).click();
    await page.getByRole('button', { name: 'Yes, delete permanently' }).click();
    await page.getByRole('heading', { name: 'Your report has been deleted' }).waitFor();
    assert.equal(await prisma.report.findUnique({ where: { id: current.id } }), null);
    for (const id of [current.id, expired.id]) {
      // Next.js can stream a not-found boundary after the initial HTTP 200 headers.
      const missing = await context.request.get(`/report/${id}`);
      assert.ok([200, 404].includes(missing.status()));
      const html = await missing.text();
      assert.match(html, /404|could not be found/);
      assert.equal(html.includes('Synthetic privacy test only.'), false);
      assert.equal((await context.request.get(`/api/report-pdf?id=${id}`)).status(), 404);
    }
    await stranger.close();
    console.log('Live MongoDB TTL configuration, guest deletion, cancellation, expired/deleted report and PDF access: passed.');
  }
  assert.deepEqual(failures, []);
  await context.close();
} finally {
  await browser.close();
  try { if (ids.length) await prisma.report.deleteMany({ where: { id: { in: ids } } }); }
  finally { await prisma.$disconnect(); }
}
