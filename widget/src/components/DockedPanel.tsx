import React, { useRef, useEffect, useState } from 'react'
import { MarkdownContent } from './Markdown'
import { Autocomplete } from './Autocomplete'
import { ProductGrid } from './ProductGrid'
import { CartView } from './CartView'
import { CheckoutView } from './CheckoutView'
import { WishlistView } from './WishlistView'
import { AddressForm } from './AddressForm'
import { PaymentPending } from './PaymentPending'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
  isError?: boolean
  products?: any[]
  cartUpdate?: any
  checkout?: any
  wishlistUpdate?: any[]
  addressForm?: any
  paymentPending?: { checkoutUrl?: string }
  toolStatus?: { name: string; status: 'running' | 'done' }
  imagePreview?: string
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
  supportedLanguages: string[]
  language: string
  onLanguageChange: (lang: string) => void
  onAddToCart?: (productId: string, size?: string, color?: string) => void
  onRemoveFromCart?: (index: number) => void
  onCheckout?: () => void
  onAddToWishlist?: (productId: string) => void
  onRemoveFromWishlist?: (productId: string) => void
  onMoveToCart?: (productId: string, size?: string, color?: string) => void
  onAddressSubmit?: (billing: any, shipping: any, email: string, sameAsBilling: boolean) => void
  isOrderSubmitting?: boolean
  streamingId?: string | null
  onImageSearch?: (base64: string) => void
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
  onAddToWishlist,
  onRemoveFromWishlist,
  onMoveToCart,
  onAddressSubmit,
  isOrderSubmitting,
  streamingId,
  onImageSearch,
}: DockedPanelProps) {
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const userScrolledUp = useRef(false)

  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container) return
    const onScroll = () => {
      const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 80
      userScrolledUp.current = !atBottom
    }
    container.addEventListener('scroll', onScroll, { passive: true })
    return () => container.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!userScrolledUp.current) {
      const container = messagesContainerRef.current
      if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
      }
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

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !onImageSearch) return
    e.target.value = ''
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        const maxSize = 512
        let { width, height } = img
        if (width > maxSize || height > maxSize) {
          if (width > height) { height = Math.round(height * maxSize / width); width = maxSize }
          else { width = Math.round(width * maxSize / height); height = maxSize }
        }
        canvas.width = width
        canvas.height = height
        canvas.getContext('2d')!.drawImage(img, 0, 0, width, height)
        const base64 = canvas.toDataURL('image/jpeg', 0.8).split(',')[1]
        onImageSearch(base64)
      }
      img.src = reader.result as string
    }
    reader.readAsDataURL(file)
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
                  streamingId === message.id ? (
                    <span id="zk-streaming-msg">{message.content}</span>
                  ) : (
                    <MarkdownContent content={message.content} />
                  )
                ) : (
                  <>
                    {message.imagePreview && (
                      <img
                        src={`data:image/jpeg;base64,${message.imagePreview}`}
                        alt="Uploaded"
                        style={{ maxWidth: '120px', borderRadius: '8px', marginBottom: '6px', display: 'block' }}
                      />
                    )}
                    {message.content}
                  </>
                )}
              </div>
              {message.products && message.products.length > 0 && onAddToCart && (
                <ProductGrid
                  products={message.products}
                  onAddToCart={onAddToCart}
                  onAddToWishlist={onAddToWishlist}
                />
              )}
              {message.cartUpdate && onRemoveFromCart && onCheckout && (
                <CartView cart={message.cartUpdate} onRemoveItem={onRemoveFromCart} onCheckout={onCheckout} />
              )}
              {message.checkout && (
                <CheckoutView checkout={message.checkout} brandName={brandName} />
              )}
              {message.wishlistUpdate && onRemoveFromWishlist && onMoveToCart && (
                <WishlistView
                  items={message.wishlistUpdate}
                  onRemove={onRemoveFromWishlist}
                  onMoveToCart={onMoveToCart}
                />
              )}
              {message.addressForm && onAddressSubmit && (
                <AddressForm
                  checkout={message.addressForm}
                  onSubmit={onAddressSubmit}
                  isSubmitting={isOrderSubmitting || false}
                />
              )}
              {message.paymentPending && (
                <PaymentPending checkoutUrl={message.paymentPending.checkoutUrl} />
              )}
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
            <button type="button" className="zk-input-icon zk-input-icon--left" aria-label="Attach image" title="Attach image" onClick={() => fileInputRef.current?.click()}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="M21 15l-5-5L5 21" />
              </svg>
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleFileSelect} />
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
            {input.trim() ? (
              <button
                type="submit"
                className="zk-send"
                disabled={isLoading}
                aria-label="Send message"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            ) : (
              <button type="button" className="zk-input-icon zk-input-icon--right" aria-label="Voice input" title="Voice input">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="23" />
                  <line x1="8" y1="23" x2="16" y2="23" />
                </svg>
              </button>
            )}
          </div>
        </div>
        <div className="zk-powered-by">
          Powered by <a href="https://zunkireelabs.com" target="_blank" rel="noopener noreferrer">Zunkiree</a>
        </div>
      </form>
    </div>
  )
}
