import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth/useAuth'
import { AppShell } from './components/AppShell'
import { ConfigurationPage } from './pages/ConfigurationPage'
import { LoginPage } from './pages/LoginPage'
import { isPreviewMode } from './lib/supabase'

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((module) => ({
    default: module.DashboardPage,
  })),
)
const CompaniesPage = lazy(() =>
  import('./pages/CompaniesPage').then((module) => ({
    default: module.CompaniesPage,
  })),
)
const CompanyDetailPage = lazy(() =>
  import('./pages/CompanyDetailPage').then((module) => ({
    default: module.CompanyDetailPage,
  })),
)
const AssessmentsPage = lazy(() =>
  import('./pages/AssessmentsPage').then((module) => ({
    default: module.AssessmentsPage,
  })),
)
const AssessmentBuilderPage = lazy(() =>
  import('./pages/AssessmentBuilderPage').then((module) => ({
    default: module.AssessmentBuilderPage,
  })),
)
const AssessmentResultPage = lazy(() =>
  import('./pages/AssessmentResultPage').then((module) => ({
    default: module.AssessmentResultPage,
  })),
)
const EvidenceReviewPage = lazy(() =>
  import('./pages/EvidenceReviewPage').then((module) => ({
    default: module.EvidenceReviewPage,
  })),
)
const AccountPage = lazy(() =>
  import('./pages/AccountPage').then((module) => ({
    default: module.AccountPage,
  })),
)

function LoadingScreen() {
  return (
    <main className="loading-screen">
      <span className="loading-orbit" />
      <strong>Preparing your workspace</strong>
    </main>
  )
}

export default function App() {
  const { configured, loading, session } = useAuth()

  if (!configured && !isPreviewMode) return <ConfigurationPage />
  if (loading) return <LoadingScreen />
  if (!session && !isPreviewMode) return <LoginPage />

  return (
    <AppShell>
      <Suspense fallback={<div className="page-loader">Loading workspace…</div>}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/companies" element={<CompaniesPage />} />
          <Route path="/companies/:smeId" element={<CompanyDetailPage />} />
          <Route path="/assessments" element={<AssessmentsPage />} />
          <Route path="/assessments/new" element={<AssessmentBuilderPage />} />
          <Route path="/assessments/:runId" element={<AssessmentResultPage />} />
          <Route path="/evidence" element={<EvidenceReviewPage />} />
          <Route path="/settings" element={<AccountPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  )
}
