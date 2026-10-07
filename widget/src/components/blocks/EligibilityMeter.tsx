import type { BlockComponentProps, EligibilityData } from './types'
import { CheckIcon, Ring, idx } from './ui'

export function EligibilityMeter({ block }: BlockComponentProps<EligibilityData>) {
  const { score, verdict, checks } = block.data
  return (
    <div>
      <div className="zk-elig__top">
        <Ring value={score} size={76} stroke={8} />
        <div className="zk-elig__verdict">{verdict}</div>
      </div>
      <ul className="zk-elig__checks">
        {checks.map((c, i) => (
          <li key={i} className={c.ok ? 'zk-elig__ok' : 'zk-elig__no'} style={idx(i)}>
            <span className="zk-elig__icon">{c.ok ? <CheckIcon size={11} /> : '!'}</span>
            <div><strong>{c.label}</strong><em>{c.detail}</em></div>
          </li>
        ))}
      </ul>
    </div>
  )
}
