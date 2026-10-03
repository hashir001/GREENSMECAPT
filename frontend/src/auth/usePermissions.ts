import { isPreviewMode } from '../lib/supabase'
import type { ApplicationRole } from '../types/api'
import { useAuth } from './useAuth'

export function usePermissions() {
  const { user } = useAuth()
  const claimedRole = user?.app_metadata.greensmecapt_role
  const role = typeof claimedRole === 'string' ? claimedRole as ApplicationRole : null
  const documentRole = role !== null && ['admin', 'reviewer', 'sme_user'].includes(role)
  const reviewerRole = role !== null && ['admin', 'reviewer'].includes(role)
  const effectiveRole: ApplicationRole | null = isPreviewMode ? 'reviewer' : role
  return {
    role: effectiveRole,
    homePath: '/',
    canViewDashboard: isPreviewMode || reviewerRole || role === 'investor',
    canViewSMEs: isPreviewMode || documentRole,
    canViewAssessments: isPreviewMode || reviewerRole || role === 'investor',
    canReviewEvidence: isPreviewMode || reviewerRole,
    canCompleteExpertSurvey: role === 'expert',
    canCreateSMEs: isPreviewMode || role === 'admin',
    canUpdateSMEs: role === 'admin' || role === 'sme_user',
    canDeleteSMEs: role === 'admin',
    canDeleteAssessmentRuns: role === 'admin',
    canUploadDocuments: isPreviewMode || documentRole,
    canProcessDocuments: isPreviewMode || documentRole,
    canDeleteDocuments: isPreviewMode || documentRole,
    canValidateEvidence: isPreviewMode || reviewerRole,
    canVerifyOwnEvidence: role === 'sme_user',
    canRunAssessments: isPreviewMode || reviewerRole,
    canApproveProfiles: isPreviewMode || reviewerRole,
    canPublishProfiles: isPreviewMode || reviewerRole,
    canCompareApprovedProfiles: (
      isPreviewMode
      || reviewerRole
      || role === 'investor'
    ),
  }
}
