import type { LucideIcon } from 'lucide-react'

type MetricCardProps = {
  icon: LucideIcon
  label: string
  value: string
  detail: string
  tone?: 'jade' | 'gold' | 'blue' | 'plum'
}

export function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = 'jade',
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <div className="metric-card__head">
        <span className="metric-card__icon">
          <Icon size={19} strokeWidth={2} />
        </span>
        <span className="metric-card__label">{label}</span>
      </div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  )
}
