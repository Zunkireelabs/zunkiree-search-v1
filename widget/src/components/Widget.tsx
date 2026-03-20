import React, { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react'
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
  checkout_mode?: string
}

interface WishlistItem {
  product_id: string
  name: string
  price: number | null
  currency: string
  original_price: number | null
  image: string
  url: string
  in_stock: boolean
  sizes: string[]
  colors: string[]
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
  isError?: boolean
  products?: Product[]
  cartUpdate?: CartState
  checkout?: CheckoutData
  wishlistUpdate?: WishlistItem[]
  addressForm?: CheckoutData
  paymentPending?: { checkoutUrl?: string }
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
  widgetMode?: 'search' | 'agent'
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
  const [isOrderSubmitting, setIsOrderSubmitting] = useState(false)
  // Ref for streaming content — updates DOM directly, no React re-render
  const streamingRef = useRef<{ id: string; content: string } | null>(null)
  const hasAnimated = useRef(false)

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth <= 768)
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  useEffect(() => {
    fetch(`${apiUrl}/api/v1/widget/config/${siteId}`)
      .then(res => res.json())
      .then(data => setConfig(data))
      .catch(() => setConfig({
        brand_name: 'Assistant', primary_color: '#2563eb',
        placeholder_text: 'Ask a question...', welcome_message: null,
      }))
  }, [apiUrl, siteId])

  useLayoutEffect(() => {
    bootstrap()
    setDockPortalTarget(getDockPanel())
    return () => { destroy() }
  }, [])

  useEffect(() => {
    if (mode === 'right-docked') enterDock(() => setMode('bottom-expanded'))
    else exitDock()
  }, [mode])

  // Direct DOM update for streaming — bypasses React entirely
  const updateStreamingDOM = useCallback((content: string) => {
    const el = document.getElementById('zk-streaming-msg')
    if (el) el.textContent = content
  }, [])

  // Pending display override — set before auto-submitting to show a clean message
  const pendingDisplayText = useRef<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    if (mode === 'bottom-minimized') setMode('bottom-expanded')

    const rawContent = input.trim()
    const displayContent = pendingDisplayText.current || rawContent
    pendingDisplayText.current = null

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: displayContent,
    }
    const assistantId = (Date.now() + 1).toString()

    setMessages(prev => [...prev.filter(m => !m.isError), userMessage])
    setInput('')
    setIsLoading(true)

    const payload = {
      site_id: siteId,
      question: rawContent, // send the full query to the API (with product ID)
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

      // Add empty assistant message once — then update DOM directly
      const ensureMessage = () => {
        if (!addedMessage) {
          addedMessage = true
          streamingRef.current = { id: assistantId, content: '' }
          setMessages(prev => [...prev, {
            id: assistantId,
            role: 'assistant',
            content: '',
          }])
        }
      }

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
              ensureMessage()
              streamingContent += event.data
              // Direct DOM update — zero React overhead
              updateStreamingDOM(streamingContent)
            } else if (event.type === 'products') {
              ensureMessage()
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, products: event.data } : m)
              )
            } else if (event.type === 'cart_update') {
              ensureMessage()
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, cartUpdate: event.data } : m)
              )
            } else if (event.type === 'checkout') {
              ensureMessage()
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, checkout: event.data } : m)
              )
            } else if (event.type === 'address_form') {
              ensureMessage()
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, addressForm: event.data } : m)
              )
            } else if (event.type === 'wishlist_update') {
              ensureMessage()
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? { ...m, wishlistUpdate: event.data } : m)
              )
            } else if (event.type === 'tool_call') {
              ensureMessage()
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? {
                  ...m, toolStatus: { name: event.name, status: event.status },
                } : m)
              )
            } else if (event.type === 'done') {
              if (event.session_id) setSessionId(event.session_id)
              streamingRef.current = null
              // Final commit — one React update with the complete content
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
      streamingRef.current = null
      const errorMsg = error instanceof Error ? error.message : 'Sorry, I encountered an error. Please try again.'
      setMessages(prev => [...prev, {
        id: (Date.now() + 2).toString(), role: 'assistant',
        content: errorMsg, isError: true,
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleAddToCart = (productId: string, size?: string, color?: string) => {
    if (size) {
      let msg = `Add product ${productId} to my cart, size ${size}`
      if (color) msg += `, color ${color}`
      pendingDisplayText.current = `Add this to my cart, size ${size}${color ? `, ${color}` : ''}`
      setInput(msg)
    } else {
      pendingDisplayText.current = 'Add this to my cart — what size should I get?'
      setInput(`I want to add product ${productId} to my cart. What size should I get?`)
    }
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    setTimeout(() => handleSubmit(fakeEvent), 50)
  }

  const handleRemoveFromCart = (index: number) => {
    pendingDisplayText.current = `Remove item ${index + 1} from my cart`
    setInput(`Remove item ${index + 1} from my cart`)
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    setTimeout(() => handleSubmit(fakeEvent), 50)
  }

  const handleCheckout = () => {
    setInput('Checkout')
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    setTimeout(() => handleSubmit(fakeEvent), 50)
  }

  const handleAddToWishlist = (productId: string) => {
    pendingDisplayText.current = 'Save this to my wishlist'
    setInput(`Save product ${productId} to my wishlist`)
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    setTimeout(() => handleSubmit(fakeEvent), 50)
  }

  const handleRemoveFromWishlist = (productId: string) => {
    pendingDisplayText.current = 'Remove this from my wishlist'
    setInput(`Remove product ${productId} from my wishlist`)
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent
    setTimeout(() => handleSubmit(fakeEvent), 50)
  }

  const handleMoveToCart = (productId: string, size?: string, color?: string) => {
    handleAddToCart(productId, size, color)
  }

  const handleAddressSubmit = async (
    billing: { full_name: string; line1: string; line2: string; city: string; state: string; postal_code: string; country: string; phone: string },
    shipping: { full_name: string; line1: string; line2: string; city: string; state: string; postal_code: string; country: string; phone: string } | null,
    email: string,
    sameAsBilling: boolean,
    paymentMethod: 'cod' | 'online' = 'cod',
  ) => {
    setIsOrderSubmitting(true)
    try {
      const orderRes = await fetch(`${apiUrl}/api/v1/orders/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: siteId, session_id: sessionId,
          billing_address: billing, shipping_address: shipping,
          shopper_email: email, same_as_billing: sameAsBilling,
        }),
      })

      if (!orderRes.ok) {
        const data = await orderRes.json().catch(() => ({}))
        throw new Error(data.detail || 'Failed to create order')
      }

      const orderData = await orderRes.json()
      const order = orderData.order

      if (paymentMethod === 'online') {
        const payRes = await fetch(`${apiUrl}/api/v1/orders/${order?.id}/pay`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ success_url: window.location.href, cancel_url: window.location.href }),
        })
        if (!payRes.ok) {
          const data = await payRes.json().catch(() => ({}))
          throw new Error(data.detail || 'Failed to initiate payment')
        }
        const payData = await payRes.json()
        setMessages(prev => [...prev, {
          id: (Date.now() + 3).toString(), role: 'assistant',
          content: `Order **${order?.order_number}** created! Redirecting to secure payment...`,
          paymentPending: { checkoutUrl: payData.checkout_url },
        }])
        if (payData.checkout_url) setTimeout(() => { window.location.href = payData.checkout_url }, 1500)
      } else {
        setMessages(prev => [...prev, {
          id: (Date.now() + 3).toString(), role: 'assistant',
          content: `Order **${order?.order_number}** placed successfully!\n\nTotal: ${order?.currency} ${order?.total?.toLocaleString()}\nPayment: Cash on Delivery\n\nWe'll process your order shortly. Thank you for shopping with us!`,
          suggestions: ['What\'s popular?', 'Show my wishlist'],
        }])
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Failed to process order'
      setMessages(prev => [...prev, {
        id: (Date.now() + 4).toString(), role: 'assistant', content: errorMsg, isError: true,
      }])
    } finally {
      setIsOrderSubmitting(false)
    }
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion)
    if (mode === 'bottom-minimized') setMode('bottom-expanded')
  }

  const handleOpen = () => { hasAnimated.current = true; setMode('bottom-expanded') }
  const handleMinimize = () => { hasAnimated.current = true; setMode('bottom-minimized') }
  const handleDock = () => { if (window.innerWidth < DOCK_MIN_WIDTH) return; setMode('right-docked') }
  const handleUndock = () => { setMode('bottom-expanded') }

  const brandName = config?.brand_name || siteId
  const primaryColor = config?.primary_color || '#2563eb'

  const getSuggestions = (): string[] => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && messages[i].suggestions?.length) return messages[i].suggestions!
    }
    return config?.quick_actions || []
  }

  const placeholder = config?.placeholder_text || `Ask ${brandName} a question\u2026`

  const sharedProps = {
    brandName, messages, suggestions: getSuggestions(), input, isLoading,
    onInputChange: setInput, onSubmit: handleSubmit, onSuggestionClick: handleSuggestionClick,
    placeholder, apiUrl, siteId, supportedLanguages: config?.supported_languages || [],
    language, onLanguageChange: setLanguage, onAddToCart: handleAddToCart,
    onRemoveFromCart: handleRemoveFromCart, onCheckout: handleCheckout,
    onAddToWishlist: handleAddToWishlist, onRemoveFromWishlist: handleRemoveFromWishlist,
    onMoveToCart: handleMoveToCart, onAddressSubmit: handleAddressSubmit, isOrderSubmitting,
    streamingId: streamingRef.current?.id || null,
  }

  return (
    <div className={isMobile ? 'zk-mobile' : ''}>
      <style>{styles(primaryColor)}</style>

      {mode === 'bottom-minimized' && (
        <CollapsedBar
          brandName={brandName} suggestions={getSuggestions()}
          animate={!hasAnimated.current} hasMessages={messages.length > 0}
          onClick={handleOpen} onSuggestionClick={handleSuggestionClick}
        />
      )}

      {mode === 'bottom-expanded' && (
        <ExpandedPanel {...sharedProps} onClose={handleMinimize} onDock={handleDock} />
      )}

      {mode === 'right-docked' && dockPortalTarget && createPortal(
        <DockedPanel {...sharedProps} onMinimize={handleMinimize} onUndock={handleUndock} />,
        dockPortalTarget,
      )}
    </div>
  )
}
