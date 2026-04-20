import { useEffect } from "react";
import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Kbd } from "@/components/ui/Kbd";
import { Tooltip } from "@/components/ui/Tooltip";
import { useCardGroupActions } from "@/components/CardGroupContext";
import { cn } from "@/lib/cn";

/**
 * Two-button toolbar that drives expand-all / collapse-all on every
 * ``<Card>`` inside a ``<CardGroupProvider>``. Also installs the
 * global ``e`` / ``c`` keyboard shortcuts.
 *
 * The shortcut listener ignores events whose target is an
 * ``<input>`` / ``<textarea>`` / contentEditable — same guard the
 * QuickJump palette uses for ``/`` — so typing into a tag / note
 * field never accidentally collapses the view.
 */
export function ExpandCollapseAll({
  className,
  orientation = "horizontal",
}: {
  className?: string;
  /** ``"vertical"`` stacks the buttons full-width so they fit a
   *  narrow sticky sidebar (the 15rem ToC column) without the
   *  ``Expand all`` / ``Collapse all`` label wrapping onto two
   *  lines. Default stays horizontal for the wide header strip. */
  orientation?: "horizontal" | "vertical";
}) {
  const actions = useCardGroupActions();

  useEffect(() => {
    if (!actions) return;
    const { expandAll, collapseAll } = actions;
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);
      // Also suppress the shortcut when focus is anywhere inside an
      // open modal / listbox / command palette. The QuickJump palette
      // steals focus to its ``<li role="option">`` items on hover,
      // which bypasses the INPUT guard — this closest() check catches
      // those cases without needing the palette to expose its state.
      const inModal =
        target?.closest(
          '[role="dialog"], [role="listbox"], [role="menu"]',
        ) != null;
      if (inField || inModal) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "e") {
        e.preventDefault();
        expandAll();
      } else if (e.key === "c") {
        e.preventDefault();
        collapseAll();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [actions]);

  if (!actions) return null;

  const isVertical = orientation === "vertical";
  const buttonClass = isVertical ? "w-full justify-start" : undefined;

  return (
    <div
      className={cn(
        "flex gap-1",
        isVertical ? "flex-col items-stretch" : "items-center",
        className,
      )}
    >
      <Tooltip
        content={
          <span className="inline-flex items-center gap-1">
            Expand all sections <Kbd>e</Kbd>
          </span>
        }
      >
        <Button
          variant="secondary"
          size="sm"
          className={buttonClass}
          onClick={actions.expandAll}
          aria-label="Expand all sections"
        >
          <ChevronsUpDown className="h-4 w-4" />
          Expand all
        </Button>
      </Tooltip>
      <Tooltip
        content={
          <span className="inline-flex items-center gap-1">
            Collapse all sections <Kbd>c</Kbd>
          </span>
        }
      >
        <Button
          variant="secondary"
          size="sm"
          className={buttonClass}
          onClick={actions.collapseAll}
          aria-label="Collapse all sections"
        >
          <ChevronsDownUp className="h-4 w-4" />
          Collapse all
        </Button>
      </Tooltip>
    </div>
  );
}
