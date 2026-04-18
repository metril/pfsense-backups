import { StrictMode, useMemo } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import App from "./App";
import { ApiError } from "./api/client";
import { ToastProvider, useToast } from "./components/ui/Toast";
import "./index.css";

/**
 * Extract a user-friendly message from an error. FastAPI returns either a
 * string ``detail`` or a list of validation error objects — handle both
 * (L5 / related frontend polish).
 */
function extractMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: unknown } | null;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item: { msg?: string; loc?: unknown[] }) =>
          item?.msg ? `${(item.loc ?? []).join(".")}: ${item.msg}` : JSON.stringify(item),
        )
        .join("; ");
    }
    return err.message || `HTTP ${err.status}`;
  }
  return err instanceof Error ? err.message : String(err);
}

/** Bridge component that wires TanStack Query error callbacks to our toast stack. */
function AppWithErrorBridge() {
  const toast = useToast();
  // Query/mutation caches live for the life of the app; reinstantiating them
  // inside the component would clear state on every re-render. So we create
  // them exactly once and only attach the toast handlers.
  const qc = useMemo(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (err, query) => {
            // Background refetches that fail shouldn't spam the user. Show
            // only when the query has NO cached data (the user is actively
            // waiting on it).
            if (!query.state.data) toast.error(extractMessage(err));
          },
        }),
        mutationCache: new MutationCache({
          onError: (err, _vars, _ctx, mutation) => {
            // Let per-mutation onError override if the caller handled it.
            if (mutation.options.onError) return;
            toast.error(extractMessage(err));
          },
        }),
        defaultOptions: {
          queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 15_000 },
        },
      }),
    [toast],
  );

  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <AppWithErrorBridge />
    </ToastProvider>
  </StrictMode>,
);
