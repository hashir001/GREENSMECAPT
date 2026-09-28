import {
  ArrowUpRight,
  Building2,
  LoaderCircle,
  MapPin,
  Plus,
  Search,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { usePermissions } from '../auth/usePermissions'
import { StatusPill } from '../components/StatusPill'
import { api } from '../lib/api'
import type { SME } from '../types/api'

export function CompaniesPage() {
  const navigate = useNavigate()
  const permissions = usePermissions()
  const [companies, setCompanies] = useState<SME[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState<SME>({
    sme_id: '',
    legal_name: '',
    sector: '',
    jurisdiction: '',
  })

  useEffect(() => {
    void api.listSMEs()
      .then(setCompanies)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Companies failed to load.')
      })
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return companies

    return companies.filter((company) =>
      [company.legal_name, company.sector, company.jurisdiction]
        .some((value) => value.toLowerCase().includes(needle)),
    )
  }, [companies, query])

  function updateDraft(field: keyof SME, value: string) {
    setDraft((current) => ({ ...current, [field]: value }))
  }

  async function createCompany(event: FormEvent) {
    event.preventDefault()
    setCreating(true)
    setError('')

    try {
      const next = await api.createSME({
        sme_id: draft.sme_id.trim(),
        legal_name: draft.legal_name.trim(),
        sector: draft.sector.trim(),
        jurisdiction: draft.jurisdiction.trim(),
      })
      setCompanies((current) => [...current, next])
      setCreateOpen(false)
      void navigate(`/companies/${next.sme_id}`)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'The company record could not be created.')
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">{permissions.role === 'investor' ? 'Published opportunities' : 'Company intelligence'}</span>
          <h1>SME portfolio</h1>
          <p>{permissions.role === 'investor' ? 'Explore only reviewer-approved, published SME profiles.' : 'Explore the companies, sectors and evidence records available to you.'}</p>
        </div>
        {permissions.canCreateSMEs && (
          <button className="primary-button" type="button" onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> Add company
          </button>
        )}
      </section>

      {createOpen && (
        <div className="company-create-backdrop" role="presentation" onMouseDown={() => setCreateOpen(false)}>
          <form className="company-create-dialog" onSubmit={(event) => void createCompany(event)} onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span className="eyebrow">New evidence record</span>
                <h2>Add an SME</h2>
                <p>Create the company workspace first, then upload and process its sources.</p>
              </div>
              <button className="icon-button" type="button" aria-label="Close company form" onClick={() => setCreateOpen(false)}><X size={17} /></button>
            </header>
            <div className="company-create-grid">
              <label className="builder-field">Company ID<input required minLength={1} value={draft.sme_id} onChange={(event) => updateDraft('sme_id', event.target.value)} placeholder="sme_ecopack" /></label>
              <label className="builder-field">Legal name<input required minLength={1} value={draft.legal_name} onChange={(event) => updateDraft('legal_name', event.target.value)} placeholder="EcoPack Manufacturing LLC" /></label>
              <label className="builder-field">Sector<input required minLength={1} value={draft.sector} onChange={(event) => updateDraft('sector', event.target.value)} placeholder="Sustainable packaging" /></label>
              <label className="builder-field">Jurisdiction<input required minLength={1} value={draft.jurisdiction} onChange={(event) => updateDraft('jurisdiction', event.target.value)} placeholder="United Arab Emirates" /></label>
            </div>
            <footer>
              <button className="secondary-button" type="button" onClick={() => setCreateOpen(false)}>Cancel</button>
              <button className="primary-button" type="submit" disabled={creating}>
                {creating ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}
                {creating ? 'Creating…' : 'Create company workspace'}
              </button>
            </footer>
          </form>
        </div>
      )}

      <section className="panel portfolio-panel">
        <div className="portfolio-toolbar">
          <label className="search-field">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search company, sector or jurisdiction"
            />
          </label>
          <span className="result-count">{filtered.length} companies</span>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <div className="company-grid">
          {loading
            ? Array.from({ length: 6 }, (_, index) => (
                <div className="skeleton skeleton--company" key={index} />
              ))
            : filtered.map((company, index) => (
                <article className="company-card" key={company.sme_id}>
                  <div className="company-card__top">
                    <span className={`company-avatar company-avatar--${index % 4}`}>
                      <Building2 size={21} />
                    </span>
                    <StatusPill label="Active record" tone="positive" />
                  </div>
                  <h2>{company.legal_name}</h2>
                  <span className="company-card__id">{company.sme_id}</span>
                  <div className="company-card__meta">
                    <span>{company.sector}</span>
                    <span><MapPin size={14} /> {company.jurisdiction}</span>
                  </div>
                  {permissions.role === 'investor'
                    ? <span className="company-card__action">Published profile <StatusPill label="Approved" tone="positive" /></span>
                    : <Link className="company-card__action" to={`/companies/${company.sme_id}`}>
                        Open company record <ArrowUpRight size={16} />
                      </Link>}
                </article>
              ))}
        </div>

        {!loading && !filtered.length && (
          <div className="empty-state">
            <strong>No matching companies</strong>
            <p>Try a different company name, sector or location.</p>
          </div>
        )}
      </section>
    </>
  )
}
