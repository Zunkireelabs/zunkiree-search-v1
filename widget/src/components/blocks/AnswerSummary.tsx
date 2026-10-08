import type { UIBlock } from './types'
import { CheckIcon } from './ui'
import { formatMoney } from './money'

// Input blocks collapse into a one-line summary once answered; "Edit" reopens them.
export const COLLAPSIBLE = new Set(['choice_cards', 'range_slider', 'journey_cards', 'lead_form'])

export function summarize(block: UIBlock): string | null {
  const a = block.answered
  if (!a) return null
  switch (block.type) {
    case 'choice_cards': {
      const picked: string[] = a.selected || []
      const labels = (block.data.options as { id: string; label: string }[]).filter(o => picked.includes(o.id)).map(o => o.label)
      return labels.join(', ') || null
    }
    case 'range_slider':
      return `${formatMoney(Number(a.value), block.data.unit)} / year`
    case 'journey_cards':
      return (block.data.tiles as { id: string; title: string }[]).find(t => t.id === a.journey)?.title ?? null
    case 'lead_form':
      return 'Details shared'
    default:
      return null
  }
}

export function AnswerSummary({ question, answer, onEdit, busy }: { question?: string; answer: string; onEdit: () => void; busy?: boolean }) {
  return (
    <div className="zk-answer">
      <span className="zk-answer__tick"><CheckIcon size={12} /></span>
      <span className="zk-answer__text">
        {question && <span className="zk-answer__q">{question}</span>}
        <span className="zk-answer__a">{answer}</span>
      </span>
      <button type="button" className="zk-answer__edit" disabled={busy} onClick={onEdit}>Edit</button>
    </div>
  )
}
