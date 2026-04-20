import { Editor, type OnMount } from "@monaco-editor/react";
import { useRef } from "react";
import "@/lib/monacoInit";

// Options is a module-level constant so re-rendering the viewer doesn't
// hand Monaco a fresh object identity each time — that would kick the
// editor into updateOptions() every render and, for deeper fields, can
// scramble folding/scroll state in the wrapper.
const OPTIONS = {
  readOnly: true,
  wordWrap: "on",
  minimap: { enabled: true },
  lineNumbers: "on",
  folding: true,
  scrollBeyondLastLine: false,
} as const;

/**
 * Thin Monaco wrapper that adds Structured ↔ Raw XML tab-switch
 * support:
 *
 * - ``focusLine`` (1-based) — when set, reveal that line in the
 *   center + paint a brief highlight so the operator's eye lands on
 *   the right element after switching from the Structured tab.
 *   Re-applies on every change (even to the same value) so clicking
 *   the same row twice still flashes.
 * - ``onCursorLineChange`` — fires on every cursor move with the
 *   current 1-based line. The parent uses this to reverse-lookup
 *   which anchorId the cursor is inside so switching back to
 *   Structured lands on the same row.
 *
 * The ``highlight`` decoration uses Monaco's line-class mechanism
 * (not ``selectionHighlight`` which would fight the editor's own
 * selection rendering). Style lives in ``index.css``.
 */
export default function MonacoViewer({
  content,
  focusLine,
  onCursorLineChange,
}: {
  content: string;
  focusLine?: number;
  onCursorLineChange?: (line: number) => void;
}) {
  type MonacoEditor = Parameters<OnMount>[0];
  type MonacoNamespace = Parameters<OnMount>[1];
  const editorRef = useRef<MonacoEditor | null>(null);
  const monacoRef = useRef<MonacoNamespace | null>(null);
  const decorationsRef = useRef<string[]>([]);
  const lastFocusRef = useRef<number | undefined>(undefined);
  // Silence the "fired just because we revealed a line" cursor
  // callback — Monaco emits onDidChangeCursorPosition as a side
  // effect of revealLineInCenter, which would echo back into the
  // parent's focus state and re-trigger this same effect.
  const suppressCursorRef = useRef(false);

  function applyFocus(line: number | undefined) {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco || !line || line < 1) {
      decorationsRef.current = editor
        ? editor.deltaDecorations(decorationsRef.current, [])
        : [];
      return;
    }
    suppressCursorRef.current = true;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: 1 });
    decorationsRef.current = editor.deltaDecorations(decorationsRef.current, [
      {
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          className: "monaco-xref-focus-line",
        },
      },
    ]);
    window.setTimeout(() => {
      suppressCursorRef.current = false;
    }, 0);
  }

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    editor.onDidChangeCursorPosition((e) => {
      if (suppressCursorRef.current) return;
      onCursorLineChange?.(e.position.lineNumber);
    });
    // Re-apply focus after mount — the ``focusLine`` prop may have
    // been set before the editor was ready.
    applyFocus(focusLine);
    lastFocusRef.current = focusLine;
  };

  // Re-reveal whenever ``focusLine`` changes. React's render cycle
  // runs on every parent update; only act when the value actually
  // moves (including re-selecting the same row, signalled by the
  // parent bumping a version — we handle sentinel ``undefined`` as
  // "clear highlight").
  if (lastFocusRef.current !== focusLine && editorRef.current) {
    applyFocus(focusLine);
    lastFocusRef.current = focusLine;
  }

  return (
    <Editor
      value={content}
      language="xml"
      theme="vs-dark"
      height="100%"
      options={OPTIONS}
      onMount={handleMount}
    />
  );
}
