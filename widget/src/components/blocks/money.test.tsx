import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MONEY_VECTORS, formatMoney, normalizeCurrency } from './money'
import { BlockRenderer } from './BlockRenderer'
import type { UIBlock } from './types'

describe('formatMoney', () => {
  it.each(MONEY_VECTORS)('formats %d %s as %s', (amount, currency, expected) => {
    expect(formatMoney(amount, currency)).toBe(expected)
  })

  it('does not depend on the browser locale', () => {
    // toLocaleString('de-DE') would print 25.000; the formatter writes its own grouping
    expect(formatMoney(25000, 'USD')).toBe('$25,000')
    expect((25000).toLocaleString('de-DE')).not.toBe('25,000')
  })

  it('accepts a legacy symbol or an ISO code for the same currency', () => {
    expect(normalizeCurrency('$')).toBe('USD')
    expect(normalizeCurrency('usd')).toBe('USD')
    expect(normalizeCurrency('₹')).toBe('INR')
    expect(normalizeCurrency('chf')).toBe('CHF')
  })
})

function html(b: Partial<UIBlock> & { type: string }, extra: Partial<UIBlock> = {}): string {
  const block = { block_id: 'b-1', schema_version: 1, fallback_text: 'FB', ...b, ...extra } as UIBlock
  return renderToStaticMarkup(<BlockRenderer block={block} onAction={() => {}} locked={false} />)
}

describe('money in the education blocks', () => {
  const slider = (unit: string) => ({ type: 'range_slider', data: { field: 'budget', min: 1000000, max: 5000000, step: 100000, value: 2500000, unit } })
  const calc = (currency: string) => ({ type: 'cost_calculator', data: { currency, parts: [{ id: 'tuition', label: 'Tuition / year', min: 100000, max: 900000, step: 50000, value: 500000 }] } })

  it('the budget slider shows NPR with Indian grouping', () => {
    const out = html(slider('NPR'))
    expect(out).toContain('NPR 10,00,000')   // scale minimum
    expect(out).toContain('NPR 50,00,000')   // scale maximum
  })

  it('the cost calculator shows NPR with Indian grouping', () => {
    const out = html(calc('NPR'))
    expect(out).toContain('NPR 1,00,000')
    expect(out).toContain('NPR 9,00,000')
  })

  it('a block stored with a legacy symbol still renders as before', () => {
    expect(html(slider('$'))).toContain('$1,000,000')
    expect(html(calc('$'))).toContain('$100,000')
  })

  it('an answered budget slider collapses to the amount in the same format', () => {
    const out = html(slider('NPR'), { answered: { value: 2500000 } })
    expect(out).toContain('zk-answer')
    expect(out).toContain('NPR 25,00,000 / year')
  })
})
