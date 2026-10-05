import { NextRequest, NextResponse } from "next/server";
import { forwardToPlanningApi } from "@/lib/upstream";

export async function POST(request: NextRequest) {
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json({ detail: "JSON is required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 500) return NextResponse.json({ detail: "Request is too large." }, { status: 413 });
  let input: unknown;
  try { input = JSON.parse(raw); }
  catch { return NextResponse.json({ detail: "Invalid JSON." }, { status: 400 }); }
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return NextResponse.json({ detail: "Invalid request." }, { status: 422 });
  }
  const values = input as Record<string, unknown>;
  if (Object.keys(values).sort().join(",") !== "attempt,max_frames,motion_id" ||
      typeof values.attempt !== "string" || !/^[A-Za-z0-9_-]{1,80}$/.test(values.attempt) ||
      !["spin-kick", "run", "speed-vault"].includes(String(values.motion_id)) ||
      (values.max_frames !== 0 && values.max_frames !== 3)) {
    return NextResponse.json({ detail: "Choose a registered motion, unique attempt ID, and frame limit." }, { status: 422 });
  }
  return forwardToPlanningApi("/api/attempts", JSON.stringify(values));
}
