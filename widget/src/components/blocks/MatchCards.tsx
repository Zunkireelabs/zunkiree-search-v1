import type { BlockComponentProps, MatchCardsData } from './types'
import { Ring, idx } from './ui'

export function MatchCards({ block, onAction, locked }: BlockComponentProps<MatchCardsData>) {
  return (
    <div className="zk-match-list">
      {block.data.items.map((item, i) => (
        <div key={item.id} className="zk-match" style={idx(i)}>
          <Ring value={item.score} size={58} />
          <div className="zk-match__body">
            <div className="zk-match__head">
              {item.icon && <span className="zk-match__flag">{item.icon}</span>}
              <span className="zk-match__label">{item.label}</span>
              {i === 0 && <span className="zk-match__badge">Best match</span>}
            </div>
            <ul className="zk-match__reasons">
              {item.reasons.map((r, j) => <li key={j}>{r}</li>)}
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
