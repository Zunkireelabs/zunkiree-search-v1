import type { BlockComponentProps, InfoCardData } from './types'

export function InfoCard({ block }: BlockComponentProps<InfoCardData>) {
  const { icon, heading, rows } = block.data
  return (
    <div className="zk-info">
      <div className="zk-info__head">{icon && <span>{icon}</span>}{heading}</div>
      <dl className="zk-info__rows">
        {rows.map((r, i) => (
          <div key={i} className="zk-info__row"><dt>{r.label}</dt><dd>{r.value}</dd></div>
        ))}
      </dl>
    </div>
  )
}
