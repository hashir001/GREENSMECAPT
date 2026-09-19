import { ArrowRight, Database, KeyRound, Server } from 'lucide-react'

import { Brand } from '../components/Brand'

export function ConfigurationPage() {
  return (
    <main className="configuration-page">
      <section className="configuration-card">
        <Brand />
        <span className="eyebrow">One-time environment setup</span>
        <h1>Connect the secure identity layer.</h1>
        <p>
          The interface is ready, but Supabase credentials have not been supplied.
          Copy <code>.env.example</code> to <code>.env.local</code> and add the project
          URL and public anonymous key.
        </p>
        <div className="configuration-steps">
          <div><Database size={19} /><span>Create or select the Supabase project</span></div>
          <div><KeyRound size={19} /><span>Add the two public frontend variables</span></div>
          <div><Server size={19} /><span>Configure the matching backend issuer</span></div>
        </div>
        <code className="configuration-command">cp .env.example .env.local</code>
        <span className="configuration-note">
          Restart <strong>npm run dev</strong> after saving the environment file.
          <ArrowRight size={16} />
        </span>
      </section>
    </main>
  )
}
