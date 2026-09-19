import { ArrowUpRight, Building2, MapPin, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { StatusPill } from '../components/StatusPill'
import { api } from '../lib/api'
import type { SME } from '../types/api'

export function CompaniesPage() {
  const [companies, setCompanies] = useState<SME[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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

  return (
    <>
      <section className="page-heading">
        <div>
          <span className="eyebrow">Company intelligence</span>
          <h1>SME portfolio</h1>
          <p>Explore the companies, sectors and evidence records available to you.</p>
        </div>
      </section>

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
                  <Link className="company-card__action" to={`/companies/${company.sme_id}`}>
                    Open company record <ArrowUpRight size={16} />
                  </Link>
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
