// Backend persists every timestamp in UTC. ISO strings on the wire
// usually carry an explicit offset (`+00:00` from a tz-aware datetime
// or `Z`), but SQLite round-trips occasionally drop the tzinfo, so the
// helper below treats a naive ISO as UTC rather than letting the
// browser misread it as local time. Then we render in the browser's
// own zone via toLocaleString().

function asUtcDate(ts: string): Date {
  const hasOffset = /Z$|[+-]\d{2}:?\d{2}$/.test(ts);
  return new Date(hasOffset ? ts : ts + "Z");
}

export function formatLocal(
  ts: string,
  opts: Intl.DateTimeFormatOptions = {},
): string {
  return asUtcDate(ts).toLocaleString(undefined, opts);
}

export function formatTimeOnly(ts: string): string {
  return asUtcDate(ts).toLocaleTimeString(undefined, { hour12: false });
}

export function formatLocalDate(ts: string): string {
  return asUtcDate(ts).toLocaleDateString();
}
