import React, { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { styles } from './styles'
import { CollapsedBar } from './CollapsedBar'
import { ExpandedPanel } from './ExpandedPanel'
import { DockedPanel } from './DockedPanel'
import { bootstrap, destroy, getDockPanel } from '../layout/LayoutManager'
import { enterDock, exitDock, DOCK_MIN_WIDTH } from '../layout/DockStateManager'

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
}

type WidgetMode = 'bottom-minimized' | 'bottom-expanded' | 'right-docked'

export function Widget({ siteId, apiUrl }: WidgetProps) {
  const [mode, setMode] = useState<WidgetMode>('bottom-minimized')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [language, setLanguage] = useState('en')
  const [dockPortalTarget, setDockPortalTarget] = useState<HTMLElement | null>(null)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 768)
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
    fetch(`${apiUrl}/api/v1/widget/config/${siteId}`)
      .then(res => res.json())
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
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    if (mode === 'bottom-minimized') setMode('bottom-expanded')

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
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
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, products: event.data } : m)
              )
            } else if (event.type === 'cart_update') {
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, cartUpdate: event.data } : m)
              )
            } else if (event.type === 'checkout') {
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, checkout: event.data } : m)
              )
            } else if (event.type === 'tool_call') {
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
              if (event.session_id) setSessionId(event.session_id)
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

  // ── Direct REST cart operations (no LLM round-trip) ──

  const handleAddToCart = async (productId: string, size?: string, color?: string): Promise<void> => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/cart/${sessionId}/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ site_id: siteId, product_id: productId, quantity: 1, size: size || '', color: color || '' }),
      })
      if (!res.ok) throw new Error('Failed to add to cart')
      const cart: CartState = await res.json()
      // Append a cart update as an assistant message so it renders inline
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: `Added to cart (${cart.item_count} item${cart.item_count !== 1 ? 's' : ''})`,
        cartUpdate: cart,
      }])
    } catch (err) {
      console.error('[Zunkiree] Add to cart error:', err)
    }
  }

  const handleRemoveFromCart = async (index: number) => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/cart/${sessionId}/${index}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Failed to remove from cart')
      const cart: CartState = await res.json()
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: cart.item_count > 0 ? `Item removed (${cart.item_count} remaining)` : 'Cart is now empty',
        cartUpdate: cart,
      }])
    } catch (err) {
      console.error('[Zunkiree] Remove from cart error:', err)
    }
  }

  const handleCheckout = async () => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/cart/${sessionId}/checkout`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to checkout')
      const checkout: CheckoutData = await res.json()
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: 'Here are your items ready for checkout:',
        checkout,
      }])
    } catch (err) {
      console.error('[Zunkiree] Checkout error:', err)
    }
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
          onSubmit={handleSubmit}
          onSuggestionClick={handleSuggestionClick}
          onClose={handleMinimize}
          onDock={handleDock}
          placeholder={placeholder}
          apiUrl={apiUrl}
          siteId={siteId}
          supportedLanguages={config?.supported_languages || []}
          language={language}
          onLanguageChange={setLanguage}
          onAddToCart={handleAddToCart}
          onRemoveFromCart={handleRemoveFromCart}
          onCheckout={handleCheckout}
        />
      )}

      {mode === 'right-docked' && dockPortalTarget && createPortal(
        <>
          {/* Inject styles into dock portal (outside shadow DOM) */}
          <style>{styles(primaryColor)}</style>
          <DockedPanel
            brandName={brandName}
            messages={messages}
            suggestions={getSuggestions()}
            input={input}
            isLoading={isLoading}
            onInputChange={setInput}
            onSubmit={handleSubmit}
            onSuggestionClick={handleSuggestionClick}
            onMinimize={handleMinimize}
            onUndock={handleUndock}
            placeholder={placeholder}
            apiUrl={apiUrl}
            siteId={siteId}
            supportedLanguages={config?.supported_languages || []}
            language={language}
            onLanguageChange={setLanguage}
            onAddToCart={handleAddToCart}
            onRemoveFromCart={handleRemoveFromCart}
            onCheckout={handleCheckout}
          />
        </>,
        dockPortalTarget,
      )}
    </div>
  )
}
