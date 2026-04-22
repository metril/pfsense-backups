import { useEffect } from "react";
import { expandThenScrollToHash } from "@/lib/xref";
import { useXrefHistory } from "@/components/xref/XrefHistory";
import { BackPill } from "@/components/nav/BackPill";

/**
 * Floating pill at the bottom-right that appears whenever the xref
 * back-stack has at least one entry. Clicking rewinds one step —
 * scrolls back to the origin row and flashes it so the operator
 * re-orients. Installs a global ``[`` keyboard shortcut (same
 * ``input / modal`` guard the other shortcuts use).
 *
 * Shares visual treatment with ``ReturnToBackupPill`` (accent outline,
 * solid bg) via the shared ``BackPill`` base; only the position and
 * keybinding differ. Left vs right naturally separates the two
 * back-navigators so they never collide.
 */
export function XrefBackPill() {
  const history = useXrefHistory();

  useEffect(() => {
    if (!history) return;
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      const inModal =
        target?.closest(
          '[role="dialog"], [role="listbox"], [role="menu"]',
        ) != null;
      if (inField || inModal) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "[") {
        e.preventDefault();
        goBack();
      }
    }
    function goBack() {
      if (!history) return;
      const stack = history.stack;
      const entry = stack[stack.length - 1];
      if (!entry) return;
      history.pop();
      expandThenScrollToHash(`#${entry.anchorId}`);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [history]);

  if (!history || history.stack.length === 0) return null;

  const top = history.stack[history.stack.length - 1];
  const onClick = () => {
    history.pop();
    expandThenScrollToHash(`#${top.anchorId}`);
  };

  const stackDepth = history.stack.length;

  return (
    <BackPill
      position="right"
      label={
        <>
          Back to <span className="opacity-80">{top.label}</span>
        </>
      }
      kbd="["
      onClick={onClick}
      ariaLabel={`Back to ${top.label}`}
      title={`Back to ${top.label} ([)`}
      trailing={
        stackDepth > 1 ? (
          <span
            className="ml-1 rounded bg-accent/20 px-1 text-[10px]"
            title={`${stackDepth} entries on the back stack`}
          >
            {stackDepth}
          </span>
        ) : undefined
      }
    />
  );
}
