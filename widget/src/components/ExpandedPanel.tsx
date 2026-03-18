import React, { useRef, useEffect, useState } from 'react'
import { MarkdownContent } from './Markdown'
import { Autocomplete } from './Autocomplete'
import { ProductGrid } from './ProductGrid'
import { CartView } from './CartView'
import { CheckoutView } from './CheckoutView'
import { AgentProductGrid } from './agent/AgentProductGrid'
import { AgentProductDetail } from './agent/AgentProductDetail'
import { AgentCartView } from './agent/AgentCartView'
import { WishlistView } from './agent/WishlistView'
import { OrderConfirmation } from './agent/OrderConfirmation'
import { AgentCheckout } from './agent/AgentCheckout'

interface AgentRenderEvent {
  component: string
  props: any
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
  isError?: boolean
  products?: any[]
  cartUpdate?: any
  checkout?: any
  toolStatus?: { name: string; status: 'running' | 'done' }
  renderEvents?: AgentRenderEvent[]
}

interface ExpandedPanelProps {
  brandName: string
  messages: Message[]
  suggestions: string[]
  input: string
  isLoading: boolean
  onInputChange: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
  onSuggestionClick: (suggestion: string) => void
  onClose: () => void
  onDock: () => void
  placeholder: string
  apiUrl: string
  siteId: string
  sessionId?: string
  supportedLanguages: string[]
  language: string
  onLanguageChange: (lang: string) => void
  onAddToCart?: (productId: string, size?: string, color?: string) => void
  onRemoveFromCart?: (index: number) => void
  onCheckout?: () => void
  onViewProduct?: (slug: string) => void
  onViewCart?: () => void
  onContinueShopping?: () => void
  enableShopping?: boolean
  cartItemCount?: number
}

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'EN',
  ne: 'NP',
  hi: 'HI',
  es: 'ES',
  fr: 'FR',
  de: 'DE',
  zh: 'ZH',
  ja: 'JA',
  ko: 'KO',
  ar: 'AR',
  pt: 'PT',
  ru: 'RU',
  bn: 'BN',
}

export function ExpandedPanel({
  brandName,
  messages,
  suggestions,
  input,
  isLoading,
  onInputChange,
  onSubmit,
  onSuggestionClick,
  onClose,
  onDock,
  placeholder,
  apiUrl,
  siteId,
  supportedLanguages,
  language,
  onLanguageChange,
  onAddToCart,
  onRemoveFromCart,
  onCheckout,
  onViewProduct,
  onViewCart,
  onContinueShopping,
  enableShopping,
  cartItemCount,
  sessionId,
}: ExpandedPanelProps) {
  const messagesRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [showAutocomplete, setShowAutocomplete] = useState(false)

  useEffect(() => {
    // Scroll messages to bottom without affecting parent/window scroll
    const container = messagesRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
    // Don't auto-focus on mobile — it opens the keyboard and squishes the panel
    if (!isLoading && window.innerWidth > 768) {
      inputRef.current?.focus({ preventScroll: true })
    }
  }, [messages, isLoading])

  // Mobile: reposition panel when virtual keyboard opens/closes
  // so the header always stays visible.
  // Android fires 'resize' on visualViewport; iOS fires both 'resize' and 'scroll'.
  useEffect(() => {
    if (window.innerWidth > 768) return
    const vv = window.visualViewport
    if (!vv) return

    // Store the initial viewport height to detect keyboard
    const fullHeight = window.innerHeight

    const reposition = () => {
      const panel = panelRef.current
      if (!panel) return

      // Keyboard is open if the visual viewport is significantly smaller
      // than the full layout viewport (works on both Android and iOS)
      const keyboardOpen = vv.height < fullHeight * 0.75

      if (keyboardOpen) {
        // Pin panel within the visual viewport (the actually visible area).
        // vv.offsetTop = distance from layout viewport top to visual viewport top
        // vv.height = visible area height (excludes keyboard)
        const top = vv.offsetTop + 8
        const height = vv.height - 16
        panel.style.setProperty('top', `${top}px`, 'important')
        panel.style.setProperty('bottom', 'auto', 'important')
        panel.style.setProperty('height', `${height}px`, 'important')
      } else {
        // Keyboard closed: remove overrides
        panel.style.removeProperty('top')
        panel.style.removeProperty('bottom')
        panel.style.removeProperty('height')
      }
    }

    vv.addEventListener('resize', reposition)
    vv.addEventListener('scroll', reposition)
    return () => {
      vv.removeEventListener('resize', reposition)
      vv.removeEventListener('scroll', reposition)
    }
  }, [])

  // Desktop: capture wheel/trackpad scroll and route to messages area
  useEffect(() => {
    if (window.innerWidth <= 480) return
    const panel = messagesRef.current?.closest('.zk-expanded-panel') as HTMLElement | null
    const msgs = messagesRef.current
    if (!panel || !msgs) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      msgs.scrollTop += e.deltaY
    }
    panel.addEventListener('wheel', onWheel, { passive: false })
    return () => panel.removeEventListener('wheel', onWheel)
  }, [])

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`
    }
  }, [input])

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onInputChange(e.target.value)
    setShowAutocomplete(e.target.value.trim().length >= 2)
    const textarea = e.target
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !isLoading) {
        setShowAutocomplete(false)
        onSubmit(e as unknown as React.FormEvent)
      }
    }
  }

  const handleAutocompleteSelect = (suggestion: string) => {
    onInputChange(suggestion)
    setShowAutocomplete(false)
    inputRef.current?.focus({ preventScroll: true })
  }

  const handleLocalSuggestionClick = (suggestion: string) => {
    onSuggestionClick(suggestion)
    inputRef.current?.focus({ preventScroll: true })
  }

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  return (
    <>
      {/* Subtle backdrop */}
      <div className="zk-backdrop" onClick={handleBackdropClick} />

      {/* Panel */}
      <div className="zk-expanded-panel" ref={panelRef}>
        {/* Header - 64px */}
        <div className="zk-expanded-panel__header">
          <span className="zk-expanded-panel__title">{brandName}</span>
          <div className="zk-expanded-panel__controls">
            {supportedLanguages.length >= 2 && (
              <div className="zk-lang-toggle">
                {supportedLanguages.map(lang => (
                  <button
                    key={lang}
                    type="button"
                    className={`zk-lang-btn${language === lang ? ' zk-lang-btn--active' : ''}`}
                    onClick={() => onLanguageChange(lang)}
                    aria-label={`Switch to ${lang}`}
                  >
                    {LANGUAGE_LABELS[lang] || lang.toUpperCase()}
                  </button>
                ))}
              </div>
            )}
            {enableShopping && (cartItemCount || 0) > 0 && (
              <button
                className="zk-header-cart"
                onClick={onViewCart}
                type="button"
                aria-label={`Cart (${cartItemCount} items)`}
                title="View cart"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z" />
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <path d="M16 10a4 4 0 01-8 0" />
                </svg>
                <span className="zk-header-cart__badge">{cartItemCount}</span>
              </button>
            )}
            <button
              className="zk-header-btn zk-dock-btn"
              onClick={onDock}
              aria-label="Dock panel"
              type="button"
              title="Dock to side"
            >
              {/* Panel-right / dock icon */}
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="4" width="20" height="16" rx="2" />
                <line x1="14" y1="4" x2="14" y2="20" />
              </svg>
            </button>
            <button
              className="zk-header-btn"
              onClick={onClose}
              aria-label="Minimize panel"
              type="button"
              title="Minimize"
            >
              {/* Minus icon */}
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Hero Section - only when no messages */}
        {messages.length === 0 && (
          <div className="zk-expanded-panel__hero">
            <h2 className="zk-expanded-panel__hero-title">
              How can {brandName} help?
            </h2>
            {suggestions.length > 0 && (
              <div className="zk-expanded-panel__hero-chips">
                {suggestions.slice(0, 3).map((suggestion, idx) => (
                  <button
                    key={idx}
                    className="zk-chip"
                    onClick={() => handleLocalSuggestionClick(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Conversation Area */}
        <div className="zk-expanded-panel__messages" ref={messagesRef}>
          <div className="zk-expanded-panel__messages-inner">
            {messages.map(message => (
              <div key={message.id} className={`zk-message zk-message-${message.role}`}>
                <div className="zk-message-content">
                  {message.role === 'assistant' ? (
                    <MarkdownContent content={message.content} />
                  ) : (
                    message.content
                  )}
                </div>
                {message.products && message.products.length > 0 && onAddToCart && (
                  <ProductGrid products={message.products} onAddToCart={onAddToCart} />
                )}
                {message.cartUpdate && onRemoveFromCart && onCheckout && (
                  <CartView cart={message.cartUpdate} onRemoveItem={onRemoveFromCart} onCheckout={onCheckout} />
                )}
                {message.checkout && (
                  <CheckoutView checkout={message.checkout} brandName={brandName} />
                )}
                {message.renderEvents && message.renderEvents.map((re, idx) => {
                  // Gate ecommerce components behind enableShopping
                  const isEcommerceComponent = ['product_grid', 'product_detail', 'cart_view', 'wishlist_view', 'checkout', 'order_confirmation'].includes(re.component)
                  if (isEcommerceComponent && !enableShopping) return null

                  switch (re.component) {
                    case 'product_grid':
                      return (
                        <AgentProductGrid
                          key={`render-${idx}`}
                          products={re.props.products || []}
                          title={re.props.title}
                          onViewProduct={(slug) => {
                            if (onViewProduct) onViewProduct(slug)
                          }}
                          onAddToCart={(slug) => {
                            if (onAddToCart) onAddToCart(slug)
                          }}
                        />
                      )
                    case 'product_detail':
                      return (
                        <AgentProductDetail
                          key={`render-${idx}`}
                          product={re.props.product}
                          onAddToCart={(slug, _varId, varLabel, qty) => {
                            if (onAddToCart) {
                              let msg = varLabel ? `${slug}, ${varLabel}` : slug
                              if (qty && qty > 1) msg += `, quantity ${qty}`
                              onAddToCart(msg)
                            }
                          }}
                          onAddToWishlist={(slug) => {
                            if (onAddToCart) onAddToCart(`save ${slug} to wishlist`)
                          }}
                        />
                      )
                    case 'cart_view':
                      return (
                        <AgentCartView
                          key={`render-${idx}`}
                          items={re.props.items || []}
                          subtotal={re.props.subtotal || 0}
                          onRemoveItem={(itemId) => {
                            if (onRemoveFromCart) onRemoveFromCart(itemId)
                          }}
                          onCheckout={() => {
                            if (onCheckout) onCheckout()
                          }}
                        />
                      )
                    case 'wishlist_view':
                      return (
                        <WishlistView
                          key={`render-${idx}`}
                          items={re.props.items || []}
                          onRemove={(slug) => {
                            if (onAddToCart) onAddToCart(`remove ${slug} from wishlist`)
                          }}
                          onAddToCart={(slug) => {
                            if (onAddToCart) onAddToCart(slug)
                          }}
                        />
                      )
                    case 'categories':
                      return (
                        <div key={`render-${idx}`} className="zk-agent-categories">
                          {(re.props.categories || []).map((cat: string) => (
                            <button
                              key={cat}
                              type="button"
                              className="zk-chip"
                              onClick={() => handleLocalSuggestionClick(`Show me ${cat.replace(/-/g, ' ')}`)}
                            >
                              {cat.replace(/-/g, ' ')}
                            </button>
                          ))}
                        </div>
                      )
                    case 'checkout':
                      return (
                        <AgentCheckout
                          key={`render-${idx}`}
                          cartId={re.props.cartId}
                          items={re.props.items || []}
                          subtotal={re.props.subtotal || 0}
                          apiUrl={apiUrl}
                          siteId={siteId}
                          sessionId={sessionId || ''}
                          onContinueShopping={onContinueShopping}
                        />
                      )
                    case 'order_confirmation':
                      return (
                        <OrderConfirmation
                          key={`render-${idx}`}
                          orderId={re.props.orderId || ''}
                          total={re.props.total || 0}
                          onContinueShopping={onContinueShopping}
                        />
                      )
                    default:
                      return null
                  }
                })}
                {message.suggestions && message.suggestions.length > 0 && (
                  <div className="zk-message__suggestions">
                    {message.suggestions.map((suggestion, idx) => (
                      <button
                        key={idx}
                        className="zk-chip"
                        onClick={() => handleLocalSuggestionClick(suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {isLoading && (
              <div className="zk-message zk-message-assistant">
                <div className="zk-message-content zk-typing">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            )}
            <div />
          </div>
        </div>

        {/* Sticky Input Area */}
        <form className="zk-expanded-panel__input" onSubmit={onSubmit} style={{ position: 'relative' }}>
          <Autocomplete
            apiUrl={apiUrl}
            siteId={siteId}
            query={input}
            onSelect={handleAutocompleteSelect}
            visible={showAutocomplete && !isLoading}
          />
          <div className="zk-input-container">
            <div className="zk-input-inner">
              <textarea
                ref={inputRef}
                className="zk-input"
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                disabled={isLoading}
                rows={1}
              />
              <button
                type="submit"
                className="zk-send"
                disabled={!input.trim() || isLoading}
                aria-label="Send message"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
          <div className="zk-powered-by">
            Powered by <a href="https://zunkireelabs.com" target="_blank" rel="noopener noreferrer">Zunkiree</a>
          </div>
        </form>
      </div>
    </>
  )
}
