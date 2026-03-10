import React, { useRef, useEffect, useState } from 'react'
import { MarkdownContent } from './Markdown'
import { Autocomplete } from './Autocomplete'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
  isError?: boolean
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
  supportedLanguages: string[]
  language: string
  onLanguageChange: (lang: string) => void
}

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'En',
  ne: 'ने',
  hi: 'हि',
  es: 'Es',
  fr: 'Fr',
  de: 'De',
  zh: '中',
  ja: '日',
  ko: '한',
  ar: 'عر',
  pt: 'Pt',
  ru: 'Ру',
  bn: 'বা',
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
}: ExpandedPanelProps) {
  const messagesRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [showAutocomplete, setShowAutocomplete] = useState(false)

  useEffect(() => {
    // Scroll messages to bottom without affecting parent/window scroll
    const container = messagesRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
    if (!isLoading) {
      inputRef.current?.focus({ preventScroll: true })
    }
  }, [messages, isLoading])

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
      <div className="zk-expanded-panel">
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
