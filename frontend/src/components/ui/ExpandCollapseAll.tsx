import { useEffect } from "react";
import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Kbd } from "@/components/ui/Kbd";
import { Tooltip } from "@/components/ui/Tooltip";
import { useCardGroupActions } from "@/components/CardGroupContext";

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
}: {
  className?: string;
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
      if (inField) return;
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

  return (
    <div className={className}>
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
          onClick={actions.collapseAll}
          aria-label="Collapse all sections"
          className="ml-1"
        >
          <ChevronsDownUp className="h-4 w-4" />
          Collapse all
        </Button>
      </Tooltip>
    </div>
  );
}
