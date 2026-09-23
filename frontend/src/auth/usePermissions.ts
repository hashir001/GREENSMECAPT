import { isPreviewMode } from '../lib/supabase'
import { useAuth } from './useAuth'

type ApplicationRole = 'admin' | 'reviewer' | 'investor' | 'sme_user'

export function usePermissions() {
  const { user } = useAuth()
  const claimedRole = user?.app_metadata.greensmecapt_role
  const role = typeof claimedRole === 'string' ? claimedRole as ApplicationRole : null
  const documentRole = role !== null && ['admin', 'reviewer', 'sme_user'].includes(role)
  const reviewerRole = role !== null && ['admin', 'reviewer'].includes(role)
  return {
    role: isPreviewMode ? 'reviewer' as const : role,
    canCreateSMEs: isPreviewMode || role === 'admin',
    canUploadDocuments: isPreviewMode || documentRole,
    canProcessDocuments: isPreviewMode || documentRole,
    canValidateEvidence: isPreviewMode || reviewerRole,
    canRunAssessments: isPreviewMode || reviewerRole,
    canCompareApprovedProfiles: (
      isPreviewMode
      || reviewerRole
      || role === 'investor'
    ),
  }
}
