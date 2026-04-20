/**
 * Interface chip coloring — stable per interface name.
 *
 * Operators review a lot of firewall / NAT / VPN config. Giving "LAN"
 * the same color every time (regardless of which backup they're
 * reading) lets them spot "this rule is on a different interface than
 * I expected" from across the table without reading the text. An
 * 8-slot palette keeps color repetition rare on typical pfSense
 * deployments (1–3 interfaces) while staying hue-distinct on the
 * dark theme.
 */

const PALETTE_CLASSES = [
  // Each entry is the full set of Tailwind classes for a chip in that
  // hue — background tint, foreground text, border. We keep them
  // Tailwind-native (vs. arbitrary values) so JIT picks them up.
  { bg: "bg-[hsl(199_75%_55%/0.15)]", fg: "text-[hsl(199_75%_75%)]", border: "border-[hsl(199_75%_55%/0.35)]" }, // cyan
  { bg: "bg-[hsl(142_60%_50%/0.15)]", fg: "text-[hsl(142_60%_70%)]", border: "border-[hsl(142_60%_50%/0.35)]" }, // green
  { bg: "bg-[hsl(38_92%_58%/0.15)]",  fg: "text-[hsl(38_92%_75%)]",  border: "border-[hsl(38_92%_58%/0.35)]"  }, // amber
  { bg: "bg-[hsl(320_70%_60%/0.15)]", fg: "text-[hsl(320_70%_78%)]", border: "border-[hsl(320_70%_60%/0.35)]" }, // magenta
  { bg: "bg-[hsl(265_70%_65%/0.15)]", fg: "text-[hsl(265_70%_80%)]", border: "border-[hsl(265_70%_65%/0.35)]" }, // violet
  { bg: "bg-[hsl(172_60%_50%/0.15)]", fg: "text-[hsl(172_60%_70%)]", border: "border-[hsl(172_60%_50%/0.35)]" }, // teal
  { bg: "bg-[hsl(15_85%_58%/0.15)]",  fg: "text-[hsl(15_85%_75%)]",  border: "border-[hsl(15_85%_58%/0.35)]"  }, // red-amber
  { bg: "bg-[hsl(210_80%_60%/0.15)]", fg: "text-[hsl(210_80%_78%)]", border: "border-[hsl(210_80%_60%/0.35)]" }, // blue
] as const;

export interface InterfaceChipClasses {
  bg: string;
  fg: string;
  border: string;
}

/**
 * Stable hash of an interface key → one of the 8 palette slots.
 *
 * Deterministic (djb2) — the same key always gets the same slot. The
 * first few pfSense-reserved keys (wan/lan/opt1…opt5) map as:
 *   wan → cyan, lan → green, opt1 → amber, opt2 → magenta, opt3 → violet,
 *   opt4 → teal, opt5 → red-amber, opt6 → blue.
 * (Printed here so design reviewers can sanity-check the mapping
 * against screenshots; any change to the palette shifts this.)
 */
export function interfaceChipClasses(key: string): InterfaceChipClasses {
  let hash = 5381;
  for (let i = 0; i < key.length; i++) {
    hash = ((hash * 33) + key.charCodeAt(i)) >>> 0;
  }
  return PALETTE_CLASSES[hash % PALETTE_CLASSES.length];
}

/**
 * Canonical display label for an interface key. pfSense's internal
 * names (wan/lan/opt1) are lowercase; uppercase them for readability
 * since that matches the pfSense UI.
 */
export function interfaceLabel(key: string): string {
  return key.toUpperCase();
}
