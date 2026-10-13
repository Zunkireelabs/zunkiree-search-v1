import { describe, it, expect } from 'vitest'
import { planScroll, scrollToMessageTop, type ScrollMessage } from './scrollPolicy'

const user = (id: string): ScrollMessage => ({ id, role: 'user' })
const text = (id: string): ScrollMessage => ({ id, role: 'assistant' })
const card = (id: string): ScrollMessage => ({ id, role: 'assistant', blocks: [{}] })
const pending = (id: string): ScrollMessage => ({ id, role: 'assistant', pending: {} })

describe('planScroll: a reply with a card starts at its top', () => {
  it('anchors a new card reply, so a tall card is read from its first line', () => {
    expect(planScroll([user('u1'), card('a1')], null)).toEqual({ type: 'anchor', id: 'a1' })
  })

  it('anchors while the card is still loading (skeleton)', () => {
    expect(planScroll([user('u1'), pending('a1')], null)).toEqual({ type: 'anchor', id: 'a1' })
  })

  it('holds still while the same reply keeps arriving (sentence, then card), so the page does not jump', () => {
    expect(planScroll([user('u1'), card('a1')], 'a1')).toEqual({ type: 'hold' })
  })

  it('anchors again for the next card reply', () => {
    expect(planScroll([user('u1'), card('a1'), user('u2'), card('a2')], 'a1')).toEqual({ type: 'anchor', id: 'a2' })
  })
})

describe('planScroll: everything else keeps following the bottom', () => {
  it('follows the bottom for a plain text reply (unchanged behaviour)', () => {
    expect(planScroll([user('u1'), text('a1')], null)).toEqual({ type: 'bottom', releaseAnchor: false })
  })

  it('follows the bottom when there are no messages or the last one is the visitor\'s', () => {
    expect(planScroll([], null)).toEqual({ type: 'bottom', releaseAnchor: false })
    expect(planScroll([user('u1')], null)).toEqual({ type: 'bottom', releaseAnchor: false })
  })

  it('treats an empty blocks list as a text reply', () => {
    expect(planScroll([{ id: 'a1', role: 'assistant', blocks: [] }], null)).toEqual({ type: 'bottom', releaseAnchor: false })
  })

  it('un-sticks after a card reply: sending the next message scrolls down even though we were not at the bottom', () => {
    expect(planScroll([user('u1'), card('a1'), user('u2')], 'a1')).toEqual({ type: 'bottom', releaseAnchor: true })
  })

  it('un-sticks for a text reply that follows a card reply', () => {
    expect(planScroll([user('u1'), card('a1'), user('u2'), text('a2')], 'a1')).toEqual({ type: 'bottom', releaseAnchor: true })
  })
})

// A stand-in for the scroll container: no browser layout needed, only the numbers the function reads.
function fakeContainer(opts: { containerTop: number; scrollTop: number; elements: Record<string, number> }) {
  const calls: Array<{ top: number; behavior: string }> = []
  return {
    calls,
    getBoundingClientRect: () => ({ top: opts.containerTop }),
    scrollTop: opts.scrollTop,
    querySelectorAll: () => Object.entries(opts.elements).map(([id, top]) => ({
      dataset: { messageId: id },
      getBoundingClientRect: () => ({ top }),
    })),
    scrollTo: (o: { top: number; behavior: string }) => { calls.push(o) },
  }
}

describe('scrollToMessageTop', () => {
  it('scrolls so the message top sits just under the top edge of the chat area', () => {
    // message is 700px below the container top on screen, and the chat is already scrolled 120px
    const c = fakeContainer({ containerTop: 100, scrollTop: 120, elements: { a1: 800 } })
    expect(scrollToMessageTop(c as never, 'a1')).toBe(true)
    expect(c.calls).toEqual([{ top: 700 + 120 - 8, behavior: 'smooth' }])
  })

  it('never scrolls above the start of the chat', () => {
    const c = fakeContainer({ containerTop: 100, scrollTop: 0, elements: { a1: 104 } })
    scrollToMessageTop(c as never, 'a1')
    expect(c.calls[0].top).toBe(0)
  })

  it('does nothing and says so when the message is not on the page', () => {
    const c = fakeContainer({ containerTop: 0, scrollTop: 0, elements: { a1: 50 } })
    expect(scrollToMessageTop(c as never, 'missing')).toBe(false)
    expect(c.calls).toEqual([])
  })
})
