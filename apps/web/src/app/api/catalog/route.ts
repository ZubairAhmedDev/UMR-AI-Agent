import { forwardToPlanningApi } from "@/lib/upstream";

export async function GET() {
  return forwardToPlanningApi("/api/catalog");
}
