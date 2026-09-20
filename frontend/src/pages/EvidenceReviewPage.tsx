import { AlertTriangle, CheckCircle2, Clock3, FileSearch, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { usePermissions } from '../auth/usePermissions'
import { EvidenceReviewPanel } from '../components/EvidenceReviewPanel'
import { api } from '../lib/api'
import type { EvidenceItem, SME } from '../types/api'

export function EvidenceReviewPage() {
  const { canValidateEvidence } = usePermissions()
  const [companies, setCompanies] = useState<SME[]>([])
  const [evidence, setEvidence] = useState<EvidenceItem[]>([])
  const [documentNames, setDocumentNames] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void api.listSMEs()
      .then(async (nextCompanies) => {
        setCompanies(nextCompanies)
        const records = await Promise.all(nextCompanies.map((company) => api.getSMERecord(company.sme_id)))
        setEvidence(records.flatMap((record) => record.evidence_items))
        setDocumentNames(Object.fromEntries(
          records.flatMap((record) => record.documents)
            .map((document) => [document.document_id, document.file_name]),
        ))
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Evidence could not be loaded.'))
      .finally(() => setLoading(false))
  }, [])

  const companyNames = useMemo(
    () => Object.fromEntries(companies.map((company) => [company.sme_id, company.legal_name])),
    [companies],
  )
  const unvalidated = evidence.filter((item) => item.validation_status === 'unvalidated').length
  const accepted = evidence.filter((item) => item.validation_status === 'accepted').length
  const rejected = evidence.filter((item) => item.validation_status === 'rejected').length

  async function validateEvidence(evidenceId: string, status: 'accepted' | 'rejected', reason?: string) {
    const updated = await api.validateEvidence(evidenceId, status, reason)
    setEvidence((current) => current.map((item) => item.evidence_id === updated.evidence_id ? updated : item))
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Human assurance</span>
          <h1>Evidence review queue</h1>
          <p>Inspect extracted claims in their original context before they enter assessment.</p>
        </div>
        <div className="review-assurance"><ShieldCheck size={18} /><span>Nothing enters scoring without an explicit decision</span></div>
      </section>

      <section className="queue-summary">
        <article><span className="queue-summary__icon queue-summary__icon--gold"><Clock3 size={19} /></span><div><strong>{unvalidated}</strong><span>Awaiting review</span></div></article>
        <article><span className="queue-summary__icon queue-summary__icon--jade"><CheckCircle2 size={19} /></span><div><strong>{accepted}</strong><span>Accepted evidence</span></div></article>
        <article><span className="queue-summary__icon queue-summary__icon--coral"><AlertTriangle size={19} /></span><div><strong>{rejected}</strong><span>Rejected evidence</span></div></article>
        <article><span className="queue-summary__icon queue-summary__icon--blue"><FileSearch size={19} /></span><div><strong>{companies.length}</strong><span>Companies covered</span></div></article>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {loading ? <div className="skeleton evidence-page-skeleton" /> : (
        <EvidenceReviewPanel evidenceItems={evidence} canValidate={canValidateEvidence} companyNames={companyNames} documentNames={documentNames} onValidate={validateEvidence} />
      )}
    </>
  )
}
