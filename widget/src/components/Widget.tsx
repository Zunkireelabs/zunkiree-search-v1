import React, { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { styles } from './styles'
import { agentStyles } from './agent/agentStyles'
import { CollapsedBar } from './CollapsedBar'
import { ExpandedPanel } from './ExpandedPanel'
import { DockedPanel } from './DockedPanel'
import { bootstrap, destroy, getDockPanel } from '../layout/LayoutManager'
import { enterDock, exitDock, DOCK_MIN_WIDTH } from '../layout/DockStateManager'

// Agent mode render event types
interface AgentRenderEvent {
  component: string
  props: any
}

interface Product {
  id: string
  name: string
  description: string
  price: number | null
  currency: string
  original_price: number | null
  images: string[]
  url: string
  brand: string
  category: string
  sizes: string[]
  colors: string[]
  in_stock: boolean
}

interface CartState {
  items: Array<{
    product_id: string; name: string; price: number; currency: string
    quantity: number; size: string; color: string; image: string; url: string
  }>
  item_count: number
  subtotal: number
  currency: string
}

interface CheckoutData {
  items: Array<{
    name: string; price: number; currency: string; quantity: number
    size: string; color: string; url: string; image: string
  }>
  subtotal: number
  currency: string
  item_count: number
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
  isError?: boolean
  products?: Product[]
  cartUpdate?: CartState
  checkout?: CheckoutData
  toolStatus?: { name: string; status: 'running' | 'done' }
  renderEvents?: AgentRenderEvent[]
}

interface WidgetConfig {
  brand_name: string
  primary_color: string
  placeholder_text: string
  welcome_message: string | null
  quick_actions?: string[]
  supported_languages?: string[]
  website_type?: string | null
  enable_shopping?: boolean
}

interface WidgetProps {
  siteId: string
  apiUrl: string
  widgetMode?: 'search' | 'agent'
}

type WidgetMode = 'bottom-minimized' | 'bottom-expanded' | 'right-docked'

export function Widget({ siteId, apiUrl, widgetMode = 'search' }: WidgetProps) {
  const [mode, setMode] = useState<WidgetMode>('bottom-minimized')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const [sessionId, setSessionId] = useState(() => {
    const key = `zk-session-${siteId}`
    const stored = localStorage.getItem(key)
    if (stored) return stored
    const id = crypto.randomUUID()
    localStorage.setItem(key, id)
    return id
  })
  const [language, setLanguage] = useState('en')
  const [dockPortalTarget, setDockPortalTarget] = useState<HTMLElement | null>(null)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768)
  const [cartItemCount, setCartItemCount] = useState(0)
  const hasAnimated = useRef(false)

  // JS-based mobile detection (host site may lack viewport meta tag,
  // so CSS @media queries can't be trusted)
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth <= 768)
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // Fetch widget config
  useEffect(() => {
    fetch(`${apiUrl}/v1/sites/${siteId}/config`)
      .then(res => {
        if (!res.ok) throw new Error(`Config fetch failed: ${res.status}`)
        return res.json()
      })
      .then(data => {
        setConfig(data)
      })
      .catch(err => {
        console.error('Failed to load widget config:', err)
        setConfig({
          brand_name: 'Assistant',
          primary_color: '#2563eb',
          placeholder_text: 'Ask a question...',
          welcome_message: null,
        })
      })
  }, [apiUrl, siteId])

  // Bootstrap layout wrapper once (synchronous, before paint)
  useLayoutEffect(() => {
    bootstrap()
    setDockPortalTarget(getDockPanel())
    return () => {
      destroy()
    }
  }, [])

  // Dock state: enter/exit via CSS class toggle only (no DOM mutation)
  useEffect(() => {
    if (mode === 'right-docked') {
      enterDock(() => setMode('bottom-expanded'))
    } else {
      exitDock()
    }
  }, [mode])

  // Query API — SSE streaming
  const handleSubmit = async (e: React.FormEvent, directMessage?: string) => {
    e.preventDefault()
    const messageText = (directMessage || input).trim()
    if (!messageText || isLoading) return

    if (mode === 'bottom-minimized') setMode('bottom-expanded')

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: messageText,
    }

    const assistantId = (Date.now() + 1).toString()

    setMessages(prev => {
      const filtered = prev.filter(m => !m.isError)
      return [...filtered, userMessage]
    })
    setInput('')
    setIsLoading(true)

    const payload = {
      site_id: siteId,
      question: userMessage.content,
      session_id: sessionId,
      language: language !== 'en' ? language : undefined,
    }

    try {
      const response = await fetch(`${apiUrl}/api/v1/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail?.message || 'Failed to get answer')
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let streamingContent = ''
      let addedMessage = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const jsonStr = line.slice(6).trim()
          if (!jsonStr) continue

          try {
            const event = JSON.parse(jsonStr)

            if (event.type === 'token') {
              streamingContent += event.data
              if (!addedMessage) {
                addedMessage = true
                setMessages(prev => [...prev, {
                  id: assistantId,
                  role: 'assistant',
                  content: streamingContent,
                }])
              } else {
                setMessages(prev =>
                  prev.map(m => m.id === assistantId ? { ...m, content: streamingContent } : m)
                )
              }
            } else if (event.type === 'products') {
              // Product search results
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, products: event.data } : m)
              )
            } else if (event.type === 'cart_update') {
              // Cart state update
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, cartUpdate: event.data } : m)
              )
            } else if (event.type === 'checkout') {
              // Checkout data
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, checkout: event.data } : m)
              )
            } else if (event.type === 'tool_call') {
              // Tool execution status
              if (!addedMessage) {
                addedMessage = true
                setMessages(prev => [...prev, {
                  id: assistantId,
                  role: 'assistant',
                  content: '',
                  toolStatus: { name: event.name, status: event.status },
                }])
              } else {
                setMessages(prev =>
                  prev.map(m => m.id === assistantId ? {
                    ...m,
                    toolStatus: { name: event.name, status: event.status },
                  } : m)
                )
              }
            } else if (event.type === 'done') {
              if (event.session_id) {
                setSessionId(event.session_id)
                localStorage.setItem(`zk-session-${siteId}`, event.session_id)
              }
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? {
                  ...m,
                  content: event.answer,
                  suggestions: event.suggestions,
                  toolStatus: undefined,
                } : m)
              )
              setIsLoading(false)
            } else if (event.type === 'error') {
              throw new Error(event.message)
            }
          } catch (parseErr) {
            if (parseErr instanceof SyntaxError) continue
            throw parseErr
          }
        }
      }
    } catch (error) {
      console.error('[Zunkiree] Stream error:', error)
      const errorMsg = error instanceof Error ? error.message : 'Sorry, I encountered an error. Please try again.'
      setMessages(prev => [...prev, {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: errorMsg,
        isError: true,
      }])
    } finally {
      setIsLoading(false)
    }
  }

  // Agent mode SSE handler — calls /v1/sites/{siteId}/agent/chat
  // SSE format from Hono: "event: <type>\ndata: <json>\nid: <n>\n\n"
  const handleAgentSubmit = async (e: React.FormEvent, directMessage?: string) => {
    e.preventDefault()
    const messageText = (directMessage || input).trim()
    if (!messageText || isLoading) return

    if (mode === 'bottom-minimized') setMode('bottom-expanded')

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: messageText,
    }
    const assistantId = (Date.now() + 1).toString()

    setMessages(prev => [...prev.filter(m => !m.isError), userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await fetch(`${apiUrl}/v1/sites/${siteId}/agent/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionId },
        body: JSON.stringify({
          sessionId,
          message: userMessage.content,
        }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.error || 'Failed to get response')
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let streamingContent = ''
      let addedMessage = false
      let renderEvents: AgentRenderEvent[] = []
      let currentEventType = ''

      const ensureMessage = () => {
        if (!addedMessage) {
          addedMessage = true
          setMessages(prev => [...prev, {
            id: assistantId,
            role: 'assistant',
            content: streamingContent,
            renderEvents: [...renderEvents],
          }])
        }
      }

      const updateMessage = (updates: Partial<Message>) => {
        setMessages(prev =>
          prev.map(m => m.id === assistantId ? { ...m, ...updates } : m)
        )
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEventType = line.slice(6).trim()
            continue
          }
          if (line.startsWith('id:') || line.trim() === '') continue
          if (!line.startsWith('data:')) continue

          const jsonStr = line.slice(5).trim()
          if (!jsonStr) continue

          try {
            const eventData = JSON.parse(jsonStr)

            switch (currentEventType) {
              case 'message': {
                // Streaming text content
                streamingContent += eventData.content || ''
                ensureMessage()
                updateMessage({ content: streamingContent })
                break
              }

              case 'tool_call': {
                // Show tool execution status
                const toolName = (eventData.name || '').replace(/_/g, ' ')
                ensureMessage()
                updateMessage({
                  toolStatus: { name: toolName, status: 'running' },
                })
                break
              }

              case 'tool_result': {
                // Tool finished
                ensureMessage()
                updateMessage({ toolStatus: undefined })
                break
              }

              case 'render': {
                // Rich UI component to render
                const re = eventData as AgentRenderEvent
                renderEvents = [...renderEvents, re]
                ensureMessage()
                updateMessage({ renderEvents: [...renderEvents] })
                // Track cart item count from cart_view events
                if (re.component === 'cart_view' && Array.isArray(re.props?.items)) {
                  setCartItemCount(re.props.items.length)
                }
                break
              }

              case 'done': {
                ensureMessage()
                updateMessage({ toolStatus: undefined })
                setIsLoading(false)
                break
              }

              case 'error': {
                throw new Error(eventData.error || 'Agent error')
              }

              default: {
                // Unknown event type — try to use as message content
                if (eventData.content) {
                  streamingContent += eventData.content
                  ensureMessage()
                  updateMessage({ content: streamingContent })
                }
              }
            }
          } catch (parseErr) {
            if (parseErr instanceof SyntaxError) continue
            throw parseErr
          }
        }
      }
    } catch (error) {
      console.error('[Zunkiree Agent] Stream error:', error)
      setMessages(prev => [...prev, {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: error instanceof Error ? error.message : 'Sorry, something went wrong.',
        isError: true,
      }])
    } finally {
      setIsLoading(false)
    }
  }

  // Unified submit handler — routes to search or agent mode
  const handleUnifiedSubmit = widgetMode === 'agent' ? handleAgentSubmit : handleSubmit

  const handleAddToCart = (productId: string, size?: string, color?: string) => {
    let msg = `Add product ${productId} to my cart`
    if (size) msg += `, size ${size}`
    if (color) msg += `, color ${color}`
    setInput(msg)
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    handleUnifiedSubmit(fakeEvent, msg)
  }

  const handleRemoveFromCart = (index: number) => {
    const msg = `Remove item ${index + 1} from my cart`
    setInput(msg)
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    handleUnifiedSubmit(fakeEvent, msg)
  }

  const handleCheckout = () => {
    const msg = 'I want to checkout'
    setInput(msg)
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    handleUnifiedSubmit(fakeEvent, msg)
  }

  const handleViewProduct = (slug: string) => {
    const msg = `Show me details for ${slug}`
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    handleUnifiedSubmit(fakeEvent, msg)
  }

  const handleViewCart = () => {
    const msg = 'Show my cart'
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    handleUnifiedSubmit(fakeEvent, msg)
  }

  const handleContinueShopping = () => {
    const msg = 'Show me more products'
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    handleUnifiedSubmit(fakeEvent, msg)
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion)
    if (mode === 'bottom-minimized') setMode('bottom-expanded')
  }

  const handleOpen = () => {
    hasAnimated.current = true
    setMode('bottom-expanded')
  }

  const handleMinimize = () => {
    hasAnimated.current = true
    setMode('bottom-minimized')
  }

  const handleDock = () => {
    if (window.innerWidth < DOCK_MIN_WIDTH) return
    setMode('right-docked')
  }

  const handleUndock = () => {
    setMode('bottom-expanded')
  }

  const brandName = config?.brand_name || siteId
  const primaryColor = config?.primary_color || '#2563eb'
  const enableShopping = config?.enable_shopping === true

  // Get current suggestions: last assistant message's, or config quick_actions
  const getSuggestions = (): string[] => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && messages[i].suggestions?.length) {
        return messages[i].suggestions!
      }
    }
    return config?.quick_actions || []
  }

  const placeholder = config?.placeholder_text || `Ask ${brandName} a question\u2026`

  return (
    <div className={isMobile ? 'zk-mobile' : ''}>
      <style>{styles(primaryColor)}</style>
      {widgetMode === 'agent' && <style>{agentStyles(primaryColor)}</style>}

      {mode === 'bottom-minimized' && (
        <CollapsedBar
          brandName={brandName}
          suggestions={getSuggestions()}
          animate={!hasAnimated.current}
          hasMessages={messages.length > 0}
          onClick={handleOpen}
          onSuggestionClick={handleSuggestionClick}
        />
      )}

      {mode === 'bottom-expanded' && (
        <ExpandedPanel
          brandName={brandName}
          messages={messages}
          suggestions={getSuggestions()}
          input={input}
          isLoading={isLoading}
          onInputChange={setInput}
          onSubmit={handleUnifiedSubmit}
          onSuggestionClick={handleSuggestionClick}
          onClose={handleMinimize}
          onDock={handleDock}
          placeholder={placeholder}
          apiUrl={apiUrl}
          siteId={siteId}
          sessionId={sessionId}
          supportedLanguages={config?.supported_languages || []}
          language={language}
          onLanguageChange={setLanguage}
          onAddToCart={handleAddToCart}
          onRemoveFromCart={handleRemoveFromCart}
          onCheckout={handleCheckout}
          onViewProduct={handleViewProduct}
          onViewCart={handleViewCart}
          onContinueShopping={handleContinueShopping}
          enableShopping={enableShopping}
          cartItemCount={cartItemCount}
        />
      )}

      {mode === 'right-docked' && dockPortalTarget && createPortal(
        <DockedPanel
          brandName={brandName}
          messages={messages}
          suggestions={getSuggestions()}
          input={input}
          isLoading={isLoading}
          onInputChange={setInput}
          onSubmit={handleUnifiedSubmit}
          onSuggestionClick={handleSuggestionClick}
          onMinimize={handleMinimize}
          onUndock={handleUndock}
          placeholder={placeholder}
          apiUrl={apiUrl}
          siteId={siteId}
          sessionId={sessionId}
          supportedLanguages={config?.supported_languages || []}
          language={language}
          onLanguageChange={setLanguage}
          onAddToCart={handleAddToCart}
          onRemoveFromCart={handleRemoveFromCart}
          onCheckout={handleCheckout}
          onViewProduct={handleViewProduct}
          onViewCart={handleViewCart}
          onContinueShopping={handleContinueShopping}
          enableShopping={enableShopping}
          cartItemCount={cartItemCount}
        />,
        dockPortalTarget,
      )}
    </div>
  )
}
