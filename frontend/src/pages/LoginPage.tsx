import { ArrowRight, CheckCircle2, LockKeyhole, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { useAuth } from '../auth/useAuth'
import { Brand } from '../components/Brand'

export function LoginPage() {
  const { requestPasswordReset, signIn, signUp } = useAuth()
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [role, setRole] = useState<'sme_user' | 'investor'>('sme_user')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [companySector, setCompanySector] = useState('')
  const [companyJurisdiction, setCompanyJurisdiction] = useState('United Arab Emirates')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setNotice('')

    try {
      if (mode === 'signin') {
        await signIn(email, password)
      } else {
        const result = await signUp({
          email,
          password,
          role,
          companyName: role === 'sme_user' ? companyName : undefined,
          companySector: role === 'sme_user' ? companySector : undefined,
          companyJurisdiction: role === 'sme_user' ? companyJurisdiction : undefined,
        })
        if (result.requiresEmailConfirmation) {
          setNotice('Account created. Confirm your email, then sign in.')
          setMode('signin')
        }
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Sign-in failed.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handlePasswordReset() {
    setError('')
    setNotice('')

    if (!email.trim()) {
      setError('Enter your email address first.')
      return
    }

    setSubmitting(true)

    try {
      await requestPasswordReset(email.trim())
      setNotice(
        'Password-reset instructions have been sent if the account exists.',
      )
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'Password reset could not be requested.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-story">
        <div className="login-story__halo login-story__halo--one" />
        <div className="login-story__halo login-story__halo--two" />
        <Brand />
        <div className="login-story__copy">
          <span className="eyebrow eyebrow--light">Green capital, clearer decisions</span>
          <h1>See the evidence behind every sustainable investment.</h1>
          <p>
            Document intelligence, traceable assessment and multi-method ranking—built
            for the realities of emerging green SMEs.
          </p>
        </div>
        <div className="login-story__proof">
          <div><CheckCircle2 size={17} /> Source-linked evidence</div>
          <div><CheckCircle2 size={17} /> Adaptive SME assessment</div>
          <div><CheckCircle2 size={17} /> Robust decision analysis</div>
        </div>
        <div className="login-story__signal">
          <Sparkles size={18} />
          <span>AI-assisted. Human-governed. Fully traceable.</span>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-panel__inner">
          <span className="login-panel__lock"><LockKeyhole size={22} /></span>
          <span className="eyebrow">Secure platform access</span>
          <h2>{mode === 'signin' ? 'Welcome back.' : 'Create your account.'}</h2>
          <p>{mode === 'signin' ? 'Sign in with your GREENSMECAPT account.' : 'SMEs and investors can start directly.'}</p>

          <div className="auth-mode-switch">
            <button type="button" className={mode === 'signin' ? 'active' : ''} onClick={() => setMode('signin')}>Sign in</button>
            <button type="button" className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')}>Create account</button>
          </div>

          <form className="login-form" onSubmit={handleSubmit}>
            {mode === 'signup' && (
              <div className="signup-role-switch">
                <button type="button" className={role === 'sme_user' ? 'active' : ''} onClick={() => setRole('sme_user')}>I represent an SME</button>
                <button type="button" className={role === 'investor' ? 'active' : ''} onClick={() => setRole('investor')}>I am an investor</button>
              </div>
            )}
            {mode === 'signup' && role === 'sme_user' && (
              <>
                <label><span>Company legal name</span><input required value={companyName} onChange={(event) => setCompanyName(event.target.value)} /></label>
                <label><span>Sector</span><input required value={companySector} onChange={(event) => setCompanySector(event.target.value)} /></label>
                <label><span>Jurisdiction</span><input required value={companyJurisdiction} onChange={(event) => setCompanyJurisdiction(event.target.value)} /></label>
              </>
            )}
            <label>
              <span>Email address</span>
              <input
                type="email"
                autoComplete="email"
                placeholder="name@organisation.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={mode === 'signup' ? 12 : undefined}
              />
            </label>

            {error && <div className="form-error">{error}</div>}
            {notice && <div className="form-success">{notice}</div>}

            {mode === 'signin' && <button className="login-form__reset" type="button" disabled={submitting} onClick={() => void handlePasswordReset()}>Forgot your password?</button>}

            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? 'Please wait…' : mode === 'signin' ? 'Enter platform' : 'Create account'}
              {!submitting && <ArrowRight size={18} />}
            </button>
          </form>

          <p className="login-panel__footnote">
            Reviewer, expert and administrator roles remain controlled by platform administrators.
          </p>
        </div>
      </section>
    </main>
  )
}
