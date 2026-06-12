import { ApiError } from "@/api/client";

/**
 * Extract a user-friendly message from an error. FastAPI returns either a
 * string ``detail`` or a list of validation error objects — handle both
 * (L5 / related frontend polish).
 */
export function extractMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: unknown } | null;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item: { msg?: string; loc?: unknown[] }) =>
          item?.msg ? `${(item.loc ?? []).join(".")}: ${item.msg}` : JSON.stringify(item),
        )
        .join("; ");
    }
    return err.message || `HTTP ${err.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}
