import { extractMessage } from "@/lib/errors";
import { Alert } from "./Alert";

/**
 * Inline error block for a failed page-level query. Pages that render
 * `data ?? []` would otherwise show their empty state ("No backups yet")
 * when the fetch actually failed — the global toast fires once, but the
 * persistent UI must say "failed", not "empty".
 */
export function QueryError({ title, error }: { title: string; error: unknown }) {
  return (
    <Alert tone="danger" title={title}>
      {extractMessage(error)}
    </Alert>
  );
}
