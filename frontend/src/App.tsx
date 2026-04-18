import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { useAuthStatus } from "./api/queries";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { InstancesPage } from "./pages/Instances";
import { BackupsPage } from "./pages/Backups";
import { BackupDiffPage } from "./pages/BackupDiff";
import { LogsPage } from "./pages/Logs";
import { SchedulePage } from "./pages/Schedule";
import { NotificationsPage } from "./pages/Notifications";
import { SettingsPage } from "./pages/Settings";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const status = useAuthStatus();
  if (status.isPending) return null;
  if (!status.data?.authenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  useEffect(() => {
    // Ensure a csrftoken cookie exists before we attempt any mutations.
    api.ensureCsrf().catch(() => {});
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="instances" element={<InstancesPage />} />
        <Route path="backups" element={<BackupsPage />} />
        <Route path="backups/diff/:a/:b" element={<BackupDiffPage />} />
        <Route path="schedule" element={<SchedulePage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
