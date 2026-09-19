import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type RankingDatum = {
  name: string
  score: number
  rank: number
}

type TooltipPayload = {
  payload?: RankingDatum
}

function ScoreTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: TooltipPayload[]
}) {
  const item = payload?.[0]?.payload

  if (!active || !item) return null

  return (
    <div className="chart-tooltip">
      <span>Rank {item.rank}</span>
      <strong>{item.name}</strong>
      <p>{Math.round(item.score * 100)} / 100</p>
    </div>
  )
}

export function RankingChart({ data }: { data: RankingDatum[] }) {
  return (
    <div className="ranking-chart" aria-label="Latest SME ranking">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 20, bottom: 4, left: 10 }}
        >
          <CartesianGrid horizontal={false} stroke="#dfe8e2" />
          <XAxis
            type="number"
            domain={[0, 1]}
            tickFormatter={(value: number) => `${Math.round(value * 100)}`}
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#718078', fontSize: 11 }}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={118}
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#18352c', fontSize: 12, fontWeight: 600 }}
          />
          <Tooltip cursor={{ fill: '#f0f6f2' }} content={<ScoreTooltip />} />
          <Bar
            dataKey="score"
            fill="#168a5b"
            radius={[0, 8, 8, 0]}
            maxBarSize={28}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
