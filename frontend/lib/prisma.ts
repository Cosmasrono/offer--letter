import { PrismaClient } from "@offer-checker/prisma-client-v2";

// Reuse one client across hot reloads in development.
const globalForPrisma = globalThis as unknown as { visaPrisma?: PrismaClient };

export const prisma = globalForPrisma.visaPrisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") globalForPrisma.visaPrisma = prisma;

export const isDatabaseConfigured = () => Boolean(process.env.DATABASE_URL);
