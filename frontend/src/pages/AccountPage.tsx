import { KeyRound, Mail, ShieldCheck, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { useAuth } from '../auth/useAuth'
import { usePermissions } from '../auth/usePermissions'

function humanize(value: string | null) {
  return value ? value.replaceAll('_', ' ') : 'unassigned'
}

export function AccountPage() {
  const { configured, updatePassword, user } = useAuth()
  const { role } = usePermissions()
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const rawAssignments = user?.app_metadata.sme_ids
  const assignments = Array.isArray(rawAssignments)
    ? rawAssignments.filter((value): value is string => typeof value === 'string')
    : []

  async function handlePasswordUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')

    if (password.length < 12) {
      setError('Use at least 12 characters for the new password.')
      return
    }

    if (password !== confirmation) {
      setError('The password confirmation does not match.')
      return
    }

    setSubmitting(true)

    try {
      await updatePassword(password)
      setPassword('')
      setConfirmation('')
      setNotice('Your password has been updated.')
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Your password could not be updated.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Account security</span>
          <h1>Profile and access</h1>
          <p>
            Review the identity and organization access trusted by the platform.
          </p>
        </div>
        <div className="review-assurance">
          <ShieldCheck size={18} />
          <span>Permissions come from signed Supabase claims</span>
        </div>
      </section>

      <section className="account-layout">
        <article className="panel account-card">
          <div className="panel__header">
            <div>
              <span className="eyebrow">Authenticated identity</span>
              <h2>Your account</h2>
            </div>
            <span className="account-card__icon"><UserRound size={21} /></span>
          </div>

          <dl className="account-details">
            <div>
              <dt><Mail size={15} /> Email</dt>
              <dd>{user?.email ?? 'Preview account'}</dd>
            </div>
            <div>
              <dt><ShieldCheck size={15} /> Application role</dt>
              <dd>{humanize(role)}</dd>
            </div>
            <div>
              <dt>Assigned SMEs</dt>
              <dd>
                {assignments.length
                  ? assignments.join(', ')
                  : role === 'sme_user'
                    ? 'No SME assignment'
                    : 'Portfolio-wide access'}
              </dd>
            </div>
          </dl>
        </article>

        <article className="panel account-card">
          <div className="panel__header">
            <div>
              <span className="eyebrow">Credential management</span>
              <h2>Change password</h2>
            </div>
            <span className="account-card__icon"><KeyRound size={21} /></span>
          </div>

          {!configured ? (
            <div className="account-preview-note">
              Password management becomes available when Supabase authentication
              is connected. Preview mode never changes credentials.
            </div>
          ) : <form className="account-password-form" onSubmit={handlePasswordUpdate}>
            <label>
              <span>New password</span>
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                minLength={12}
                required
              />
            </label>
            <label>
              <span>Confirm new password</span>
              <input
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                minLength={12}
                required
              />
            </label>

            {error && <div className="form-error">{error}</div>}
            {notice && <div className="form-success">{notice}</div>}

            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? 'Updating…' : 'Update password'}
            </button>
          </form>}
        </article>
      </section>
    </>
  )
}
