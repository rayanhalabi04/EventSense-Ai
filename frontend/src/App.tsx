import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { LazyMotion, domAnimation } from 'framer-motion'
import { useAuthStore } from './store/authStore'
import { authService } from './services/auth'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AppLayout } from './components/layout/AppLayout'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { OverviewPage } from './pages/OverviewPage'
import { InboxPage } from './pages/InboxPage'
import { ConversationDetailPage } from './pages/ConversationDetailPage'
import { TasksPage } from './pages/TasksPage'
import { EscalationsPage } from './pages/EscalationsPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { AuditLogsPage } from './pages/AuditLogsPage'
import { EvaluationPage } from './pages/EvaluationPage'

function AppBootstrap() {
  const { token, user, setUser, logout } = useAuthStore()

  useEffect(() => {
    if (token && !user) {
      const derivedUser = authService.userFromToken(token)
      if (derivedUser) {
        setUser(derivedUser)
      } else {
        logout()
      }
    }
  }, [token, user, setUser, logout])

  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <LazyMotion features={domAnimation}>
        <AppBootstrap />
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/landing" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />

          {/* Protected app routes */}
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/overview" element={<OverviewPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/inbox/:conversationId" element={<ConversationDetailPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/escalations" element={<EscalationsPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route
              path="/audit-logs"
              element={
                <ProtectedRoute requiredRole="manager">
                  <AuditLogsPage />
                </ProtectedRoute>
              }
            />
            <Route path="/evaluation" element={<EvaluationPage />} />
          </Route>

          {/* 404 */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </LazyMotion>
    </BrowserRouter>
  )
}
