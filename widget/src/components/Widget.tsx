import React, { useState, useEffect, useRef } from 'react'
import { styles } from './styles'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
  isError?: boolean
}

interface WidgetConfig {
  brand_name: string
  primary_color: string
  placeholder_text: string
  welcome_message: string | null
}

interface WidgetProps {
  siteId: string
  apiUrl: string
}

export function Widget({ siteId, apiUrl }: WidgetProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

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

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input when expanded
  useEffect(() => {
    if (isExpanded && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isExpanded])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    // Expand if not already
    if (!isExpanded) {
      setIsExpanded(true)
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    }

    // Clear previous error messages before new query
    setMessages(prev => {
      console.log('[Zunkiree] Before filtering:', prev)
      const filtered = prev.filter(m => !m.isError)
      console.log('[Zunkiree] After filtering:', filtered)
      const newMessages = [...filtered, userMessage]
      console.log('[Zunkiree] Setting new messages:', newMessages)
      return newMessages
    })
    setInput('')
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
    }
    setIsLoading(true)

    const payload = {
      site_id: siteId,
      question: userMessage.content,
    }
    console.log('[Zunkiree] Request payload:', payload)

    try {
      const response = await fetch(`${apiUrl}/api/v1/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      const data = await response.json()

      if (!response.ok) {
        console.error('[Zunkiree] Error response:', response.status, data)
        throw new Error(data.detail?.message || 'Failed to get answer')
      }

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.answer,
        suggestions: data.suggestions,
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error('[Zunkiree] Fetch error:', error)
      console.log('[Zunkiree] Adding error message')
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        isError: true,
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion)
    inputRef.current?.focus()
    setTimeout(() => {
      if (inputRef.current) {
        adjustTextareaHeight(inputRef.current)
      }
    }, 0)
  }

  const handleInputFocus = () => {
    if (messages.length > 0) {
      setIsExpanded(true)
    }
  }

  const handleClose = () => {
    setIsExpanded(false)
  }

  const adjustTextareaHeight = (textarea: HTMLTextAreaElement) => {
    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto'
    const scrollHeight = textarea.scrollHeight
    // Max height is 216px (9 lines × 24px)
    textarea.style.height = `${Math.min(scrollHeight, 216)}px`
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    adjustTextareaHeight(e.target)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !isLoading) {
        handleSubmit(e as unknown as React.FormEvent)
      }
    }
  }

  // Get last assistant message for preview bar
  const getLastAssistantMessage = (): string => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') {
        return messages[i].content
      }
    }
    return ''
  }

  const handleExpand = () => {
    setIsExpanded(true)
  }

  const primaryColor = config?.primary_color || '#2563eb'

  return (
    <>
      <style>{styles(primaryColor)}</style>

      <div className={`zk-widget ${isExpanded ? 'zk-expanded' : ''}`}>
        {/* Unified Chat Panel - Expands/collapses smoothly */}
        {messages.length > 0 && (
          <div className={`zk-chat-panel ${isExpanded ? 'zk-chat-expanded' : 'zk-chat-collapsed'}`}>
            {/* Header - Always visible */}
            <div className="zk-chat-header" onClick={isExpanded ? handleClose : handleExpand}>
              {isExpanded ? (
                <>
                  <span className="zk-panel-title">{config?.brand_name || 'Assistant'}</span>
                  <button
                    className="zk-toggle-btn"
                    onClick={handleClose}
                    aria-label="Minimize chat"
                    type="button"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </button>
                </>
              ) : (
                <>
                  <div className="zk-preview-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <span className="zk-preview-text">{getLastAssistantMessage()}</span>
                  <button
                    className="zk-toggle-btn"
                    onClick={handleExpand}
                    aria-label="Expand chat"
                    type="button"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="18 15 12 9 6 15" />
                    </svg>
                  </button>
                </>
              )}
            </div>

            {/* Messages - Only visible when expanded */}
            <div className="zk-messages-wrapper">
              <div className="zk-messages">
                {messages.map(message => (
                  <div key={message.id} className={`zk-message zk-message-${message.role}`}>
                    <div className="zk-message-content">
                      {message.content}
                    </div>
                    {message.suggestions && message.suggestions.length > 0 && (
                      <div className="zk-suggestions">
                        {message.suggestions.map((suggestion, idx) => (
                          <button
                            key={idx}
                            className="zk-suggestion"
                            onClick={() => handleSuggestionClick(suggestion)}
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
          </div>
        )}

        {/* Bottom Input Bar - Always visible */}
        <form className="zk-input-bar" onSubmit={handleSubmit}>
          <div className="zk-input-container">
            <div className="zk-input-inner">
              <textarea
                ref={inputRef}
                className="zk-input"
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                onFocus={handleInputFocus}
                placeholder={config?.placeholder_text || 'Ask a question...'}
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
