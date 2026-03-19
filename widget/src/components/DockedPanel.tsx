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
import { AgentCartConfirmation } from './agent/AgentCartConfirmation'

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

interface DockedPanelProps {
  brandName: string
  messages: Message[]
  suggestions: string[]
  input: string
  isLoading: boolean
  onInputChange: (value: string) => void
  onSubmit: (e: React.FormEvent) => void
  onSuggestionClick: (suggestion: string) => void
  onMinimize: () => void
  onUndock: () => void
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

export function DockedPanel({
  brandName,
  messages,
  suggestions,
  input,
  isLoading,
  onInputChange,
  onSubmit,
  onSuggestionClick,
  onMinimize,
  onUndock,
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
}: DockedPanelProps) {
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [showAutocomplete, setShowAutocomplete] = useState(false)

  useEffect(() => {
    // Scroll messages to bottom without affecting parent/window scroll
    const container = messagesContainerRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
    if (!isLoading) {
      inputRef.current?.focus({ preventScroll: true })
    }
  }, [messages, isLoading])

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

  return (
    <div className="zk-docked">
      {/* Header */}
      <div className="zk-docked__header">
        <span className="zk-docked__title">{brandName}</span>
        <div className="zk-docked__controls">
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
            className="zk-header-btn"
            onClick={onUndock}
            aria-label="Undock panel"
            type="button"
            title="Undock"
          >
            {/* Same split-panel icon as dock button — click toggles back */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <line x1="14" y1="4" x2="14" y2="20" />
            </svg>
          </button>
          <button
            className="zk-header-btn"
            onClick={onMinimize}
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
        <div className="zk-docked__hero">
          <h2 className="zk-docked__hero-title">
            How can {brandName} help?
          </h2>
          {suggestions.length > 0 && (
            <div className="zk-docked__hero-chips">
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
      <div className="zk-docked__messages" ref={messagesContainerRef}>
        <div className="zk-docked__messages-inner">
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
                const isEcommerceComponent = ['product_grid', 'product_detail', 'cart_view', 'wishlist_view', 'checkout', 'order_confirmation', 'cart_confirmation'].includes(re.component)
                if (isEcommerceComponent && !enableShopping) return null

                switch (re.component) {
                  case 'product_grid':
                    return <AgentProductGrid key={`r-${idx}`} products={re.props.products || []} title={re.props.title} onViewProduct={(slug) => onViewProduct?.(slug)} onAddToCart={(slug) => onAddToCart?.(slug)} />
                  case 'product_detail':
                    return <AgentProductDetail key={`r-${idx}`} product={re.props.product} onAddToCart={(slug, _v, label, qty) => { let msg = label ? `${slug}, ${label}` : slug; if (qty && qty > 1) msg += `, quantity ${qty}`; onAddToCart?.(msg) }} onAddToWishlist={(slug) => onAddToCart?.(`save ${slug} to wishlist`)} />
                  case 'cart_view':
                    return <AgentCartView key={`r-${idx}`} items={re.props.items || []} subtotal={re.props.subtotal || 0} onRemoveItem={(id) => onRemoveFromCart?.(id)} onCheckout={() => onCheckout?.()} />
                  case 'wishlist_view':
                    return <WishlistView key={`r-${idx}`} items={re.props.items || []} onRemove={(slug) => onAddToCart?.(`remove ${slug} from wishlist`)} onAddToCart={(slug) => onAddToCart?.(slug)} />
                  case 'categories':
                    return (
                      <div key={`r-${idx}`} className="zk-agent-categories">
                        {(re.props.categories || []).map((cat: string) => (
                          <button key={cat} type="button" className="zk-chip" onClick={() => handleLocalSuggestionClick(`Show me ${cat.replace(/-/g, ' ')}`)}>
                            {cat.replace(/-/g, ' ')}
                          </button>
                        ))}
                      </div>
                    )
                  case 'checkout':
                    return <AgentCheckout key={`r-${idx}`} cartId={re.props.cartId} items={re.props.items || []} subtotal={re.props.subtotal || 0} apiUrl={apiUrl} siteId={siteId} sessionId={sessionId || ''} onContinueShopping={onContinueShopping} />
                  case 'order_confirmation':
                    return <OrderConfirmation key={`r-${idx}`} orderId={re.props.orderId || ''} total={re.props.total || 0} onContinueShopping={onContinueShopping} />
                  case 'cart_confirmation':
                    return <AgentCartConfirmation key={`r-${idx}`} {...re.props} onViewCart={() => handleLocalSuggestionClick('Show my cart')} onContinueShopping={() => {}} />
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

      {/* Input Area */}
      <form className="zk-docked__input" onSubmit={onSubmit} style={{ position: 'relative' }}>
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
  )
}
