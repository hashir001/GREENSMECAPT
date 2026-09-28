import {
  AlertTriangle,
  BrainCircuit,
  Check,
  ChevronRight,
  Eye,
  FileSearch,
  FileText,
  Layers3,
  LoaderCircle,
  RefreshCw,
  ScanText,
  Sparkles,
  Table2,
} from 'lucide-react'
import { useState } from 'react'

import { api } from '../lib/api'
import type {
  DocumentProcessingResult,
  PageProcessingProfile,
  SourceDocument,
} from '../types/api'
import type { DocumentJobProgress } from '../types/jobs'
import { StatusPill } from './StatusPill'

type RouteFilter = 'all' | 'native' | 'ocr' | 'table' | 'visual' | 'review'

type Props = {
  document: SourceDocument | null
  processing?: DocumentProcessingResult
  progress?: DocumentJobProgress
  busy: boolean
  canProcess: boolean
  onProcess: (documentId: string) => void
  onRefresh: () => void
}

function humanize(value: string) {
  return value.replaceAll('_', ' ')
}

function routeMatches(profile: PageProcessingProfile, filter: RouteFilter) {
  if (filter === 'all') return true
  if (filter === 'native') return profile.required_capabilities.includes('native_reading')
  if (filter === 'ocr') return profile.required_capabilities.includes('ocr')
  if (filter === 'table') return profile.required_capabilities.includes('table_structure')
  if (filter === 'visual') return profile.required_capabilities.includes('multimodal_interpretation')
  return profile.required_capabilities.includes('human_review')
    || profile.required_capabilities.includes('visual_relevance_review')
}

function statusTone(status: string) {
  if (status === 'completed' || status === 'succeeded') return 'positive' as const
  if (status === 'failed') return 'danger' as const
  if (status === 'running' || status === 'processing' || status === 'queued') return 'warning' as const
  return 'neutral' as const
}

export function DocumentIntelligencePanel({
  document,
  processing,
  progress,
  busy,
  canProcess,
  onProcess,
  onRefresh,
}: Props) {
  const [routeFilter, setRouteFilter] = useState<RouteFilter>('all')
  const [visiblePages, setVisiblePages] = useState(18)
  const [sourceBusy, setSourceBusy] = useState(false)
  const [sourceError, setSourceError] = useState('')

  const report = processing?.report
  const manifest = report?.processing_manifest
  const profiles = manifest?.page_profiles ?? []
  const filteredProfiles = profiles.filter(
    (profile) => routeMatches(profile, routeFilter),
  )
  const status = progress?.job.status ?? processing?.state.status ?? 'stored'
  const checkpoints = progress?.batches ?? []
  const nativePages = profiles.filter((profile) =>
    profile.required_capabilities.includes('native_reading'),
  ).length
  const ocrPages = profiles.filter((profile) =>
    profile.required_capabilities.includes('ocr'),
  ).length
  const reviewPages = profiles.filter((profile) =>
    profile.required_capabilities.includes('human_review')
      || profile.required_capabilities.includes('visual_relevance_review'),
  ).length
  const visualDecisions = report?.visual_understanding?.decisions ?? []
  const evidence = processing?.evidence_items ?? []
  const pendingReview = evidence.filter(
    (item) => item.validation_status === 'unvalidated',
  ).length
  const completedBatches = checkpoints.filter(
    (batch) => batch.status === 'completed',
  ).length

  async function openSource() {
    if (!document) return
    setSourceBusy(true)
    setSourceError('')

    try {
      const blob = await api.getDocumentContent(
        document.sme_id,
        document.document_id,
      )
      const url = URL.createObjectURL(blob)
      const link = window.document.createElement('a')
      link.href = url
      link.target = '_blank'
      link.rel = 'noopener noreferrer'
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (caught) {
      setSourceError(
        caught instanceof Error
          ? caught.message
          : 'The original source could not be opened.',
      )
    } finally {
      setSourceBusy(false)
    }
  }

  if (!document) {
    return (
      <section className="panel intelligence-panel intelligence-panel--empty">
        <span className="empty-state__icon"><BrainCircuit size={22} /></span>
        <strong>Select a document to inspect its intelligence pipeline</strong>
        <p>Upload or select a source to see PDF routing, OCR, page batches, semantic extraction and reconciliation.</p>
      </section>
    )
  }

  return (
    <section className="panel intelligence-panel">
      <header className="intelligence-panel__header">
        <div className="intelligence-panel__identity">
          <span><BrainCircuit size={23} /></span>
          <div>
            <span className="eyebrow">Document intelligence</span>
            <h2>{document.file_name}</h2>
            <p>{humanize(document.document_type)} · {document.mime_type}</p>
          </div>
        </div>
        <div className="intelligence-panel__actions">
          <StatusPill label={humanize(status)} tone={statusTone(status)} />
          <button className="secondary-button secondary-button--small" type="button" onClick={() => void openSource()} disabled={sourceBusy}>
            {sourceBusy ? <LoaderCircle className="spin" size={15} /> : <Eye size={15} />}
            Open source
          </button>
          <button className="icon-button" type="button" aria-label="Refresh document intelligence" onClick={onRefresh}>
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      {sourceError && <div className="form-error">{sourceError}</div>}
      {processing?.state.failure_message && (
        <div className="intelligence-failure">
          <AlertTriangle size={18} />
          <div>
            <strong>{humanize(processing.state.failure_code ?? 'processing failed')}</strong>
            <p>{processing.state.failure_message}</p>
          </div>
        </div>
      )}

      <div className="pipeline-strip" aria-label="Document processing stages">
        <PipelineStep label="Stored" detail="Integrity checked" state="done" />
        <PipelineStep
          label="Read & route"
          detail={manifest ? `${manifest.total_pages} pages classified` : 'Awaiting analysis'}
          state={manifest ? 'done' : status === 'running' ? 'active' : 'pending'}
        />
        <PipelineStep
          label="OCR & structure"
          detail={manifest ? `${ocrPages} OCR · ${manifest.table_page_count} table pages` : 'Native or scanned routing'}
          state={manifest ? 'done' : status === 'running' ? 'active' : 'pending'}
        />
        <PipelineStep
          label="NLP extraction"
          detail={report ? `${report.deterministic_evidence_ids.length + report.intelligent_evidence_ids.length} grounded claims` : 'Metric and context extraction'}
          state={report ? 'done' : status === 'running' ? 'active' : 'pending'}
        />
        <PipelineStep
          label="Reconcile"
          detail={processing?.reconciliation ? `${processing.reconciliation.clusters.length} evidence clusters` : 'Cross-source consistency'}
          state={processing?.reconciliation ? 'done' : 'pending'}
        />
        <PipelineStep
          label="Human review"
          detail={pendingReview ? `${pendingReview} decisions pending` : evidence.length ? 'Review complete' : 'No extracted evidence'}
          state={pendingReview ? 'active' : evidence.length ? 'done' : 'pending'}
        />
      </div>

      {progress && (status === 'queued' || status === 'running') && (
        <div className="live-processing-banner">
          <LoaderCircle className="spin" size={18} />
          <div>
            <strong>{status === 'queued' ? 'Queued for document intelligence' : 'Processing bounded page batches'}</strong>
            <span>{completedBatches} of {checkpoints.length || 'planned'} batches complete · attempt {progress.job.attempt_count}/{progress.job.max_attempts}</span>
          </div>
        </div>
      )}

      <div className="intelligence-metrics">
        <IntelligenceMetric icon={FileText} label="Pages" value={manifest?.total_pages ?? '—'} detail={manifest?.execution_mode ? `${manifest.execution_mode} execution` : 'Not yet classified'} />
        <IntelligenceMetric icon={ScanText} label="Reading route" value={profiles.length ? `${nativePages}/${ocrPages}` : '—'} detail="native / OCR pages" />
        <IntelligenceMetric icon={Table2} label="Structured tables" value={manifest?.table_page_count ?? '—'} detail="pages with preserved rows" />
        <IntelligenceMetric icon={Sparkles} label="Visual regions" value={manifest?.visual_page_count ?? '—'} detail={`${visualDecisions.length} routed decisions`} />
        <IntelligenceMetric icon={FileSearch} label="Evidence" value={processing?.state.evidence_count ?? 0} detail={`${report?.rejected_intelligent_claim_count ?? 0} rejected AI proposals`} />
        <IntelligenceMetric icon={Layers3} label="Page exceptions" value={reviewPages} detail="unreadable or visually uncertain pages" />
      </div>

      {!report && canProcess && status !== 'running' && status !== 'queued' && (
        <div className="intelligence-callout">
          <div>
            <strong>This source is stored but has not completed analysis.</strong>
            <p>Run the pipeline to route every page through native PDF reading, OCR, table structure and semantic extraction as required.</p>
          </div>
          <button className="primary-button" type="button" disabled={busy} onClick={() => onProcess(document.document_id)}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <BrainCircuit size={16} />}
            {busy ? 'Processing…' : 'Run document intelligence'}
          </button>
        </div>
      )}

      {(checkpoints.length > 0 || manifest?.batches.length) && (
        <section className="intelligence-section">
          <div className="intelligence-section__heading">
            <div><span className="eyebrow">Durable execution</span><h3>Page batches</h3></div>
            <span>{completedBatches || manifest?.batches.length || 0} complete</span>
          </div>
          <div className="batch-grid">
            {(checkpoints.length ? checkpoints : manifest?.batches ?? []).map((batch) => {
              const maximumAttempts = 'max_attempts' in batch ? batch.max_attempts : batch.maximum_attempts
              return (
                <article className={`batch-card batch-card--${batch.status}`} key={batch.batch_id}>
                  <div><strong>{batch.batch_id.replace(`${document.document_id}_`, '').replaceAll('_', ' ')}</strong><StatusPill label={humanize(batch.status)} tone={statusTone(batch.status)} /></div>
                  <p>Pages {batch.page_numbers[0]}–{batch.page_numbers.at(-1)}</p>
                  <small>Attempt {batch.attempt_count}/{maximumAttempts}</small>
                  {batch.failure_message && <span>{batch.failure_message}</span>}
                </article>
              )
            })}
          </div>
        </section>
      )}

      {manifest && (
        <section className="intelligence-section">
          <div className="intelligence-section__heading intelligence-section__heading--routes">
            <div><span className="eyebrow">Page-level routing</span><h3>What each page required</h3></div>
            <div className="route-filters">
              {(['all', 'native', 'ocr', 'table', 'visual', 'review'] as RouteFilter[]).map((filter) => (
                <button type="button" className={routeFilter === filter ? 'active' : ''} key={filter} onClick={() => { setRouteFilter(filter); setVisiblePages(18) }}>
                  {humanize(filter)}
                </button>
              ))}
            </div>
          </div>
          <div className="page-route-grid">
            {filteredProfiles.slice(0, visiblePages).map((profile) => (
              <details className="page-route-card" key={profile.page_number}>
                <summary>
                  <span>Page {profile.page_number}</span>
                  <div>{profile.content_kinds.map((kind) => <i key={kind}>{humanize(kind)}</i>)}</div>
                  <ChevronRight size={15} />
                </summary>
                <div>
                  <p><strong>Text source:</strong> {humanize(profile.text_source ?? 'unreadable')}</p>
                  <p><strong>Processors:</strong> {profile.required_capabilities.map(humanize).join(', ')}</p>
                  <p><strong>Structure:</strong> {profile.table_count} tables · {profile.visual_region_count} visual regions</p>
                  {profile.reasons.map((reason) => <span key={reason}>{reason}</span>)}
                </div>
              </details>
            ))}
          </div>
          {filteredProfiles.length > visiblePages && (
            <button className="secondary-button secondary-button--small route-more" type="button" onClick={() => setVisiblePages((current) => current + 24)}>
              Show 24 more pages
            </button>
          )}
          {!filteredProfiles.length && <div className="muted-copy">No pages use this route.</div>}
        </section>
      )}

      {report && (
        <section className="intelligence-section extraction-diagnostics">
          <div className="intelligence-section__heading">
            <div><span className="eyebrow">Semantic diagnostics</span><h3>How evidence was produced</h3></div>
          </div>
          <div className="diagnostic-grid">
            <article><span>Rules and catalog</span><strong>{report.deterministic_evidence_ids.length}</strong><p>Deterministic, traceable metric matches.</p></article>
            <article><span>Language model</span><strong>{report.intelligent_evidence_ids.length}</strong><p>{report.intelligent_request_count} bounded request{report.intelligent_request_count === 1 ? '' : 's'} · metrics and varied wording.</p><StatusPill label={humanize(report.intelligent_provider_status)} tone={statusTone(report.intelligent_provider_status)} /></article>
            <article><span>Activity & context</span><strong>{report.context_evidence_ids.length}</strong><p>Grounded qualitative facts awaiting human review.</p></article>
            <article><span>Visual understanding</span><strong>{report.visual_evidence_ids.length}</strong><p>Claims grounded in selected charts or diagrams.</p></article>
            <article><span>Rejected proposals</span><strong>{report.rejected_intelligent_claim_count}</strong><p>AI suggestions blocked by grounding or bounds.</p></article>
          </div>
          {report.intelligent_provider_error && <div className="intelligence-failure"><AlertTriangle size={17} /><p>{report.intelligent_provider_error}</p></div>}
        </section>
      )}

      {visualDecisions.length > 0 && (
        <section className="intelligence-section">
          <div className="intelligence-section__heading"><div><span className="eyebrow">Selective multimodal analysis</span><h3>Charts, diagrams and images</h3></div></div>
          <div className="visual-decision-list">
            {visualDecisions.map((decision) => (
              <article key={`${decision.page_number}:${decision.region_id}`}>
                <div><strong>Page {decision.page_number} · {humanize(decision.region_id)}</strong><div><StatusPill label={humanize(decision.relevance)} tone={decision.relevance === 'relevant' ? 'positive' : decision.relevance === 'uncertain' ? 'warning' : 'neutral'} /><StatusPill label={humanize(decision.provider_status)} tone={statusTone(decision.provider_status)} /></div></div>
                <p>{decision.relevance_reason}</p>
                {decision.provider_summary && <blockquote>{decision.provider_summary}</blockquote>}
                {decision.issue && <span><AlertTriangle size={14} /> {decision.issue}</span>}
                {decision.rejected_claims.map((claim) => <small key={`${claim.claim_index}:${claim.indicator_id}`}>{humanize(claim.indicator_id)} rejected: {claim.reason}</small>)}
              </article>
            ))}
          </div>
        </section>
      )}
    </section>
  )
}

function PipelineStep({ label, detail, state }: { label: string; detail: string; state: 'done' | 'active' | 'pending' }) {
  return (
    <div className={`pipeline-step pipeline-step--${state}`}>
      <span>{state === 'done' ? <Check size={14} /> : state === 'active' ? <LoaderCircle className="spin" size={14} /> : null}</span>
      <div><strong>{label}</strong><small>{detail}</small></div>
    </div>
  )
}

function IntelligenceMetric({ icon: Icon, label, value, detail }: { icon: typeof FileText; label: string; value: string | number; detail: string }) {
  return (
    <article>
      <span><Icon size={17} /></span>
      <div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div>
    </article>
  )
}
