import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { blockStyles } from './blockStyles'
import { BlockRenderer } from './BlockRenderer'
import { BlockSkeleton } from './BlockSkeleton'
import { BlockErrorBoundary, shouldReset } from './BlockErrorBoundary'
import { BlockAnnouncer, announcementAfter, announcementFor } from './BlockAnnouncer'
import type { UIBlock } from './types'

// ---- a small CSS reader over the REAL stylesheet (no filesystem, no new dependency) ----

interface Rule { media: string | null; selectors: string[]; body: string }

function parse(css: string): Rule[] {
  const out: Rule[] = []
  const skip = (open: number) => {
    let depth = 1, j = open + 1
    while (depth > 0 && j < css.length) { if (css[j] === '{') depth++; else if (css[j] === '}') depth--; j++ }
    return j
  }
  const scan = (media: string | null, from: number, end: number) => {
    let i = from
    while (i < end) {
      const open = css.indexOf('{', i)
      if (open === -1 || open >= end) return
      const head = css.slice(i, open).replace(/\/\*[\s\S]*?\*\//g, '').trim()
      if (head.startsWith('@media')) {
        const close = skip(open)
        scan(head.slice(6).trim(), open + 1, close - 1)
        i = close
      } else if (head.startsWith('@')) {
        i = skip(open)
      } else {
        const close = css.indexOf('}', open)
        out.push({ media, selectors: head.split(',').map(s => s.trim()), body: css.slice(open + 1, close) })
        i = close + 1
      }
    }
  }
  scan(null, 0, css.length)
  return out
}

const CSS = blockStyles('#2563eb')
const RULES = parse(CSS)

const rule = (selector: string, media: string | null = null) => RULES.find(r => r.media === media && r.selectors.includes(selector))
// a selector can appear in several rules; this is the one that actually declares `prop`
const ruleDeclaring = (selector: string, prop: string) =>
  RULES.find(r => r.selectors.includes(selector) && new RegExp(`(?:^|[;\\s])${prop}\\s*:`).test(r.body))
const declared = (r: Rule | undefined, prop: string): string | undefined => {
  const found = [...(r?.body ?? '').matchAll(new RegExp(`(?:^|[;\\s])${prop}\\s*:\\s*([^;]+)`, 'g'))]
  return found.length ? found[found.length - 1][1].trim() : undefined
}
const token = (name: string) => declared(RULES.find(r => declared(r, name) !== undefined), name)!.replace(/\s*\/\*.*$/, '').trim()

function hex(value: string): string {
  const v = value.trim()
  const m = /^var\((--[\w-]+)\)$/.exec(v)
  if (m) return hex(token(m[1]))
  if (/^#[0-9a-f]{3}$/i.test(v)) return '#' + [...v.slice(1)].map(c => c + c).join('')
  return v
}
function luminance(color: string): number {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex(color).slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
const WHITE = '#ffffff'

describe('the contrast checker itself', () => {
  it('flags the two colour pairs that used to ship', () => {
    expect(contrast('#ffffff', '#16a34a')).toBeLessThan(4.5)   // white on the old green
    expect(contrast('#d97706', '#ffffff')).toBeLessThan(4.5)   // the old amber on white
  })
})

describe('text and icons meet WCAG AA contrast (4.5:1), measured from the real stylesheet', () => {
  const cases: [string, string, string][] = [
    ['Strong-fit chip', declared(rule('.zk-match__tier--strong'), 'color')!, declared(rule('.zk-match__tier--strong'), 'background')!],
    ['Possible-fit chip', declared(rule('.zk-match__tier--possible'), 'color')!, declared(rule('.zk-match__tier--possible'), 'background')!],
    ['Needs-review chip', declared(rule('.zk-match__tier--needs_review'), 'color')!, '#f1f5f9'],
    ['reason mark: meets', declared(rule('.zk-match__reason--pass .zk-match__mark'), 'color')!, WHITE],
    ['reason mark: partly', declared(rule('.zk-match__reason--partial .zk-match__mark'), 'color')!, WHITE],
    ['reason mark: does not meet', declared(rule('.zk-match__reason--fail .zk-match__mark'), 'color')!, WHITE],
    ['eligibility badge: all met', declared(rule('.zk-elig__badge'), 'color')!, declared(rule('.zk-elig__badge--ok'), 'background')!],
    ['eligibility badge: some met', declared(rule('.zk-elig__badge'), 'color')!, declared(rule('.zk-elig__badge--some'), 'background')!],
    ['secondary text on the page background', token('--zk-muted'), token('--zk-bg')],
    ['body text', token('--zk-ink-2'), WHITE],
  ]
  it.each(cases)('%s', (_name, fg, bg) => {
    expect(fg, 'foreground not found in the stylesheet').toBeTruthy()
    expect(bg, 'background not found in the stylesheet').toBeTruthy()
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5)
  })
})

describe('touch targets are at least 44px on phones and touch devices', () => {
  const minHeight = (selector: string, media: string | null) => parseInt(declared(rule(selector, media), 'min-height') ?? '0', 10)

  it.each(['.zk-block__chips .zk-chip', '.zk-match__more', '.zk-answer__edit'])('%s', (selector) => {
    expect(minHeight(`.zk-mobile ${selector}`, null)).toBeGreaterThanOrEqual(44)
    expect(minHeight(selector, '(pointer: coarse)')).toBeGreaterThanOrEqual(44)
  })

  it.each(['.zk-choice', '.zk-tile', '.zk-check', '.zk-acc__head', '.zk-block__cta'])('%s', (selector) => {
    expect(minHeight(`.zk-mobile ${selector}`, null)).toBeGreaterThanOrEqual(44)
    expect(minHeight(selector, '(pointer: coarse)')).toBeGreaterThanOrEqual(44)
  })

  it('the touch rules are scoped to the block chips, not every chip in the widget', () => {
    expect(rule('.zk-mobile .zk-chip')).toBeUndefined()
    expect(rule('.zk-chip', '(pointer: coarse)')).toBeUndefined()
  })
})

describe('comparison table', () => {
  const block = {
    block_id: 'c-1', type: 'comparison_table', schema_version: 1, title: 'U.K. vs Australia', fallback_text: 'FB',
    data: { columns: [{ id: 'uk', label: 'U.K.' }, { id: 'au', label: 'Australia' }], rows: [{ label: 'Tuition', values: ['$1', '$2'] }] },
  } as UIBlock
  const html = renderToStaticMarkup(<BlockRenderer block={block} onAction={() => {}} locked={false} />)

  it('is a labelled, keyboard-focusable scroll region with a caption and header scopes', () => {
    expect(html).toContain('role="region"')
    expect(html).toContain('tabindex="0"')
    expect(html).toContain('aria-label="U.K. vs Australia, scrollable"')
    expect(html).toContain('<caption class="zk-sr-only">U.K. vs Australia</caption>')
    expect(html).toContain('scope="col"')
    expect(html).toContain('scope="row"')
  })

  it('keeps the row labels (and the corner header) in view while scrolling sideways', () => {
    for (const selector of ['.zk-compare tbody th', '.zk-compare thead th:first-child']) {
      const sticky = ruleDeclaring(selector, 'position')
      expect(declared(sticky, 'position'), selector).toBe('sticky')
      expect(declared(sticky, 'left'), selector).toBe('0')
    }
  })

  it('scrolls inside its own box, has minimum column widths, and shows a focus ring', () => {
    expect(declared(rule('.zk-compare'), 'overflow-x')).toBe('auto')
    for (const selector of ['.zk-compare td', '.zk-compare thead th:not(:first-child)']) {
      expect(parseInt(declared(ruleDeclaring(selector, 'min-width'), 'min-width') ?? '0', 10), selector).toBeGreaterThanOrEqual(80)
    }
    expect(declared(rule('.zk-compare:focus-visible'), 'outline')).toContain('2px solid')
  })
})

describe('screen-reader helpers', () => {
  it('the hidden-text class hides visually but not from assistive technology', () => {
    const r = rule('.zk-sr-only')
    expect(declared(r, 'position')).toBe('absolute')
    expect(declared(r, 'clip')).toBeTruthy()
    expect(r!.body).not.toMatch(/display\s*:\s*none|visibility\s*:\s*hidden/)
  })

  it('the loading skeleton is announced as busy and named', () => {
    const out = renderToStaticMarkup(<BlockSkeleton blockType="stepper" label="Finding the steps…" />)
    expect(out).toContain('role="status"')
    expect(out).toContain('aria-busy="true"')
    expect(out).toContain('aria-label="Finding the steps…"')
  })
})

describe('announcing new cards', () => {
  const card = (type: string, title: string | undefined, extra: Partial<UIBlock> = {}) =>
    ({ block_id: `${type}-1`, type, schema_version: 1, title, data: {}, fallback_text: `${type} text`, ...extra }) as UIBlock
  const chips = (n: number) => card('quick_chips', undefined, { data: { chips: Array.from({ length: n }, (_, i) => ({ id: `c${i}`, label: `Chip ${i}` })) } })

  it('names the cards and counts the suggested next steps', () => {
    expect(announcementFor([card('profile_summary', 'What I know about you'), card('match_cards', 'Countries that match your profile'), chips(3)]))
      .toBe('What I know about you. Countries that match your profile. 3 suggested next steps below')
  })

  it('uses the singular for one next step', () => {
    expect(announcementFor([card('lead_form', 'Talk to a counselor'), chips(1)])).toBe('Talk to a counselor. 1 suggested next step below')
  })

  it('announces only the next steps when that is all there is', () => {
    expect(announcementFor([chips(2)])).toBe('2 suggested next steps below')
  })

  it('falls back to the plain text when nothing has a title', () => {
    expect(announcementFor([card('stepper', undefined)])).toBe('stepper text')
  })

  it('announces only at the moment a live reply finishes', () => {
    const done = [{ blocks: [card('match_cards', 'Matches')] }]
    expect(announcementAfter(true, false, done)).toBe('Matches')        // a reply just finished with cards
    expect(announcementAfter(true, true, done)).toBeNull()              // still streaming
    expect(announcementAfter(false, false, done)).toBeNull()            // a conversation restored after a reload is not announced
  })

  it('clears the announcement when the finished reply has no cards', () => {
    expect(announcementAfter(true, false, [{ blocks: [card('match_cards', 'Matches')] }, { blocks: undefined }])).toBe('')
    expect(announcementAfter(true, false, [])).toBe('')
  })

  it('renders as a quiet polite status region that is empty until something arrives', () => {
    const out = renderToStaticMarkup(<BlockAnnouncer messages={[]} busy={false} />)
    expect(out).toContain('role="status"')
    expect(out).toContain('aria-live="polite"')
    expect(out).toContain('zk-sr-only')
    expect(out).toContain('></div>')
  })
})

describe('a block that fails to render', () => {
  // React's server renderer does not use error boundaries, so the catch path is exercised on the class directly.
  const make = (children: unknown = <p>fine</p>) =>
    new BlockErrorBoundary({ fallbackText: 'PLAIN TEXT VERSION', resetKey: 'blk-1', children: children as never })

  it('turns an error into a failed state', () => {
    expect(BlockErrorBoundary.getDerivedStateFromError()).toEqual({ failed: true })
  })

  it('renders the block normally until it fails', () => {
    expect(renderToStaticMarkup(make().render() as never)).toBe('<p>fine</p>')
  })

  it('shows the plain-text version once it has failed', () => {
    const boundary = make()
    boundary.state = { failed: true }
    const out = renderToStaticMarkup(boundary.render() as never)
    expect(out).toContain('zk-block__fallback')
    expect(out).toContain('PLAIN TEXT VERSION')
    expect(out).not.toContain('fine')
  })

  it('logs the failure for developers', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    make().componentDidCatch(new Error('boom'))
    expect(spy).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })

  it('gives a different block a fresh chance, but not the same one', () => {
    expect(shouldReset('blk-1', 'blk-2', true)).toBe(true)
    expect(shouldReset('blk-1', 'blk-1', true)).toBe(false)
    expect(shouldReset('blk-1', 'blk-2', false)).toBe(false)
  })

  it('does not change how a healthy block renders', () => {
    const ok = { block_id: 'x', type: 'stepper', schema_version: 1, fallback_text: 'FB', data: { steps: [{ title: 'a' }, { title: 'b' }] } } as UIBlock
    expect(renderToStaticMarkup(<BlockRenderer block={ok} onAction={() => {}} locked={false} />)).toContain('zk-block--stepper')
  })
})
