import { FileSearch } from 'lucide-react'

export function ComingSoonPage() {
  return (
    <section className="panel coming-soon">
      <span className="coming-soon__icon"><FileSearch size={28} /></span>
      <span className="eyebrow">Next workspace</span>
      <h1>Evidence review</h1>
      <p>
        The document-to-evidence review interface is the next frontend batch. The API,
        validation states and source provenance are already in place behind it.
      </p>
    </section>
  )
}
