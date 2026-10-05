import { NextResponse } from "next/server";
import { forwardToPlanningApi } from "@/lib/upstream";

export async function GET(_request: Request, context: { params: Promise<{ attempt: string }> }) {
  const { attempt } = await context.params;
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(attempt)) {
    return NextResponse.json({ detail: "Invalid attempt ID." }, { status: 422 });
  }
  return forwardToPlanningApi(`/api/attempts/${attempt}/plan`);
}
