// Uses synthetic text documents against the local app. No AI calls, portal lookups or payments.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.VISA_TEST_URL || 'http://localhost:3000';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1100 } });
const ids = [];
try {
  await mkdir('artifacts/visa', { recursive: true });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const consent = async () => {
    await page.getByRole('checkbox').nth(0).check();
    await page.getByRole('checkbox').nth(1).check();
    await page.getByRole('button', { name: 'Agree and continue' }).click();
  };
  for (const country of ['QA', 'KW']) {
    await page.goto('/visa');
    await page.getByRole('heading', { name: 'Your document. Your choice.' }).waitFor();
    assert.equal(await page.locator('input[type=file]').count(), 0);
    if (country === 'QA') await page.screenshot({ path: 'artifacts/visa/consent-desktop.png', fullPage: true });
    await consent();
    await page.getByLabel('Issuing country').selectOption(country);
    const visa = `State of ${country === 'QA' ? 'Qatar' : 'Kuwait'}\nElectronic Visa\nVisa Number: 001234567890123\nHolder Name: TEST APPLICANT PERSON\nPassport Number: A00123456\nNationality: Kenya\nSponsor Name: Example Hospitality LLC\nProfession: Cook\nVisa Type: Work / Employment\nVisa Issue Date: 2019-01-15\nVisa Expiry Date: ${country === 'QA' ? '2030-12-31' : '2020-12-31'}\n`;
    await page.getByLabel('Visa or permit document').setInputFiles({ name: `synthetic-visa-${country}.txt`, mimeType: 'text/plain', buffer: Buffer.from(visa) });
    if (country === 'QA') await page.getByLabel('Offer letter to compare').setInputFiles({ name: 'synthetic-offer.txt', mimeType: 'text/plain', buffer: Buffer.from('Employee Name: TEST APPLICANT PERSON\nPassport Number: A00123456\nEmployer Name: Different Employer LLC\nJob Title: Cook\nSalary: QAR 2000\nThis is a fictional test offer.') });
    const previewResponse = page.waitForResponse(response => response.url().endsWith('/api/visa-preview'));
    await page.getByRole('button', { name: 'Read documents for review' }).click();
    const preview = await previewResponse;
    assert.equal(preview.status(), 200, `Preview failed: ${await preview.text()}`);
    await page.getByRole('heading', { name: 'Review the extracted details' }).waitFor();
    assert.equal(await page.locator('#visa-passport_number').inputValue(), 'A00123456');
    assert.equal(await page.locator('#visa-visa_number').inputValue(), '001234567890123');
    if (country === 'QA') {
      await page.locator('#visa-expiry_date').fill('2031-12-31');
      await page.screenshot({ path: 'artifacts/visa/review-desktop.png', fullPage: true });
    }
    await page.getByRole('checkbox', { name: /I checked these values/ }).check();
    const scanResponse = page.waitForResponse(response => response.url().endsWith('/api/analyze'));
    await page.getByRole('button', { name: /^Check visa/ }).click();
    const scan = await scanResponse;
    assert.equal(scan.status(), 200, `Scan failed: ${await scan.text()}`);
    const saved = await scan.json(); ids.push(saved.id);
    assert.equal(saved.report, null);
    await page.waitForURL(`**/report/${saved.id}`);
    await page.getByRole('heading', { name: 'Government status: not checked' }).waitFor();
    await page.getByRole('heading', { name: 'Offer and visa comparison' }).waitFor();
    if (country === 'QA') {
      await page.getByRole('heading', { name: 'Employer / sponsor · Values differ' }).waitFor();
      assert.ok(await page.getByText('Originally read: 2030-12-31', { exact: false }).count());
    } else {
      await page.getByText('High risk — visa validity or document differences', { exact: true }).waitFor();
      await page.getByText('The visa / entry validity date has passed', { exact: true }).waitFor();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: `artifacts/visa/report-${country}-mobile.png`, fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    const pdf = await context.request.get(`/api/report-pdf?id=${saved.id}`);
    assert.equal(pdf.status(), 200);
    assert.match(pdf.headers()['content-type'], /application\/pdf/);
    const content = await pdf.body();
    assert.equal(content.subarray(0, 4).toString(), '%PDF');
    await writeFile(`artifacts/visa/report-${country}.pdf`, content);
    await page.setViewportSize({ width: 1440, height: 1100 });
  }
  assert.deepEqual(errors, []);
  console.log('Qatar and Kuwait: consent, real extraction/review, corrections, comparisons, saved reports, mobile layout and PDF downloads passed.');
} finally {
  for (const id of ids) {
    const response = await context.request.delete('/api/report-privacy', { headers: { Origin: baseURL }, data: { id } });
    if (!response.ok()) { console.error('A synthetic report could not be removed:', id); process.exitCode = 1; }
  }
  await context.close();
  await browser.close();
}
