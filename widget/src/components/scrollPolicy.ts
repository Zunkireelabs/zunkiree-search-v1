// Where the chat scrolls when messages change.
//
// The panels used to follow the bottom of the conversation, which suits streaming text. A reply with a card can be taller
// than the chat area, so jumping to its bottom hides its first line and the visitor has to scroll back up. A card reply is
// therefore anchored once at its own top; everything else keeps following the bottom exactly as before.

export interface ScrollMessage {
  id: string
  role: string
  blocks?: unknown[]
  pending?: unknown
}

export type ScrollAction =
  | { type: 'anchor'; id: string }                       // new card reply: scroll to its top, once
  | { type: 'hold' }                                     // same card reply still arriving: stay put
  | { type: 'bottom'; releaseAnchor: boolean }           // follow the bottom; releaseAnchor = we were anchored before

function isCardReply(m: ScrollMessage | undefined): m is ScrollMessage {
  return !!m && m.role === 'assistant' && (!!m.blocks?.length || !!m.pending)
}

export function planScroll(messages: ScrollMessage[], anchoredId: string | null): ScrollAction {
  const last = messages[messages.length - 1]
  if (isCardReply(last)) return last.id === anchoredId ? { type: 'hold' } : { type: 'anchor', id: last.id }
  // Anchoring parks the view away from the bottom, which the "user scrolled up" rule would read as the visitor
  // scrolling up on purpose. The next message must still scroll down, so the anchor is released.
  return { type: 'bottom', releaseAnchor: anchoredId !== null }
}

interface ScrollContainer {
  scrollTop: number
  getBoundingClientRect(): { top: number }
  querySelectorAll(selector: string): ArrayLike<{ dataset: { messageId?: string }; getBoundingClientRect(): { top: number } }>
  scrollTo(options: { top: number; behavior: 'smooth' }): void
}

const TOP_GAP = 8

/** Scroll so the message with this id starts just under the top edge of the chat area. False if it is not on the page. */
export function scrollToMessageTop(container: ScrollContainer, id: string): boolean {
  const el = Array.from(container.querySelectorAll('[data-message-id]')).find(e => e.dataset.messageId === id)
  if (!el) return false
  const top = el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - TOP_GAP
  container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
  return true
}
