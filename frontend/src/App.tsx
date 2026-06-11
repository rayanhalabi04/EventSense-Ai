import { AppShell } from "@/components/layout/app-shell";
import { useAuth } from "@/hooks/use-auth";
import { AuditLogsPage } from "@/pages/audit-logs";
import { DocumentsPage } from "@/pages/documents";
import { EscalationsPage } from "@/pages/escalations";
import { EvaluationPage } from "@/pages/evaluation";
import { InboxPage } from "@/pages/inbox";
import { LoginPage } from "@/pages/login";
import { MessageDetailPage } from "@/pages/message-detail";
import { OverviewPage } from "@/pages/overview";
import { TasksPage } from "@/pages/tasks";
import { Loader2 } from "lucide-react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

function FullScreenLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Loader2 className="h-7 w-7 animate-spin text-muted-foreground" />
    </div>
  );
}

function ProtectedRoutes() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <FullScreenLoader />;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <AppShell />;
}

export function App() {
  const { isAuthenticated, isLoading } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={
          isLoading ? (
            <FullScreenLoader />
          ) : isAuthenticated ? (
            <Navigate to="/" replace />
          ) : (
            <LoginPage />
          )
        }
      />
      <Route element={<ProtectedRoutes />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/inbox/:conversationId" element={<MessageDetailPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/escalations" element={<EscalationsPage />} />
        <Route path="/audit-logs" element={<AuditLogsPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
