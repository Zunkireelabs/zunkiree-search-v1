import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { BlockRenderer } from './BlockRenderer'
import { SUPPORTED_VERSIONS, isSupported } from './blockVersions'
import type { UIBlock } from './types'

function html(b: Partial<UIBlock> & { type: string }): string {
  const full = { block_id: 'b-1', schema_version: 1, data: { steps: [{ title: 'One' }, { title: 'Two' }] }, fallback_text: 'FALLBACK TEXT', ...b } as UIBlock
  return renderToStaticMarkup(<BlockRenderer block={full} onAction={() => {}} locked={false} />)
}

describe('isSupported', () => {
  it('accepts a listed version', () => {
    expect(isSupported('stepper', 1)).toBe(true)
  })

  it('treats a missing version as v1, because blocks stored before versions existed carry none', () => {
    expect(isSupported('stepper', undefined)).toBe(true)
  })

  it('rejects version 0, a future version and an unknown type', () => {
    expect(isSupported('stepper', 0)).toBe(false)
    expect(isSupported('stepper', 2)).toBe(false)
    expect(isSupported('hologram_card', 1)).toBe(false)
  })

  it('lists every type with at least one version', () => {
    for (const [type, versions] of Object.entries(SUPPORTED_VERSIONS)) {
      expect(versions.length, type).toBeGreaterThan(0)
    }
  })
})

describe('BlockRenderer versioned rendering', () => {
  it('renders a supported version normally', () => {
    const out = html({ type: 'stepper', schema_version: 1 })
    expect(out).toContain('zk-block--stepper')
    expect(out).not.toContain('zk-block__fallback')
  })

  it('renders a block with no schema_version as v1', () => {
    const out = html({ type: 'stepper', schema_version: undefined })
    expect(out).toContain('zk-block--stepper')
  })

  it.each([0, 2, 99])('falls back to plain text for version %i', (version) => {
    const out = html({ type: 'stepper', schema_version: version })
    expect(out).toContain('zk-block__fallback')
    expect(out).toContain('FALLBACK TEXT')
    expect(out).not.toContain('zk-block--stepper')
  })

  it('still falls back for an unknown type, whatever its version', () => {
    expect(html({ type: 'hologram_card', schema_version: 1 })).toContain('zk-block__fallback')
  })
})
