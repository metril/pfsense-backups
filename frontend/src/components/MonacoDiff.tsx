import { DiffEditor } from "@monaco-editor/react";
import "@/lib/monacoInit";

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
      options={{
        readOnly: true,
        originalEditable: false,
        renderSideBySide: true,
        wordWrap: "on",
        minimap: { enabled: false },
      }}
    />
  );
}
