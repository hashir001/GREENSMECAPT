import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth/useAuth'
import { usePermissions } from './auth/usePermissions'
import { AppShell } from './components/AppShell'
import { ConfigurationPage } from './pages/ConfigurationPage'
import { LoginPage } from './pages/LoginPage'
import { isPreviewMode } from './lib/supabase'
import type { ApplicationRole } from './types/api'

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
const ApprovedComparisonPage = lazy(() =>
  import('./pages/ApprovedComparisonPage').then((module) => ({
    default: module.ApprovedComparisonPage,
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
const FinancialPage = lazy(() =>
  import('./pages/FinancialPage').then((module) => ({
    default: module.FinancialPage,
  })),
)

function ApprovedComparisonRoute() {
  const { canCompareApprovedProfiles } = usePermissions()

  if (!canCompareApprovedProfiles) {
    return <Navigate to="/assessments" replace />
  }

  return <ApprovedComparisonPage />
}

function AssessmentBuilderRoute() {
  const { canRunAssessments } = usePermissions()

  if (!canRunAssessments) {
    return <Navigate to="/assessments" replace />
  }

  return <AssessmentBuilderPage />
}

function RoleRoute({
  roles,
  children,
}: {
  roles: ApplicationRole[]
  children: ReactNode
}) {
  const { homePath, role } = usePermissions()

  if (role === null || !roles.includes(role)) {
    return <Navigate to={homePath} replace />
  }

  return children
}

function HomeRoute() {
  return <DashboardPage />
}

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
          <Route path="/" element={<HomeRoute />} />
          <Route path="/companies" element={
            <RoleRoute roles={['admin', 'reviewer', 'investor', 'sme_user']}>
              <CompaniesPage />
            </RoleRoute>
          } />
          <Route path="/companies/:smeId" element={
            <RoleRoute roles={['admin', 'reviewer', 'sme_user']}>
              <CompanyDetailPage />
            </RoleRoute>
          } />
          <Route path="/assessments" element={
            <RoleRoute roles={['admin', 'reviewer', 'investor']}>
              <AssessmentsPage />
            </RoleRoute>
          } />
          <Route path="/assessments/new" element={<AssessmentBuilderRoute />} />
          <Route path="/assessments/compare" element={<ApprovedComparisonRoute />} />
          <Route path="/assessments/:runId" element={
            <RoleRoute roles={['admin', 'reviewer', 'investor']}>
              <AssessmentResultPage />
            </RoleRoute>
          } />
          <Route path="/evidence" element={
            <RoleRoute roles={['admin', 'reviewer']}>
              <EvidenceReviewPage />
            </RoleRoute>
          } />
          <Route path="/financial" element={
            <RoleRoute roles={['admin', 'reviewer', 'sme_user']}>
              <FinancialPage />
            </RoleRoute>
          } />
          <Route path="/settings" element={<AccountPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  )
}
