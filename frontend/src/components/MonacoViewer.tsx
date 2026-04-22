import { Editor, type OnMount } from "@monaco-editor/react";
import { useEffect, useRef } from "react";
import type { IDisposable } from "monaco-editor";
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
  blameProvider,
}: {
  content: string;
  focusLine?: number;
  onCursorLineChange?: (line: number) => void;
  /** v0.40.0: hover-provider hook. Given a 1-based line number,
   *  return markdown content for Monaco's hover card — typically the
   *  same "Last modified …" text the Structured tooltip shows. The
   *  caller (``BackupView``) dispatches via the ``positions`` map to
   *  find the anchor covering the hovered line, then looks up that
   *  anchor in the blame summary. Pass ``undefined`` to disable. */
  blameProvider?: (line: number) => string | null;
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
  // Latest blameProvider stored in a ref so the Monaco hover
  // callback (captured once at mount) always dispatches to the
  // current provider. Re-registering the provider on every prop
  // change would churn Monaco's internal hover state.
  const blameProviderRef = useRef<
    ((line: number) => string | null) | undefined
  >(blameProvider);
  blameProviderRef.current = blameProvider;
  // Disposable returned by ``monaco.languages.registerHoverProvider``.
  // Tracked so a later unmount + remount (React.lazy re-suspension,
  // Strict Mode double-invocation) doesn't leak a second provider
  // into Monaco's global "xml" registry — every stale provider
  // would run on every hover for the rest of the session.
  const hoverDisposableRef = useRef<IDisposable | null>(null);

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
    // v0.40.0: register a hover provider that dispatches to the
    // caller-supplied ``blameProvider``. Registered once at mount —
    // subsequent prop changes are picked up via ``blameProviderRef``.
    // The returned disposable is tracked in a ref so the useEffect
    // cleanup below can dispose on unmount (or on a Strict Mode
    // double-mount that calls handleMount twice).
    if (hoverDisposableRef.current) {
      hoverDisposableRef.current.dispose();
    }
    hoverDisposableRef.current = monaco.languages.registerHoverProvider("xml", {
      provideHover: (_model, position) => {
        const fn = blameProviderRef.current;
        if (!fn) return null;
        const text = fn(position.lineNumber);
        if (!text) return null;
        return {
          contents: [{ value: text }],
        };
      },
    });
    // Re-apply focus after mount — the ``focusLine`` prop may have
    // been set before the editor was ready.
    applyFocus(focusLine);
    lastFocusRef.current = focusLine;
  };

  // Re-reveal whenever ``focusLine`` changes. This lives in an
  // effect rather than in the render body because revealing lines
  // and mutating Monaco decorations is a side effect that would
  // fire under React 18 strict mode / concurrent rendering in ways
  // that could double-apply or leak the ``suppressCursor`` flag.
  //
  // If the editor hasn't mounted yet we still sync ``lastFocusRef``
  // so ``handleMount`` doesn't double-apply when the prop arrives
  // before the editor is ready (rapid tab-switch + slider scrub
  // can produce focusLine changes between render and mount).
  useEffect(() => {
    if (!editorRef.current) {
      lastFocusRef.current = focusLine;
      return;
    }
    if (lastFocusRef.current === focusLine) return;
    applyFocus(focusLine);
    lastFocusRef.current = focusLine;
  }, [focusLine]);

  // Dispose the hover provider on unmount so it doesn't remain in
  // Monaco's global registry after this component goes away.
  useEffect(() => {
    return () => {
      if (hoverDisposableRef.current) {
        hoverDisposableRef.current.dispose();
        hoverDisposableRef.current = null;
      }
    };
  }, []);

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
