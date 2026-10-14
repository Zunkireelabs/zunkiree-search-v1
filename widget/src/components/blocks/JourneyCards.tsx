import type { BlockComponentProps, JourneyCardsData } from './types'
import { idx } from './ui'

// Welcome: big tiles that start a guided journey.
export function JourneyCards({ block, onAction, locked }: BlockComponentProps<JourneyCardsData>) {
  return (
    <div className="zk-journey">
      {block.data.tiles.map((t, i) => (
        <button
          key={t.id} type="button" disabled={locked} className="zk-tile" style={idx(i)}
          onClick={() => onAction({
            blockId: block.block_id, blockType: block.type, actionId: 'start',
            values: { journey: t.id }, displayText: t.title,
          })}
        >
          {t.icon && <span className="zk-tile__icon">{t.icon}</span>}
          <span className="zk-tile__text">
            <span className="zk-tile__title">{t.title}</span>
            <span className="zk-tile__desc">{t.description}</span>
          </span>
          <span className="zk-tile__go">→</span>
        </button>
      ))}
    </div>
  )
}
