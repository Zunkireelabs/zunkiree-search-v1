import { useEffect, useRef, useState } from 'react'
import type { UIBlock } from './types'

// New cards appear silently for a screen-reader user. This visually hidden status region says what just arrived, once, when
// a live reply finishes (never for a conversation restored after a reload).

export function announcementFor(blocks: UIBlock[]): string {
  const titles = blocks.filter(b => b.type !== 'quick_chips' && b.title).map(b => b.title as string)
  const steps = blocks.filter(b => b.type === 'quick_chips').reduce((n, b) => n + (b.data?.chips?.length ?? 0), 0)
  const parts: string[] = []
  if (titles.length) parts.push(titles.join('. '))
  if (steps) parts.push(`${steps} suggested next step${steps === 1 ? '' : 's'} below`)
  return parts.length ? parts.join('. ') : (blocks[0]?.fallback_text ?? '')
}

// null = leave the current announcement alone. Announces only on the moment a reply finishes.
export function announcementAfter(wasBusy: boolean, busy: boolean, messages: { blocks?: UIBlock[] }[]): string | null {
  if (busy || !wasBusy) return null
  const last = messages[messages.length - 1]
  return last?.blocks?.length ? announcementFor(last.blocks) : ''
}

export function BlockAnnouncer({ messages, busy }: { messages: { blocks?: UIBlock[] }[]; busy: boolean }) {
  const [text, setText] = useState('')
  const wasBusy = useRef(false)
  useEffect(() => {
    const next = announcementAfter(wasBusy.current, busy, messages)
    wasBusy.current = busy
    if (next !== null) setText(next)
  }, [busy, messages])
  return <div className="zk-sr-only" role="status" aria-live="polite" aria-atomic="true">{text}</div>
}
