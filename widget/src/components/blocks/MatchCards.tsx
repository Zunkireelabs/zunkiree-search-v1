import type { BlockComponentProps, MatchCardsData, ReasonStatus } from './types'
import { idx } from './ui'

// Each reason says what it checked and how it came out; the mark is decoration, the label is for screen readers.
const MARK: Record<ReasonStatus, { glyph: string; label: string }> = {
  pass: { glyph: '✓', label: 'Meets' },
  partial: { glyph: '~', label: 'Partly' },
  fail: { glyph: '!', label: 'Does not meet' },
  info: { glyph: 'i', label: 'Note' },
}

export function MatchCards({ block, onAction, locked }: BlockComponentProps<MatchCardsData>) {
  return (
    <div className="zk-match-list">
      {block.data.items.map((item, i) => (
        <div key={item.id} className={`zk-match zk-match--${item.tier}`} style={idx(i)}>
          <div className="zk-match__body">
            <div className="zk-match__head">
              {item.icon && <span className="zk-match__flag">{item.icon}</span>}
              <span className="zk-match__label">{item.label}</span>
              <span className={`zk-match__tier zk-match__tier--${item.tier}`}>{item.tier_label}</span>
            </div>
            <ul className="zk-match__reasons">
              {item.reasons.map((r, j) => (
                <li key={j} className={`zk-match__reason zk-match__reason--${r.status}`}>
                  <span className="zk-match__mark" role="img" aria-label={MARK[r.status].label}>{MARK[r.status].glyph}</span>
                  <span>{r.text}</span>
                </li>
              ))}
            </ul>
            {!locked && (
              <button
                type="button" className="zk-match__more"
                onClick={() => onAction({
                  blockId: block.block_id, blockType: block.type, actionId: 'explore',
                  values: { country: item.id }, displayText: `Tell me more about ${item.label}`,
                })}
              >
                Explore {item.label} →
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
