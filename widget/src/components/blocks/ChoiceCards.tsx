import { useState } from 'react'
import type { BlockComponentProps, ChoiceCardsData } from './types'
import { CheckIcon, idx } from './ui'

export function ChoiceCards({ block, onAction, locked }: BlockComponentProps<ChoiceCardsData>) {
  const { multi, options, field } = block.data
  const [selected, setSelected] = useState<string[]>(block.data.selected || [])

  const send = (ids: string[]) => {
    const labels = options.filter(o => ids.includes(o.id)).map(o => o.label)
    onAction({
      blockId: block.block_id, blockType: block.type, actionId: 'select',
      values: { field, selected: ids }, displayText: labels.join(', '),
    })
  }

  const tap = (id: string) => {
    if (locked) return
    if (multi) {
      setSelected(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]))
      return
    }
    // Single choice: tapping IS the answer. A beat to see the selection land, then go.
    setSelected([id])
    window.setTimeout(() => send([id]), 220)
  }

  return (
    <div>
      <div className="zk-choice-grid">
        {options.map((o, i) => {
          const on = selected.includes(o.id)
          return (
            <button
              key={o.id} type="button" disabled={locked} style={idx(i)} aria-pressed={on}
              className={`zk-choice${on ? ' zk-choice--on' : ''}${o.icon ? '' : ' zk-choice--text'}`} onClick={() => tap(o.id)}
            >
              {on && <span className="zk-choice__check"><CheckIcon size={11} /></span>}
              {o.icon && <span className="zk-choice__icon">{o.icon}</span>}
              <span className="zk-choice__label">{o.label}</span>
              {o.hint && <span className="zk-choice__hint">{o.hint}</span>}
            </button>
          )
        })}
      </div>
      {multi && !locked && (
        <button type="button" className="zk-block__cta" disabled={!selected.length} onClick={() => selected.length && send(selected)}>
          {selected.length > 1 ? `Continue with ${selected.length} selected` : 'Continue'}
        </button>
      )}
    </div>
  )
}
