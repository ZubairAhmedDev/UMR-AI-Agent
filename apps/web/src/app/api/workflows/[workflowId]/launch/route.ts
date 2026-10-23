import { NextRequest, NextResponse } from "next/server";
import { forwardToPlanningApi } from "@/lib/upstream";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ workflowId: string }> },
) {
  const { workflowId } = await context.params;

  if (!/^[A-Za-z0-9_-]{1,77}$/.test(workflowId)) {
    return NextResponse.json(
      { detail: "Invalid workflow ID." },
      { status: 422 },
    );
  }

  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return NextResponse.json(
      { detail: "JSON is required." },
      { status: 415 },
    );
  }

  const raw = await request.text();

  if (raw.length > 200) {
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
      { detail: "Invalid approval." },
      { status: 422 },
    );
  }

  const values = input as Record<string, unknown>;

  if (
    Object.keys(values).join(",") !== "approved_workflow_hash" ||
    typeof values.approved_workflow_hash !== "string" ||
    !/^[0-9a-f]{64}$/.test(values.approved_workflow_hash)
  ) {
    return NextResponse.json(
      { detail: "Approval requires the exact workflow hash." },
      { status: 422 },
    );
  }

  return forwardToPlanningApi(
    `/api/workflows/${workflowId}/launch`,
    raw,
  );
}
