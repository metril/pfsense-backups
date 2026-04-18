// Shared Monaco bootstrap. Imported for its side effects by MonacoDiff +
// MonacoViewer so both render with the same locally-bundled editor and
// don't double-register the worker or duplicate language contributions.
//
// A4 rationale still holds: we import only the editor API + XML
// contribution rather than pulling in every Monaco language.

import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/editor.api";
import "monaco-editor/esm/vs/basic-languages/xml/xml.contribution";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker();
  },
};

loader.config({ monaco });

export { monaco };
