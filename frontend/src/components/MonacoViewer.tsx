import { Editor } from "@monaco-editor/react";
import "@/lib/monacoInit";

export default function MonacoViewer({ content }: { content: string }) {
  return (
    <Editor
      value={content}
      language="xml"
      theme="vs-dark"
      height="100%"
      options={{
        readOnly: true,
        wordWrap: "on",
        minimap: { enabled: true },
        lineNumbers: "on",
        folding: true,
        scrollBeyondLastLine: false,
      }}
    />
  );
}
