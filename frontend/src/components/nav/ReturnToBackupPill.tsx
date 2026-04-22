import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BackPill } from "./BackPill";

/**
 * Floating pill at the bottom-left that appears whenever the viewer
 * URL carries a ``?from={N}`` query param (set by the blame drawer
 * when the operator jumps from one backup's view to another).
 * Clicking returns to ``/backups/{N}/view``. Also installs a ``]``
 * keyboard shortcut — mirror of ``XrefBackPill``'s ``[``, so the two
 * pills cover within-backup and cross-backup back-nav respectively.
 *
 * Persists via URL (not sessionStorage) — operators who refresh stay
 * on the destination backup and still see the pill, which matches
 * the mental model "I went somewhere on purpose; getting back should
 * survive a page reload."
 */
export function ReturnToBackupPill({
  fromBackupId,
}: {
  fromBackupId: number;
}) {
  const nav = useNavigate();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      const inModal = target?.closest(
        '[role="dialog"], [role="listbox"], [role="menu"]',
      ) != null;
      if (inField || inModal) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "]") {
        e.preventDefault();
        nav(`/backups/${fromBackupId}/view`);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [fromBackupId, nav]);

  return (
    <BackPill
      position="left"
      label={
        <>
          Back to <span className="font-mono">#{fromBackupId}</span>
        </>
      }
      kbd="]"
      onClick={() => nav(`/backups/${fromBackupId}/view`)}
      ariaLabel={`Return to backup #${fromBackupId}`}
      title={`Return to backup #${fromBackupId} (])`}
    />
  );
}
