import { useState } from 'react'
import type { BlockComponentProps, ChecklistData } from './types'
import { CheckIcon, idx } from './ui'

function load(key: string): number[] {
  try { return JSON.parse(localStorage.getItem(key) || '[]') } catch { return [] }
}

// Tick items off; progress is remembered in this browser.
export function Checklist({ block }: BlockComponentProps<ChecklistData>) {
  const { items } = block.data
  const key = `zk_chk_${block.block_id}`
  const [checked, setChecked] = useState<Set<number>>(() => new Set(load(key)))

  const toggle = (i: number) => setChecked(prev => {
    const next = new Set(prev)
    next.has(i) ? next.delete(i) : next.add(i)
    try { localStorage.setItem(key, JSON.stringify([...next])) } catch { /* private mode: still works for this view */ }
    return next
  })

  return (
    <div className="zk-checklist">
      <div className="zk-progress"><div style={{ width: `${(checked.size / items.length) * 100}%` }} /></div>
      <div className="zk-progress__label">{checked.size} of {items.length} ready</div>
      <ul className="zk-checklist__list">
        {items.map((item, i) => (
          <li key={i} style={idx(i)}>
            <label className={`zk-check${checked.has(i) ? ' zk-check--on' : ''}`}>
              <input type="checkbox" checked={checked.has(i)} onChange={() => toggle(i)} />
              <span className="zk-check__box">{checked.has(i) && <CheckIcon size={12} />}</span>
              <span className="zk-check__text">
                <span className="zk-check__label">{item.label}</span>
                {item.note && <span className="zk-check__note">{item.note}</span>}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {checked.size === items.length && <div className="zk-celebrate">🎉 Everything's ready. Nice work.</div>}
    </div>
  )
}
