// Calls to the Python backend. BACKEND_API_KEY must match the backend's, if it sets one.
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export const backendHeaders = (): Record<string, string> =>
  process.env.BACKEND_API_KEY ? { "X-Api-Key": process.env.BACKEND_API_KEY } : {};
