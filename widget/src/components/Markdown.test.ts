import { describe, it, expect } from 'vitest'
import { markdownToHtml } from './Markdown'

// MarkdownContent puts this HTML into the page with dangerouslySetInnerHTML, so the check is structural: every tag is on the
// allowlist, every attribute is on the allowlist, every href is http(s) or mailto, and no stray < or > survives in the text.
const TAGS = new Set(['p', 'strong', 'em', 'code', 'a', 'ul', 'ol', 'li', 'h3', 'h4', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td'])
const ATTRS = new Set(['class', 'href', 'target', 'rel'])

function assertSafe(html: string): void {
  const tag = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)([^<>]*)>/g
  for (const m of html.matchAll(tag)) {
    expect(TAGS.has(m[2].toLowerCase()), `tag <${m[2]}> in ${html}`).toBe(true)
    if (m[1]) continue
    const attrs = m[3].trim()
    const attr = /([^\s="]+)(?:="([^"]*)")?\s*/y
    for (let pos = 0; pos < attrs.length; ) {
      attr.lastIndex = pos
      const a = attr.exec(attrs)
      expect(a, `attributes "${attrs}" in ${html}`).not.toBeNull()
      expect(ATTRS.has(a![1]), `attribute "${a![1]}" in ${html}`).toBe(true)
      if (a![1] === 'href') expect(a![2], `href in ${html}`).toMatch(/^(https?:\/\/|mailto:)[^<>"]*$/)
      pos = attr.lastIndex
    }
  }
  expect(html.replace(tag, ''), `stray angle bracket in ${html}`).not.toMatch(/[<>]/)
}

const ATTACKS = [
  '<script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '<svg/onload=alert(1)>',
  '"><img src=x onerror=alert(1)>',
  '[click me](javascript:alert(1))',
  '[click me](JaVaScRiPt:alert(1))',
  '[click me](data:text/html,<script>alert(1)</script>)',
  '[x](https://a.com"onmouseover="alert(1))',
  '[x](https://a.com/<img src=x onerror=alert(1)>)',
  '**<img src=x onerror=alert(1)>**',
  '`<script>alert(1)</script>`',
  '[mail me](https://a.com/x@y.com)',
  '[a@b.com](https://a.com)',
  '[x](https://a.com/`b`)',
  '[x](https://a.com/*b*)',
  '[x](https://a.com/__b__)',
  'https://user@evil.com',
  '# <img src=x onerror=alert(1)>\n## <script>x</script>\n### <b onmouseover=x>hi</b>',
  '- <img src=x onerror=alert(1)>\n- [x](javascript:alert(1))',
  '1. <svg onload=alert(1)>',
  '| <img src=x onerror=alert(1)> | b |\n|---|---|\n| <script>x</script> | [x](javascript:alert(1)) |',
]

describe('markdownToHtml: untrusted text', () => {
  it.each(ATTACKS)('stays inert: %s', (attack) => {
    assertSafe(markdownToHtml(attack))
  })

  it('shows typed HTML as text', () => {
    expect(markdownToHtml('<script>alert(1)</script>')).toContain('&lt;script&gt;')
  })

  it('does not turn a javascript: link into a link', () => {
    expect(markdownToHtml('[click me](javascript:alert(1))')).not.toContain('<a ')
  })
})

describe('markdownToHtml: links', () => {
  it('opens an http link in a new tab without leaking the opener', () => {
    expect(markdownToHtml('[Admizz](https://admizz.com/apply)')).toContain(
      '<a href="https://admizz.com/apply" target="_blank" rel="noopener noreferrer">Admizz</a>')
  })

  it('links a bare email address', () => {
    expect(markdownToHtml('write to info@admizz.com today')).toContain('<a href="mailto:info@admizz.com">info@admizz.com</a>')
  })

  it('does not put a link inside a link when the URL or the label holds an email', () => {
    expect(markdownToHtml('[mail me](https://a.com/x@y.com)').match(/<a /g)).toHaveLength(1)
    expect(markdownToHtml('[a@b.com](https://a.com)').match(/<a /g)).toHaveLength(1)
  })

  it('leaves a URL as written when it contains formatting characters', () => {
    const html = markdownToHtml('[x](https://a.com/__a__/*b*/`c`)')
    expect(html).toContain('href="https://a.com/__a__/*b*/`c`"')
  })

  it('keeps bold inside a link label', () => {
    expect(markdownToHtml('[**Apply** now](https://a.com)')).toContain('><strong>Apply</strong> now</a>')
  })

  it('cannot be fooled by text that looks like an internal placeholder', () => {
    const html = markdownToHtml('\u00000\u0000 and \u00009\u0000 [x](https://a.com)')
    assertSafe(html)
    expect(html).not.toContain('undefined')
    expect(html).not.toContain('\u0000')
  })
})

describe('markdownToHtml: the source link the chatbot adds to a reply', () => {
  const line = 'More on Admizz: [UK Student Visa Fee and Health Surcharge](https://admizzeducation.com/answers/uk-student-visa-fee-nepal) (checked October 2026)'

  it('renders as one safe link that opens in a new tab, with the checked date as plain text after it', () => {
    const html = markdownToHtml(`Here are the UK facts.\n\n${line}`)
    assertSafe(html)
    expect(html.match(/<a /g)).toHaveLength(1)
    expect(html).toContain('<a href="https://admizzeducation.com/answers/uk-student-visa-fee-nepal" target="_blank" rel="noopener noreferrer">UK Student Visa Fee and Health Surcharge</a> (checked October 2026)')
  })

  it('stays one safe link when the reply around it holds formatting or an email address', () => {
    const html = markdownToHtml(`**Bold** reply, write to info@admizz.com.\n\n${line}`)
    assertSafe(html)
    expect(html.match(/<a /g)).toHaveLength(2)          // the source link and the auto-linked email, nothing else
    expect(html).toContain('<strong>Bold</strong>')
  })

  it('does not turn a link line with an unapproved scheme into a link', () => {
    for (const bad of ['javascript:alert(1)', 'data:text/html,x', 'JaVaScRiPt:alert(1)']) {
      expect(markdownToHtml(`More on Admizz: [x](${bad})`)).not.toContain('<a ')
    }
  })
})
