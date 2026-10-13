import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Widget } from './Widget'

// SBAL demo-blocker regression: handleBookService/handleServiceDetails/
// handleBookRoom used to call handleSubmit(null as any, text), and
// handleSubmit's first line is e.preventDefault() — clicking a card's
// Book/Details button threw a TypeError before any fetch ever ran.

function sseResponse(events: Array<Record<string, unknown>>) {
  const body = events.map(e => `data: ${JSON.stringify(e)}\n\n`).join('')
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

const CONFIG = {
  brand_name: 'Test Clinic',
  primary_color: '#2563eb',
  placeholder_text: 'Ask a question...',
  welcome_message: null,
  website_type: 'clinic',
  service_cards: true,
}

const SERVICE = { id: 'svc-1', name: 'Dental Cleaning', price: 1500, duration: 30, image_url: null }

describe('Widget service card actions', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    // jsdom doesn't implement scrollTo; ExpandedPanel calls it to keep
    // the message list pinned to the bottom.
    Element.prototype.scrollTo = vi.fn()
    fetchMock = vi.fn((url: string) => {
      if (url.includes('/widget/config/')) {
        return Promise.resolve(new Response(JSON.stringify(CONFIG), { status: 200 }))
      }
      // Any /query/stream call: return a minimal "done" event by default,
      // the first (service-listing) call also attaches ui.services.
      return Promise.resolve(sseResponse([
        { type: 'token', data: 'Here you go' },
        { type: 'done', answer: 'Here you go', suggestions: [], ui: { services: [SERVICE] } },
      ]))
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function renderWithServiceCard() {
    render(<Widget siteId="test-site" apiUrl="http://api.test" />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    // Open the widget and ask a question that returns a service card.
    fireEvent.click(screen.getByText(/ask test clinic a question/i))
    const textarea = await screen.findByPlaceholderText('Ask a question...')
    fireEvent.change(textarea, { target: { value: 'what services do you have?' } })
    fireEvent.click(screen.getByRole('button', { name: /send message/i }))

    await screen.findByText('Dental Cleaning')
  }

  it('clicking Details sends "Tell me more about <name>" without throwing', async () => {
    await renderWithServiceCard()
    fetchMock.mockClear()

    fireEvent.click(screen.getByRole('button', { name: /details/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse((init as RequestInit).body as string).question).toBe(
      'Tell me more about Dental Cleaning'
    )
  })

  it('clicking Book sends "I\'d like to book <name>" without throwing', async () => {
    await renderWithServiceCard()
    fetchMock.mockClear()

    fireEvent.click(screen.getByRole('button', { name: /^book$/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse((init as RequestInit).body as string).question).toBe(
      "I'd like to book Dental Cleaning"
    )
  })
})
