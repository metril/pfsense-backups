import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
} from "react-router-dom";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { api, ApiError } from "./api/client";
import { useAuthStatus } from "./api/queries";
import { Layout } from "./components/Layout";
import { ConfirmProvider } from "./components/ui/ConfirmDialog";
import { ToastProvider, useToast } from "./components/ui/Toast";
import { TooltipProvider } from "./components/ui/Tooltip";
import { AuditPage } from "./pages/Audit";
import { BackupDiffPage } from "./pages/BackupDiff";
import { BackupsPage } from "./pages/Backups";
import { BackupViewPage } from "./pages/BackupView";
import { Dashboard } from "./pages/Dashboard";
import { InstanceChangesPage } from "./pages/InstanceChanges";
import { InstanceDetailPage } from "./pages/InstanceDetail";
import { InstanceHistoryPage } from "./pages/InstanceHistory";
import { InstancesPage } from "./pages/Instances";
import { Login } from "./pages/Login";
import { LogsPage } from "./pages/Logs";
import { NotificationsPage } from "./pages/Notifications";
import { SettingsPage } from "./pages/Settings";
import "./index.css";

type ToastApi = ReturnType<typeof useToast>;

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

// v0.41.16: migrated from <BrowserRouter> to createBrowserRouter +
// <RouterProvider> so data-router-only hooks like ``useBlocker`` (used
// on the Settings page to warn about unsaved edits) actually work.
// On the legacy router, calling useBlocker throws at mount and the
// whole SettingsPage tree unmounted to a blank body. ``RequireAuth``
// is now a layout route element (no children prop) — when the user
// is authed it returns <Layout /> whose own <Outlet /> mounts each
// child route. Semantically identical to the old wrapping pattern.
function RequireAuth() {
  const status = useAuthStatus();
  if (status.isPending) return null;
  if (!status.data?.authenticated) return <Navigate to="/login" replace />;
  return <Layout />;
}

const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route index element={<Dashboard />} />
        <Route path="instances" element={<InstancesPage />} />
        <Route path="instances/:id" element={<InstanceDetailPage />} />
        <Route path="instances/:id/history" element={<InstanceHistoryPage />} />
        <Route path="instances/:id/changes" element={<InstanceChangesPage />} />
        <Route path="backups" element={<BackupsPage />} />
        <Route path="backups/:id/view" element={<BackupViewPage />} />
        <Route path="backups/diff/:a/:b" element={<BackupDiffPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </>,
  ),
);

function AppWithErrorBridge() {
  const toast = useToast();
  // Latest handler always wins. Synchronous assignment (no effect)
  // means the bridge is live on the very first render — if a query
  // error fires before any effect runs, we still have a toast ref.
  // React strict-mode double-renders are fine because each render
  // overwrites the ref with the same ToastProvider's handler.
  toastRef.current = toast;

  // Ensure a csrftoken cookie exists before we attempt any mutations.
  // Runs once at app mount — previously lived in App.tsx which has
  // been folded into this file during the data-router migration.
  useEffect(() => {
    api.ensureCsrf().catch(() => {});
  }, []);

  return (
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
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
