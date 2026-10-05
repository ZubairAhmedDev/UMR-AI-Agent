import { NextRequest, NextResponse } from "next/server";
import { forwardToPlanningApi } from "@/lib/upstream";

export async function POST(request: NextRequest, context: { params: Promise<{ attempt: string }> }) {
  const { attempt } = await context.params;
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(attempt)) {
    return NextResponse.json({ detail: "Invalid attempt ID." }, { status: 422 });
  }
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json({ detail: "JSON is required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 200) return NextResponse.json({ detail: "Request is too large." }, { status: 413 });
  let input: unknown;
  try { input = JSON.parse(raw); }
  catch { return NextResponse.json({ detail: "Invalid JSON." }, { status: 400 }); }
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return NextResponse.json({ detail: "Invalid approval." }, { status: 422 });
  }
  const values = input as Record<string, unknown>;
  if (Object.keys(values).join(",") !== "approved_plan_hash" ||
      typeof values.approved_plan_hash !== "string" || !/^[0-9a-f]{64}$/.test(values.approved_plan_hash)) {
    return NextResponse.json({ detail: "Approval requires the exact plan hash." }, { status: 422 });
  }
  return forwardToPlanningApi(`/api/attempts/${attempt}/launch`, raw);
}
