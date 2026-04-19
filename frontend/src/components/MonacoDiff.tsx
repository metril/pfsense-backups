import { DiffEditor } from "@monaco-editor/react";
import "@/lib/monacoInit";

// Module-level options so a parent re-render doesn't hand Monaco a
// fresh object on every pass — see MonacoViewer for the same note.
const OPTIONS = {
  readOnly: true,
  originalEditable: false,
  renderSideBySide: true,
  wordWrap: "on",
  minimap: { enabled: false },
} as const;

export default function MonacoDiff({
  original,
  modified,
}: {
  original: string;
  modified: string;
}) {
  return (
    <DiffEditor
      original={original}
      modified={modified}
      language="xml"
      theme="vs-dark"
      height="100%"
      options={OPTIONS}
    />
  );
}
