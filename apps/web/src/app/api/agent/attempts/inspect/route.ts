import { NextRequest, NextResponse } from "next/server";
import { forwardToPlanningApi } from "@/lib/upstream";

export async function POST(request: NextRequest) {
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json({ detail: "JSON is required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 800) return NextResponse.json({ detail: "Request is too large." }, { status: 413 });
  let input: unknown;
  try { input = JSON.parse(raw); }
  catch { return NextResponse.json({ detail: "Invalid JSON." }, { status: 400 }); }
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return NextResponse.json({ detail: "Invalid request." }, { status: 422 });
  }
  const values = input as Record<string, unknown>;
  if (typeof values.attempt !== "string" || !/^[A-Za-z0-9_-]{1,80}$/.test(values.attempt) ||
      typeof values.goal !== "string" || !values.goal.trim() || values.goal.length > 400 ||
      (values.provider !== "rules" && values.provider !== "ollama")) {
    return NextResponse.json({ detail: "Invalid attempt, goal, or provider." }, { status: 422 });
  }
  return forwardToPlanningApi(`/api/agent/attempts/${values.attempt}/analyze`,
    JSON.stringify({ goal: values.goal, provider: values.provider }));
}
