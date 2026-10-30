import { createRequire } from 'node:module';
import { PrismaClient } from '@offer-checker/prisma-client-v2';
import { memoryKeys, validFingerprint } from '../lib/scam-memory.ts';
import { reportStatus } from '../lib/scam-status.ts';

const require = createRequire(import.meta.url);
const { loadEnvConfig } = createRequire(require.resolve('next/package.json'))('@next/env');
loadEnvConfig(process.cwd(), false, { info() {}, error() {} });
const apply = process.argv.includes('--apply');
const prisma = new PrismaClient({ log: [] });
try {
  const where = { OR: [{ memoryIndexedAt: null }, { memoryIndexedAt: { isSet: false } }] };
  const count = await prisma.report.count({ where });
  console.log(`Reports awaiting memory indexing: ${count}. Mode: ${apply ? 'apply' : 'dry run'}.`);
  console.log('Administrator accounts available:', await prisma.user.count({ where: { role: 'ADMIN' } }));
  if (apply) {
    let updated = 0;
    while (true) {
      const batch = await prisma.report.findMany({ where, take: 100,
        select: { id: true, kind: true, entities: true, fingerprint: true, scamStatus: true, riskLevel: true, userReportedAt: true, reviewVersion: true, memoryConsent: true } });
      if (!batch.length) break;
      for (const report of batch) {
        const fingerprint = validFingerprint(report.fingerprint);
        const result = await prisma.report.updateMany({ where: { id: report.id, ...where }, data: {
          scamStatus: reportStatus(report), memoryIndicatorKeys: report.kind === "visa" || report.memoryConsent === false ? [] : memoryKeys(report.entities), memoryBands: report.kind === "visa" || report.memoryConsent === false ? [] : fingerprint?.bands ?? [],
          memoryIndexedAt: new Date(), reviewVersion: report.reviewVersion ?? 0,
          // Old scores may already include memory. Do not treat them as independent confirmations.
          memoryAutoEligible: false,
        } });
        updated += result.count;
      }
    }
    console.log(`Indexed ${updated} reports. No original scores, contents, or review decisions were changed.`);
  }
} catch (error) {
  console.error('Memory indexing failed:', error.code || error.name);
  process.exitCode = 1;
} finally {
  await prisma.$disconnect();
}
