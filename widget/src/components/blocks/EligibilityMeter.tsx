import type { BlockComponentProps, EligibilityData } from './types'
import { CheckIcon, idx } from './ui'

// A verdict and the individual checks behind it. No percentage: it would read as a chance of success.
export function EligibilityMeter({ block }: BlockComponentProps<EligibilityData>) {
  const { verdict, checks } = block.data
  const allMet = checks.every(c => c.ok)
  return (
    <div>
      <div className="zk-elig__top">
        <span className={`zk-elig__badge ${allMet ? 'zk-elig__badge--ok' : 'zk-elig__badge--some'}`} aria-hidden="true">
          {allMet ? <CheckIcon size={16} /> : '!'}
        </span>
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
