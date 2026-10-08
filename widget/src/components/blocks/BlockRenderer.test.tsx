import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { BlockRenderer } from './BlockRenderer'
import type { UIBlock } from './types'

// Server-rendered to static HTML, so these tests need no DOM library. Clicking "Edit" and watching the
// card reopen is therefore not covered here.

function block(type: string, data: Record<string, unknown>, extra: Partial<UIBlock> = {}): UIBlock {
  return { block_id: `${type}-test`, type, schema_version: 1, title: 'A title', data, fallback_text: 'FALLBACK TEXT', ...extra }
}

function html(b: UIBlock, props: { locked?: boolean; busy?: boolean } = {}): string {
  return renderToStaticMarkup(<BlockRenderer block={b} onAction={() => {}} locked={props.locked ?? false} busy={props.busy} />)
}

// One minimal, schema-valid payload per backend block type (mirrors backend/app/schemas/ui_blocks.py).
const SAMPLES: Record<string, Record<string, unknown>> = {
  choice_cards: { field: 'countries', multi: true, options: [{ id: 'uk', label: 'U.K.' }, { id: 'au', label: 'Australia' }], selected: [] },
  quick_chips: { chips: [{ id: 'a', label: 'Chip A' }] },
  range_slider: { field: 'budget', min: 10000, max: 50000, step: 1000, value: 25000, unit: '$' },
  match_cards: { items: [{ id: 'uk', label: 'U.K.', score: 80, reasons: ['Fits your budget'] }] },
  info_card: { heading: 'U.K. quick facts', rows: [{ label: 'Intakes', value: 'September' }] },
  comparison_table: { columns: [{ id: 'uk', label: 'U.K.' }, { id: 'au', label: 'Australia' }], rows: [{ label: 'Tuition', values: ['1', '2'] }] },
  eligibility_meter: { score: 50, verdict: 'You meet some requirements', checks: [{ label: 'English score', ok: true, detail: '6.5 vs 6 minimum' }] },
  profile_summary: { rows: [{ label: 'Budget', value: '$30,000 / year' }], missing: [] },
  lead_form: { fields: [{ id: 'name', label: 'Full name', type: 'text', required: true }] },
  stepper: { steps: [{ title: 'Step one' }, { title: 'Step two' }] },
  accordion: { items: [{ title: 'Item', detail: 'Detail' }] },
  checklist: { items: [{ label: 'Passport' }] },
  timeline: { events: [{ when: 'Jan', title: 'Apply' }, { when: 'Feb', title: 'Offer' }] },
  cost_calculator: { currency: '$', parts: [{ id: 'tuition', label: 'Tuition / year', min: 1000, max: 5000, step: 500, value: 3000 }] },
  journey_cards: { tiles: [{ id: 'find', title: 'Find the right country', description: 'Match countries' }, { id: 'apply', title: 'How to apply', description: 'Steps' }] },
}

describe('BlockRenderer: unknown types', () => {
  it('degrades an unknown type to its fallback text instead of crashing', () => {
    const out = html(block('hologram_card', {}))
    expect(out).toContain('zk-block__fallback')
    expect(out).toContain('FALLBACK TEXT')
    expect(out).not.toContain('<section')
  })

  it('shows the fallback text for a known type at a version this widget cannot render', () => {
    // Versioned rendering (Step 5B): an older bundle must not mis-render a newer block.
    const out = html(block('stepper', SAMPLES.stepper, { schema_version: 99 }))
    expect(out).toContain('zk-block__fallback')
    expect(out).toContain('FALLBACK TEXT')
    expect(out).not.toContain('zk-block--stepper')
  })
})

describe('BlockRenderer: every backend block type renders', () => {
  it.each(Object.keys(SAMPLES))('%s renders its own component, not the fallback', (type) => {
    const out = html(block(type, SAMPLES[type]))
    expect(out).toContain(`zk-block--${type}`)
    expect(out).not.toContain('zk-block__fallback')
  })

  it('dims an already-used input block, but not a self-contained one', () => {
    expect(html(block('choice_cards', SAMPLES.choice_cards), { locked: true })).toContain('zk-block--locked')
    expect(html(block('stepper', SAMPLES.stepper), { locked: true })).not.toContain('zk-block--locked')
  })
})

describe('BlockRenderer: answered cards collapse to a one-line summary', () => {
  it('collapses an answered choice card to the picked label with an Edit button', () => {
    const out = html(block('choice_cards', SAMPLES.choice_cards, { answered: { selected: ['uk'] } }))
    expect(out).toContain('zk-answer')
    expect(out).toContain('U.K.')
    expect(out).toContain('Edit')
    expect(out).not.toContain('zk-block--choice_cards')
  })

  it('collapses an answered slider to the chosen amount', () => {
    const out = html(block('range_slider', SAMPLES.range_slider, { answered: { value: 25000 } }))
    expect(out).toContain('zk-answer')
    expect(out).toContain(`$${Number(25000).toLocaleString()} / year`)
  })

  it('collapses an answered journey card to the chosen tile', () => {
    const out = html(block('journey_cards', SAMPLES.journey_cards, { answered: { journey: 'apply' } }))
    expect(out).toContain('zk-answer')
    expect(out).toContain('How to apply')
  })

  it('collapses a submitted lead form to "Details shared"', () => {
    const out = html(block('lead_form', SAMPLES.lead_form, { answered: { name: 'A' } }))
    expect(out).toContain('zk-answer')
    expect(out).toContain('Details shared')
  })

  it('keeps an unanswered card fully open', () => {
    const out = html(block('choice_cards', SAMPLES.choice_cards))
    expect(out).toContain('zk-block--choice_cards')
    expect(out).not.toContain('zk-answer')
  })

  it('never collapses a non-input block, even if it carries an answer', () => {
    const out = html(block('stepper', SAMPLES.stepper, { answered: { anything: true } }))
    expect(out).toContain('zk-block--stepper')
    expect(out).not.toContain('zk-answer')
  })

  it('stays open when the answer has nothing to summarise (empty selection)', () => {
    const out = html(block('choice_cards', SAMPLES.choice_cards, { answered: { selected: [] } }))
    expect(out).toContain('zk-block--choice_cards')
    expect(out).not.toContain('zk-answer')
  })

  it('disables Edit while a reply is streaming', () => {
    const out = html(block('choice_cards', SAMPLES.choice_cards, { answered: { selected: ['uk'] } }), { busy: true })
    expect(out).toMatch(/<button[^>]*disabled/)
  })
})
