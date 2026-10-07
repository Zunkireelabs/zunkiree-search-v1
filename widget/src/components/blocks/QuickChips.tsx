import type { BlockComponentProps, QuickChipsData } from './types'

export function QuickChips({ block, onAction, locked }: BlockComponentProps<QuickChipsData>) {
  return (
    <div className="zk-block__chips">
      {block.data.chips.map(c => (
        <button
          key={c.id}
          type="button"
          disabled={locked}
          className="zk-chip"
          onClick={() => onAction({
            blockId: block.block_id, blockType: block.type, actionId: c.id,
            values: { chip: c.id }, displayText: c.label,
          })}
        >
          {c.label}
        </button>
      ))}
    </div>
  )
}
