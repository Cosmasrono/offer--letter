import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stkPush, transactionStatus, isPayHeroConfigured, isMockMode } from '../lib/payhero.ts';

test('PayHero configuration and API requests', async (t) => {
  const originalEnv = { ...process.env };
  const originalFetch = globalThis.fetch;
  t.after(() => { process.env = originalEnv; globalThis.fetch = originalFetch; });
  Object.assign(process.env, {
    PAYHERO_API_USERNAME: 'api-user', PAYHERO_API_PASSWORD: 'api-password',
    PAYHERO_CHANNEL_ID: '133', PAYHERO_MOCK: 'false',
    PAYHERO_CALLBACK_URL: 'https://example.com/api/mpesa/callback',
    PAYHERO_CALLBACK_SECRET: 'callback-secret',
  });
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return Response.json({ success: true, reference: 'REF1', CheckoutRequestID: 'CHECK1',
      status: 'SUCCESS', provider_reference: 'RECEIPT1' });
  };
  for (const base of ['https://backend.payhero.co.ke', 'https://backend.payhero.co.ke/api/v2/']) {
    process.env.PAYHERO_BASE_URL = base;
    const result = await stkPush({ amount: 1, phone: '0712345678', externalReference: 'ORDER1' });
    assert.equal(result.reference, 'REF1');
    const { url, options } = requests.at(-1);
    assert.equal(url, 'https://backend.payhero.co.ke/api/v2/payments');
    assert.equal(options.headers.Authorization, `Basic ${Buffer.from('api-user:api-password').toString('base64')}`);
    const body = JSON.parse(options.body);
    assert.equal(body.channel_id, 133);
    assert.equal(body.amount, 1);
    assert.equal(body.callback_url, 'https://example.com/api/mpesa/callback?secret=callback-secret');
    assert.deepEqual(await transactionStatus('REF1'), { status: 'SUCCESS', receipt: 'RECEIPT1' });
    assert.equal(requests.at(-1).url, 'https://backend.payhero.co.ke/api/v2/transaction-status?reference=REF1');
  }
  process.env.PAYHERO_CALLBACK_URL = 'http://localhost:3000/api/mpesa/callback';
  const count = requests.length;
  await assert.rejects(stkPush({ amount: 50, phone: '0712345678', externalReference: 'ORDER1' }), /public HTTPS/);
  assert.equal(requests.length, count);
  process.env.PAYHERO_CHANNEL_ID = 'invalid';
  assert.equal(isPayHeroConfigured(), false);
});

test('KES 1 mock payments stay pending before success or failure, without sending a prompt', async (t) => {
  const originalEnv = { ...process.env };
  const originalFetch = globalThis.fetch;
  t.after(() => { process.env = originalEnv; globalThis.fetch = originalFetch; });
  Object.assign(process.env, { NODE_ENV: 'development', PAYHERO_MOCK: 'true' });
  globalThis.fetch = async () => { throw new Error('Mock tests must not contact PayHero'); };
  t.mock.timers.enable({ apis: ['Date'], now: 1_800_000_000_000 });

  assert.equal(isMockMode(), true);
  const success = await stkPush({ amount: 1, phone: '0712345678', externalReference: 'TEST-SUCCESS' });
  const failure = await stkPush({ amount: 1, phone: '0700000000', externalReference: 'TEST-FAILURE' });
  assert.deepEqual(await transactionStatus(success.reference), { status: 'QUEUED', receipt: null });
  assert.deepEqual(await transactionStatus(failure.reference), { status: 'QUEUED', receipt: null });

  t.mock.timers.tick(6000);
  const paid = await transactionStatus(success.reference);
  assert.equal(paid.status, 'SUCCESS');
  assert.match(paid.receipt, /^MOCK/);
  assert.deepEqual(await transactionStatus(failure.reference), { status: 'FAILED', receipt: null });

  process.env.NODE_ENV = 'production';
  assert.equal(isMockMode(), false);
});
