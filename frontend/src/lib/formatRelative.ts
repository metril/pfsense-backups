/**
 * Human-friendly "time ago" formatter. Output shape matches the
 * rest of the app's blame / cumulative-changes UI: ``12s ago``,
 * ``3m ago``, ``1h ago``, ``5d ago``, ``2w ago``, ``3mo ago``,
 * ``1y ago``. Lifted out of the blame + cumulative-changes pages
 * in v0.40.0 so both surfaces share the same thresholds — if they
 * drift the two pages will contradict each other for the same
 * backup timestamp.
 */
export function formatRelative(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.round((now - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo ago`;
  const years = Math.round(months / 12);
  return `${years}y ago`;
}
