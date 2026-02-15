import React, { useRef, useEffect } from 'react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
  isError?: boolean
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
}: DockedPanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`
    }
  }, [input])

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onInputChange(e.target.value)
    const textarea = e.target
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !isLoading) {
        onSubmit(e as unknown as React.FormEvent)
      }
    }
  }

  const handleLocalSuggestionClick = (suggestion: string) => {
    onSuggestionClick(suggestion)
    inputRef.current?.focus()
  }

  return (
    <div className="zk-docked">
      {/* Header */}
      <div className="zk-docked__header">
        <span className="zk-docked__title">{brandName}</span>
        <div className="zk-docked__controls">
          <button
            className="zk-header-btn"
            onClick={onUndock}
            aria-label="Undock panel"
            type="button"
            title="Undock"
          >
            {/* Panel-center / undock icon */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <rect x="7" y="4" width="10" height="16" />
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
      <div className="zk-docked__messages">
        <div className="zk-docked__messages-inner">
          {messages.map(message => (
            <div key={message.id} className={`zk-message zk-message-${message.role}`}>
              <div className="zk-message-content">
                {message.content}
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
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <form className="zk-docked__input" onSubmit={onSubmit}>
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
