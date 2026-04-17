import { DiffEditor, loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

// Bundle Monaco locally — no runtime CDN fetch.
self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker();
  },
};
loader.config({ monaco });


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
