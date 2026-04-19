import { Editor } from "@monaco-editor/react";
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

export default function MonacoViewer({ content }: { content: string }) {
  return (
    <Editor
      value={content}
      language="xml"
      theme="vs-dark"
      height="100%"
      options={OPTIONS}
    />
  );
}
