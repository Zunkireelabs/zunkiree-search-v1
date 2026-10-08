import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { BlockRenderer } from './BlockRenderer'
import type { UIBlock } from './types'

const ITEMS = [
  { id: 'au', label: 'Australia', icon: '🇦🇺', tier: 'strong', tier_label: 'Strong fit',
    reasons: [{ status: 'pass', text: 'Fits your $40,000 budget' }, { status: 'info', text: 'Post-study work: 2 years' }] },
  { id: 'uk', label: 'U.K.', tier: 'good', tier_label: 'Good fit',
    reasons: [{ status: 'partial', text: 'Within your budget for most options' }] },
  { id: 'ca', label: 'Canada', tier: 'possible', tier_label: 'Possible fit',
    reasons: [{ status: 'partial', text: 'No September intake listed' }, { status: 'pass', text: 'English score meets the 6 minimum' }] },
  { id: 'us', label: 'U.S.A.', tier: 'needs_review', tier_label: 'Needs review',
    reasons: [{ status: 'fail', text: 'English score is below the 6.5 minimum' }] },
]

function html(b: Partial<UIBlock> & { type: string }, props: { locked?: boolean } = {}): string {
  const block = { block_id: 'b-1', schema_version: 2, fallback_text: 'FALLBACK TEXT', ...b } as UIBlock
  return renderToStaticMarkup(<BlockRenderer block={block} onAction={() => {}} locked={props.locked ?? false} />)
}

const matches = () => html({ type: 'match_cards', data: { items: ITEMS } })

describe('match cards show a fit tier, not a percentage', () => {
  it('shows each country with its tier label and tier class', () => {
    const out = matches()
    for (const item of ITEMS) {
      expect(out).toContain(item.label)
      expect(out).toContain(item.tier_label)
      expect(out).toContain(`zk-match__tier--${item.tier}`)
    }
  })

  it('draws no score ring and no percentage', () => {
    const out = matches()
    expect(out).not.toContain('zk-ring')
    expect(out).not.toMatch(/\d\s*%/)
    expect(out).not.toContain('percent')
  })

  it('does not call anything the best match', () => {
    expect(matches().toLowerCase()).not.toContain('best match')
  })

  it('lists the reasons in the order given, each marked with its status', () => {
    const out = matches()
    expect(out.indexOf('Fits your $40,000 budget')).toBeLessThan(out.indexOf('Post-study work: 2 years'))
    for (const status of ['pass', 'partial', 'fail', 'info']) expect(out).toContain(`zk-match__reason--${status}`)
  })

  it('gives each mark a text label for screen readers', () => {
    const out = matches()
    for (const label of ['Meets', 'Partly', 'Does not meet', 'Note']) expect(out).toContain(`aria-label="${label}"`)
  })

  it('offers Explore on each card, and hides it once the card is used up', () => {
    expect(matches()).toContain('Explore Australia')
    expect(html({ type: 'match_cards', data: { items: ITEMS } }, { locked: true })).not.toContain('Explore Australia')
  })

  it('a block still at version 1 (the old percentage shape) shows its plain text instead', () => {
    const old = html({ type: 'match_cards', schema_version: 1, data: { items: [{ id: 'au', label: 'Australia', score: 92, reasons: ['x'] }] } })
    expect(old).toContain('zk-block__fallback')
    expect(old).toContain('FALLBACK TEXT')
    expect(old).not.toContain('zk-match')
  })
})

describe('eligibility shows a verdict and its checks, not a percentage', () => {
  const eligibility = (checks: { label: string; ok: boolean; detail: string }[], verdict = 'You meet some requirements') =>
    html({ type: 'eligibility_meter', data: { verdict, checks } })

  it('shows the verdict and every check', () => {
    const out = eligibility([{ label: 'English score', ok: true, detail: '6.5 vs 6 minimum' }, { label: 'Academic score', ok: false, detail: '50% vs 60% minimum' }])
    expect(out).toContain('You meet some requirements')
    expect(out).toContain('English score')
    expect(out).toContain('50% vs 60% minimum')   // the detail of one check is fine; a headline percentage is not
  })

  it('draws no ring and no headline percentage', () => {
    const out = eligibility([{ label: 'English score', ok: true, detail: '6.5 vs 6 minimum' }])
    expect(out).not.toContain('zk-ring')
    expect(out).not.toContain('percent')
  })

  it('marks the verdict as fully met only when every check passes', () => {
    expect(eligibility([{ label: 'a', ok: true, detail: 'd' }])).toContain('zk-elig__badge--ok')
    expect(eligibility([{ label: 'a', ok: true, detail: 'd' }, { label: 'b', ok: false, detail: 'd' }])).toContain('zk-elig__badge--some')
  })

  it('a version 1 eligibility block shows its plain text instead', () => {
    const old = html({ type: 'eligibility_meter', schema_version: 1, data: { score: 80, verdict: 'v', checks: [] } })
    expect(old).toContain('zk-block__fallback')
  })
})
