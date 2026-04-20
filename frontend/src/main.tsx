import { StrictMode, useEffect, useRef } from "react";
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
import { ConfirmProvider } from "./components/ui/ConfirmDialog";
import { ToastProvider, useToast } from "./components/ui/Toast";

type ToastApi = ReturnType<typeof useToast>;
import { TooltipProvider } from "./components/ui/Tooltip";
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

// QueryClient is created exactly once at module load. Previously it lived
// inside a useMemo([toast]) which re-ran whenever the ToastProvider's
// context value shifted (e.g. on HMR or any Toast state change), wiping
// the entire query cache mid-session. Using a mutable ref for the toast
// handler keeps the QC identity stable forever.
const toastRef: { current: ToastApi | null } = { current: null };

const qc = new QueryClient({
  queryCache: new QueryCache({
    onError: (err, query) => {
      // Background refetches that fail shouldn't spam the user — only
      // toast when the query has no cached data (actively blocking UI).
      if (!query.state.data) toastRef.current?.error(extractMessage(err));
    },
  }),
  mutationCache: new MutationCache({
    onError: (err, _vars, _ctx, mutation) => {
      if (mutation.options.onError) return;
      toastRef.current?.error(extractMessage(err));
    },
  }),
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 15_000 },
  },
});

function AppWithErrorBridge() {
  const toast = useToast();
  // Keep the latest toast handler addressable without re-creating the QC.
  const ref = useRef(toast);
  ref.current = toast;
  useEffect(() => {
    toastRef.current = ref.current;
    return () => {
      if (toastRef.current === ref.current) toastRef.current = null;
    };
  }, []);

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
    <TooltipProvider>
      <ToastProvider>
        <ConfirmProvider>
          <AppWithErrorBridge />
        </ConfirmProvider>
      </ToastProvider>
    </TooltipProvider>
  </StrictMode>,
);
