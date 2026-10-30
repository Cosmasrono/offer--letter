import { BACKEND_URL, backendHeaders } from "@/lib/backend";
import { getCurrentUser } from "@/lib/session";

async function forward(method: "GET" | "POST", body?: FormData) {
  try {
    const response = await fetch(`${BACKEND_URL}/verification/nea`, {
      method, headers: backendHeaders(), body, cache: "no-store", signal: AbortSignal.timeout(20_000),
    });
    const data = await response.json();
    if (!response.ok) {
      return Response.json({ error: response.status === 400 && typeof data.detail === "string"
        ? data.detail : "Registry maintenance is unavailable. Check the backend connection and shared key." }, { status: response.status === 400 ? 400 : 503 });
    }
    return Response.json(data, { headers: { "Cache-Control": "private, no-store" } });
  } catch {
    return Response.json({ error: "The registry service could not be reached. Please try again." }, { status: 503 });
  }
}

export async function GET() {
  if (!(await getCurrentUser())?.isAdmin) return Response.json({ error: "Administrator access required." }, { status: 403 });
  return forward("GET");
}

export async function POST(request: Request) {
  if (!(await getCurrentUser())?.isAdmin) return Response.json({ error: "Administrator access required." }, { status: 403 });
  const form = await request.formData().catch(() => null);
  const file = form?.get("file");
  const retrievedAt = form?.get("retrieved_at");
  if (!(file instanceof File) || file.size === 0 || file.size > 8_000_000 || typeof retrievedAt !== "string") {
    return Response.json({ error: "Choose an NEA export smaller than 8 MB and its retrieval date." }, { status: 400 });
  }
  const date = new Date(retrievedAt);
  if (!Number.isFinite(date.getTime()) || date.getTime() > Date.now()) {
    return Response.json({ error: "Enter the actual retrieval date and time, which cannot be in the future." }, { status: 400 });
  }
  const body = new FormData();
  body.set("file", file);
  body.set("retrieved_at", date.toISOString());
  return forward("POST", body);
}
