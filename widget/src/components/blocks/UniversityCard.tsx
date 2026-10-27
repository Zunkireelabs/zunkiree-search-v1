import type { BlockComponentProps, UniversityCardData } from './types'

// The block's title already names the university, so the card is just its facts.
export function UniversityCard({ block }: BlockComponentProps<UniversityCardData>) {
  return (
    <div className="zk-info zk-university">
      <dl className="zk-info__rows">
        {block.data.rows.map((r, i) => (
          <div key={i} className="zk-info__row"><dt>{r.label}</dt><dd>{r.value}</dd></div>
        ))}
      </dl>
    </div>
  )
}
