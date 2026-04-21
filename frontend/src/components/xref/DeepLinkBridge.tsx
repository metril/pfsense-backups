import { useEffect } from "react";
import { expandThenScrollToHash } from "@/lib/xref";
import { useCardGroup } from "@/components/CardGroupContext";

/**
 * Wires up hash-fragment deep links on a page.
 *
 * - **On mount**: if the URL already carries a hash (operator pasted a
 *   share link into a new tab, or navigated here from the diff view's
 *   cross-page xref), auto-expand the containing card and scroll.
 * - **On hashchange**: native anchor clicks (e.g. the ToC chip strip)
 *   fire ``hashchange``; run the same flow so the target card opens
 *   even when it was collapsed.
 * - **Bridges a DOM event to React state**: ``expandThenScrollToHash``
 *   dispatches a ``pfsense-snap-to-card`` CustomEvent which this
 *   component catches and forwards to the ``CardGroupProvider`` via
 *   ``snapTarget``. Keeps ``xref.ts`` pure DOM (it can't import React
 *   context directly).
 *
 * Props:
 *   ``includeHashchange`` — both pages default this to ``true``. The
 *   diff page's summary strip anchors fire ``hashchange`` natively,
 *   and since v0.14.0 those targets may be collapsed cards that need
 *   to be auto-opened before the scroll lands. Setting this to
 *   ``false`` skips that auto-open and produces the same silent
 *   no-op the v0.15.0 review flagged. Pass ``false`` only for pages
 *   with no Card collapse behaviour at all.
 */
export function DeepLinkBridge({
  includeHashchange = true,
}: {
  includeHashchange?: boolean;
}) {
  const groupCtx = useCardGroup();

  // On mount: pick up whatever hash is in the URL right now.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash;
    if (hash) {
      // Let children render once so their anchors exist.
      const raf = requestAnimationFrame(() => expandThenScrollToHash(hash));
      return () => cancelAnimationFrame(raf);
    }
    return;
  }, []);

  // hashchange listener (viewer only, by default).
  useEffect(() => {
    if (!includeHashchange) return;
    if (typeof window === "undefined") return;
    const onHash = () => expandThenScrollToHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [includeHashchange]);

  // Custom event → CardGroupProvider.snapTarget bridge.
  //
  // Depend on ``snapTarget`` (the stable ``useCallback``-wrapped
  // function from the provider) rather than the whole ``groupCtx``.
  // ``groupCtx`` re-memoises every time the provider's internal state
  // ticks (resetVersion, snapTargetVersion), which would tear the
  // listener down and re-install it on every expand-all / snap —
  // a brief window in which a rapidly-dispatched ``pfsense-snap-to-
  // card`` event would be missed.
  const snapTarget = groupCtx?.snapTarget;
  useEffect(() => {
    if (!snapTarget) return;
    const onSnap = (ev: Event) => {
      const ce = ev as CustomEvent<{ cardId: string }>;
      if (ce.detail?.cardId) snapTarget(ce.detail.cardId);
    };
    window.addEventListener("pfsense-snap-to-card", onSnap);
    return () => window.removeEventListener("pfsense-snap-to-card", onSnap);
  }, [snapTarget]);

  return null;
}
