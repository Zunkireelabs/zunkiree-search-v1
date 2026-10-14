import { useState } from 'react'
import type { BlockComponentProps, AccordionData } from './types'
import { idx } from './ui'

// Expandable cards: one open at a time, smooth height animation.
export function Accordion({ block }: BlockComponentProps<AccordionData>) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <div className="zk-accordion">
      {block.data.items.map((item, i) => {
        const isOpen = open === i
        return (
          <div key={i} style={idx(i)} className={`zk-acc${isOpen ? ' zk-acc--open' : ''}`}>
            <button type="button" className="zk-acc__head" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : i)}>
              <span className="zk-acc__text">
                <span className="zk-acc__title">{item.title}</span>
                {item.summary && <span className="zk-acc__summary">{item.summary}</span>}
              </span>
              <span className="zk-acc__chevron">+</span>
            </button>
            <div className="zk-acc__panel"><div><div className="zk-acc__body">{item.detail}</div></div></div>
          </div>
        )
      })}
    </div>
  )
}
