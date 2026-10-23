import { NextRequest, NextResponse } from "next/server";
import { forwardToPlanningApi } from "@/lib/upstream";

export async function POST(request: NextRequest) {
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json(
      { detail: "JSON is required." },
      { status: 415 },
    );
  }

  const raw = await request.text();

  if (raw.length > 500) {
    return NextResponse.json(
      { detail: "Request is too large." },
      { status: 413 },
    );
  }

  let input: unknown;

  try {
    input = JSON.parse(raw);
  } catch {
    return NextResponse.json(
      { detail: "Invalid JSON." },
      { status: 400 },
    );
  }

  if (
    typeof input !== "object" ||
    input === null ||
    Array.isArray(input)
  ) {
    return NextResponse.json(
      { detail: "Invalid workflow request." },
      { status: 422 },
    );
  }

  const values = input as Record<string, unknown>;

  if (
    Object.keys(values).sort().join(",") !== "motion_id,workflow_id" ||
    typeof values.workflow_id !== "string" ||
    !/^[A-Za-z0-9_-]{1,77}$/.test(values.workflow_id) ||
    typeof values.motion_id !== "string" ||
    !["spin-kick", "run", "speed-vault"].includes(values.motion_id)
  ) {
    return NextResponse.json(
      { detail: "Choose a registered motion and valid workflow ID." },
      { status: 422 },
    );
  }

  return forwardToPlanningApi(
    "/api/workflows",
    JSON.stringify(values),
  );
}
