import { NextResponse } from "next/server";

type Endpoint = "/api/catalog" | "/api/agent/proposals" | "/api/agent/reviews" | "/api/assets/status"
  | `/api/agent/attempts/${string}/analyze`
  | `/api/agent/attempts/${string}/improve`
  | `/api/agent/attempts/${string}/evaluate`
  | "/api/attempts"
  | `/api/attempts/${string}/launch`
  | `/api/attempts/${string}/status`
  | `/api/attempts/${string}/plan`;

export async function forwardToPlanningApi(endpoint: Endpoint, body?: string): Promise<NextResponse> {
  const token = process.env.UMR_AGENT_API_TOKEN;
  const apiUrl = process.env.UMR_AGENT_API_URL ?? "http://127.0.0.1:8000";
  if (!token || token.length < 32) {
    return NextResponse.json({ detail: "Planning API token is not configured." }, { status: 503 });
  }
  if (!/^https?:\/\/[^/]+$/.test(apiUrl)) {
    return NextResponse.json({ detail: "Planning API address is invalid." }, { status: 503 });
  }
  try {
    const upstream = await fetch(`${apiUrl}${endpoint}`, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(120_000),
    });
    const payload: unknown = await upstream.json();
    return NextResponse.json(payload, { status: upstream.status });
  } catch {
    return NextResponse.json({ detail: "Planning API is unavailable." }, { status: 502 });
  }
}
