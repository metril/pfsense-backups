// A4: import only the bits of Monaco we actually use. Importing the root
// `monaco-editor` module pulls in every language contribution (all of
// jsonMode, htmlMode, cssMode, sql/mysql/pgsql/redshift, solidity, abap,
// freemarker, powerquery, …). For an XML-only diff we need the editor
// API + the XML basic-language contribution, nothing else.
import { DiffEditor, loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/xml/xml.contribution";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

// Bundle Monaco locally — no runtime CDN fetch. XML uses the generic
// editor worker (no language-specific worker), so one entry suffices.
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
