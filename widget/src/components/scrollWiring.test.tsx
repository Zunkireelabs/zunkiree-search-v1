import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { DockedPanel } from './DockedPanel'
import { ExpandedPanel } from './ExpandedPanel'

// jsdom has no layout, so every element reports 0 for its position and a fixed height here. That is enough to tell the two
// scroll targets apart: the bottom of the chat is scrollHeight (5000), the top of a message is 0.
const BOTTOM = 5000
type Props = React.ComponentProps<typeof DockedPanel>
type Msg = Props['messages'][number]

const user = (id: string): Msg => ({ id, role: 'user', content: 'hello' })
const text = (id: string): Msg => ({ id, role: 'assistant', content: 'Hi there' })
const card = (id: string): Msg => ({ id, role: 'assistant', content: '', pending: { block_type: 'journey_cards', label: 'Loading' } })

function props(messages: Msg[], websiteType = 'education'): Props {
  const noop = () => {}
  return {
    brandName: 'Admizz', messages, suggestions: [], input: '', isLoading: false, onInputChange: noop, onSubmit: noop,
    onSuggestionClick: noop, onMinimize: noop, onUndock: noop, placeholder: 'Ask', apiUrl: 'http://x', siteId: 's',
    supportedLanguages: [], language: 'en', onLanguageChange: noop, websiteType,
  } as unknown as Props
}

describe('DockedPanel scrolling', () => {
  let scrollTo: ReturnType<typeof vi.fn>

  beforeEach(() => {
    scrollTo = vi.fn()
    Element.prototype.scrollTo = scrollTo as never
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, get: () => BOTTOM })
  })
  afterEach(() => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).scrollHeight
  })

  const lastTop = () => scrollTo.mock.calls[scrollTo.mock.calls.length - 1][0].top

  it('marks every message so the panel can find where a reply starts', () => {
    const { container } = render(<DockedPanel {...props([user('u1'), text('a1')])} />)
    expect([...container.querySelectorAll('[data-message-id]')].map(e => e.getAttribute('data-message-id'))).toEqual(['u1', 'a1'])
  })

  it('follows the bottom for a text reply, as before', () => {
    const { rerender } = render(<DockedPanel {...props([user('u1')])} />)
    rerender(<DockedPanel {...props([user('u1'), text('a1')])} />)
    expect(lastTop()).toBe(BOTTOM)
  })

  it('scrolls to the top of a card reply instead of its bottom', () => {
    const { rerender } = render(<DockedPanel {...props([user('u1')])} />)
    rerender(<DockedPanel {...props([user('u1'), card('a1')])} />)
    expect(lastTop()).toBe(0)
    expect(scrollTo.mock.calls[scrollTo.mock.calls.length - 1][0].behavior).toBe('smooth')
  })

  it('does not jump again while the same card reply is still arriving', () => {
    const { rerender } = render(<DockedPanel {...props([user('u1')])} />)
    rerender(<DockedPanel {...props([user('u1'), card('a1')])} />)
    const before = scrollTo.mock.calls.length
    rerender(<DockedPanel {...props([user('u1'), { ...card('a1'), content: 'Here you go' }])} />)
    expect(scrollTo.mock.calls.length).toBe(before)
  })

  it('scrolls down for the visitor\'s next message even after the view was parked at a card top', () => {
    const { container, rerender } = render(<DockedPanel {...props([user('u1')])} />)
    rerender(<DockedPanel {...props([user('u1'), card('a1')])} />)
    // the browser reports the scroll the anchor caused; the old rule read "not at the bottom" as "visitor scrolled up"
    fireEvent.scroll(container.querySelector('.zk-docked__messages')!)
    rerender(<DockedPanel {...props([user('u1'), card('a1'), user('u2')])} />)
    expect(lastTop()).toBe(BOTTOM)
  })

  it('never anchors for a tenant whose replies carry no cards (unchanged for them)', () => {
    const { rerender } = render(<DockedPanel {...props([user('u1')], 'clinic')} />)
    rerender(<DockedPanel {...props([user('u1'), text('a1')], 'clinic')} />)
    rerender(<DockedPanel {...props([user('u1'), text('a1'), user('u2'), text('a2')], 'clinic')} />)
    expect(scrollTo.mock.calls.every(c => c[0].top === BOTTOM)).toBe(true)
  })
})

describe('ExpandedPanel scrolling (same rules as the docked panel)', () => {
  let scrollTo: ReturnType<typeof vi.fn>
  type XProps = React.ComponentProps<typeof ExpandedPanel>

  const xprops = (messages: Msg[]): XProps => {
    const noop = () => {}
    return {
      brandName: 'Admizz', messages, suggestions: [], input: '', isLoading: false, onInputChange: noop, onSubmit: noop,
      onSuggestionClick: noop, onClose: noop, onDock: noop, placeholder: 'Ask', apiUrl: 'http://x', siteId: 's',
      supportedLanguages: [], language: 'en', onLanguageChange: noop, websiteType: 'education',
    } as unknown as XProps
  }

  beforeEach(() => {
    scrollTo = vi.fn()
    Element.prototype.scrollTo = scrollTo as never
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, get: () => BOTTOM })
  })
  afterEach(() => {
    delete (HTMLElement.prototype as unknown as Record<string, unknown>).scrollHeight
  })

  const lastTop = () => scrollTo.mock.calls[scrollTo.mock.calls.length - 1][0].top

  it('marks messages, anchors a card reply at its top, and still follows the bottom for text', () => {
    const { container, rerender } = render(<ExpandedPanel {...xprops([user('u1')])} />)
    rerender(<ExpandedPanel {...xprops([user('u1'), text('a1')])} />)
    expect(lastTop()).toBe(BOTTOM)
    rerender(<ExpandedPanel {...xprops([user('u1'), text('a1'), user('u2'), card('a2')])} />)
    expect(lastTop()).toBe(0)
    expect([...container.querySelectorAll('[data-message-id]')].map(e => e.getAttribute('data-message-id'))).toEqual(['u1', 'a1', 'u2', 'a2'])
  })

  it('scrolls down for the next visitor message after parking at a card top', () => {
    const { container, rerender } = render(<ExpandedPanel {...xprops([user('u1')])} />)
    rerender(<ExpandedPanel {...xprops([user('u1'), card('a1')])} />)
    fireEvent.scroll(container.querySelector('.zk-expanded-panel__messages')!)
    rerender(<ExpandedPanel {...xprops([user('u1'), card('a1'), user('u2')])} />)
    expect(lastTop()).toBe(BOTTOM)
  })
})
