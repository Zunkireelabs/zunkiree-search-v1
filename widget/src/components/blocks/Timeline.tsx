import { useState } from 'react'
import type { BlockComponentProps, TimelineData } from './types'
import { idx } from './ui'

export function Timeline({ block }: BlockComponentProps<TimelineData>) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <ol className="zk-timeline">
      {block.data.events.map((ev, i) => {
        const isOpen = open === i
        return (
          <li key={i} style={idx(i)} className={`zk-tl${isOpen ? ' zk-tl--open' : ''}`}>
            <span className="zk-tl__dot" />
            <button type="button" className="zk-tl__head" disabled={!ev.detail} onClick={() => setOpen(isOpen ? null : i)}>
              <span className="zk-tl__when">{ev.when}</span>
              <span className="zk-tl__title">{ev.title}</span>
            </button>
            {isOpen && ev.detail && <p className="zk-tl__detail">{ev.detail}</p>}
          </li>
        )
      })}
    </ol>
  )
}
