import { forwardToPlanningApi } from "@/lib/upstream";

export async function POST(request: Request) {
  return forwardToPlanningApi("/api/agent/reviews", await request.text());
}
