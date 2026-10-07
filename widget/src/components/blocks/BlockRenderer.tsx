import { useEffect, useState } from 'react'
import type { ComponentType } from 'react'
import type { BlockComponentProps, UIBlock, OnBlockAction } from './types'
import { ChoiceCards } from './ChoiceCards'
import { QuickChips } from './QuickChips'
import { RangeSlider } from './RangeSlider'
import { MatchCards } from './MatchCards'
import { InfoCard } from './InfoCard'
import { ComparisonTable } from './ComparisonTable'
import { EligibilityMeter } from './EligibilityMeter'
import { ProfileSummary } from './ProfileSummary'
import { LeadForm } from './LeadForm'
import { Stepper } from './Stepper'
import { Accordion } from './Accordion'
import { Checklist } from './Checklist'
import { Timeline } from './Timeline'
import { CostCalculator } from './CostCalculator'
import { JourneyCards } from './JourneyCards'
import { AnswerSummary, COLLAPSIBLE, summarize } from './AnswerSummary'

// One component per block type: the same type always renders the same way.
const REGISTRY: Record<string, ComponentType<BlockComponentProps>> = {
  choice_cards: ChoiceCards,
  quick_chips: QuickChips,
  range_slider: RangeSlider,
  match_cards: MatchCards,
  info_card: InfoCard,
  comparison_table: ComparisonTable,
  eligibility_meter: EligibilityMeter,
  profile_summary: ProfileSummary,
  lead_form: LeadForm,
  stepper: Stepper,
  accordion: Accordion,
  checklist: Checklist,
  timeline: Timeline,
  cost_calculator: CostCalculator,
  journey_cards: JourneyCards,
}

// Only blocks whose job is to send something to the chat look "used up" once superseded.
// Self-contained ones (stepper, checklist, calculator...) stay fully usable.
const DIM_WHEN_LOCKED = new Set(['choice_cards', 'range_slider', 'lead_form', 'journey_cards', 'match_cards', 'profile_summary', 'quick_chips'])

interface BlockRendererProps {
  block: UIBlock
  onAction: OnBlockAction
  locked: boolean
  // True while a reply is streaming: editing an earlier answer waits until it's done.
  busy?: boolean
}

export function BlockRenderer({ block, onAction, locked, busy = false }: BlockRendererProps) {
  const [editing, setEditing] = useState(false)
  // A fresh answer (including the one just submitted from "Edit") closes the editor.
  useEffect(() => setEditing(false), [block.answered])

  const Component = REGISTRY[block.type]
  // Unknown type (e.g. older widget bundle, newer backend): degrade to text, never crash.
  if (!Component) return <div className="zk-block__fallback">{block.fallback_text}</div>

  const summary = COLLAPSIBLE.has(block.type) && !editing ? summarize(block) : null
  if (summary) return <AnswerSummary question={block.title} answer={summary} busy={busy} onEdit={() => setEditing(true)} />

  // Reopened for editing: start from what they answered.
  let shown = block
  if (editing && block.answered) {
    if (block.type === 'choice_cards') shown = { ...block, data: { ...block.data, selected: block.answered.selected || [] } }
    if (block.type === 'range_slider') shown = { ...block, data: { ...block.data, value: block.answered.value ?? block.data.value } }
  }
  const effectiveLocked = editing ? busy : locked

  return (
    <section className={`zk-block zk-block--${block.type}${effectiveLocked && DIM_WHEN_LOCKED.has(block.type) ? ' zk-block--locked' : ''}`}>
      {(block.title || block.subtitle) && (
        <header className="zk-block__header">
          {block.title && <h4 className="zk-block__title">{block.title}</h4>}
          {block.subtitle && <p className="zk-block__subtitle">{block.subtitle}</p>}
        </header>
      )}
      {block.changed_because && <div className="zk-block__changed">↻ {block.changed_because}</div>}
      <Component block={shown} onAction={onAction} locked={effectiveLocked} />
      {block.sources && block.sources.length > 0 && (
        <footer className="zk-block__sources">Source: {block.sources.join(', ')}</footer>
      )}
    </section>
  )
}
