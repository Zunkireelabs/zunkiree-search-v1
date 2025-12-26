import React, { useState, useEffect, useRef } from 'react'
import { styles } from './styles'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: string[]
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
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Fetch widget config
  useEffect(() => {
    fetch(`${apiUrl}/api/v1/widget/config/${siteId}`)
      .then(res => res.json())
      .then(data => {
        setConfig(data)
        if (data.welcome_message) {
          setMessages([{
            id: 'welcome',
            role: 'assistant',
            content: data.welcome_message,
          }])
        }
      })
      .catch(err => {
        console.error('Failed to load widget config:', err)
        setConfig({
          brand_name: 'Assistant',
          primary_color: '#2563eb',
          placeholder_text: 'Ask a question...',
          welcome_message: 'Hi! How can I help you today?',
        })
        setMessages([{
          id: 'welcome',
          role: 'assistant',
          content: 'Hi! How can I help you today?',
        }])
      })
  }, [apiUrl, siteId])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await fetch(`${apiUrl}/api/v1/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: siteId,
          question: userMessage.content,
        }),
      })

      const data = await response.json()

      if (!response.ok) {
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
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again later.',
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSuggestionClick = (suggestion: string) => {
    setInput(suggestion)
  }

  const primaryColor = config?.primary_color || '#2563eb'

  return (
    <>
      <style>{styles(primaryColor)}</style>

      {/* Trigger Button */}
      {!isOpen && (
        <button
          className="zk-trigger"
          onClick={() => setIsOpen(true)}
          aria-label="Open chat"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      )}

      {/* Chat Container */}
      {isOpen && (
        <div className="zk-container">
          {/* Header */}
          <div className="zk-header">
            <span className="zk-header-title">{config?.brand_name || 'Assistant'}</span>
            <button
              className="zk-close"
              onClick={() => setIsOpen(false)}
              aria-label="Close chat"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Messages */}
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

          {/* Input */}
          <form className="zk-input-area" onSubmit={handleSubmit}>
            <input
              type="text"
              className="zk-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={config?.placeholder_text || 'Ask a question...'}
              disabled={isLoading}
            />
            <button
              type="submit"
              className="zk-send"
              disabled={!input.trim() || isLoading}
              aria-label="Send message"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </form>
        </div>
      )}
    </>
  )
}
