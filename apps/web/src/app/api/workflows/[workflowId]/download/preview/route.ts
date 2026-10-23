import { NextResponse } from "next/server";
import {
  forwardMediaToPlanningApi,
} from "@/lib/upstream";

export async function GET(
  request: Request,
  context: {
    params: Promise<{
      workflowId: string;
    }>;
  },
) {
  const { workflowId } =
    await context.params;

  if (
    !/^[A-Za-z0-9_-]{1,77}$/.test(
      workflowId,
    )
  ) {
    return NextResponse.json(
      {
        detail: "Invalid workflow ID.",
      },
      {
        status: 422,
      },
    );
  }

  return forwardMediaToPlanningApi(
    `/api/workflows/${workflowId}/download/preview`,
    request,
  );
}
