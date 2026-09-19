import { ArrowRight, CheckCircle2, LockKeyhole, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { useAuth } from '../auth/useAuth'
import { Brand } from '../components/Brand'

export function LoginPage() {
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')

    try {
      await signIn(email, password)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Sign-in failed.')
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
          <h2>Welcome back.</h2>
          <p>Sign in with your GREENSMECAPT account.</p>

          <form className="login-form" onSubmit={handleSubmit}>
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
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>

            {error && <div className="form-error">{error}</div>}

            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? 'Signing in…' : 'Enter platform'}
              {!submitting && <ArrowRight size={18} />}
            </button>
          </form>

          <p className="login-panel__footnote">
            Access is assigned by role. Investor, reviewer and SME workspaces expose
            only the information each account is permitted to use.
          </p>
        </div>
      </section>
    </main>
  )
}
