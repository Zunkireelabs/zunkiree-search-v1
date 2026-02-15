import React, { useState, useEffect, useRef } from 'react'
import { styles } from './styles'
import { CollapsedBar } from './CollapsedBar'
import { ExpandedPanel } from './ExpandedPanel'
import { DockedPanel } from './DockedPanel'

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
  quick_actions?: string[]
}

interface WidgetProps {
  siteId: string
  apiUrl: string
}

type WidgetMode = 'minimized' | 'expanded' | 'docked'

export function Widget({ siteId, apiUrl }: WidgetProps) {
  const [mode, setMode] = useState<WidgetMode>('minimized')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const hasAnimated = useRef(false)

  // Fetch widget config — UNCHANGED
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

  // Body layout shift for docked mode
  useEffect(() => {
    const root = document.getElementById('zunkiree-widget-root')
    if (mode === 'docked') {
      document.body.classList.add('zk-docked-active')
      root?.classList.add('zk-docked-mode')
    } else {
      document.body.classList.remove('zk-docked-active')
      root?.classList.remove('zk-docked-mode')
    }
    return () => {
      document.body.classList.remove('zk-docked-active')
      root?.classList.remove('zk-docked-mode')
    }
  }, [mode])

  // Query API — UNCHANGED
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    if (mode === 'minimized') setMode('expanded')

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    }

    setMessages(prev => {
      const filtered = prev.filter(m => !m.isError)
      return [...filtered, userMessage]
    })
    setInput('')
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
    if (mode === 'minimized') setMode('expanded')
  }

  const handleOpen = () => {
    hasAnimated.current = true
    setMode('expanded')
  }

  const handleClose = () => {
    hasAnimated.current = true
    setMode('minimized')
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
    <>
      <style>{styles(primaryColor)}</style>

      {mode === 'minimized' && (
        <CollapsedBar
          brandName={brandName}
          suggestions={getSuggestions()}
          animate={!hasAnimated.current}
          onClick={handleOpen}
          onSuggestionClick={handleSuggestionClick}
        />
      )}

      {mode === 'expanded' && (
        <ExpandedPanel
          brandName={brandName}
          messages={messages}
          suggestions={getSuggestions()}
          input={input}
          isLoading={isLoading}
          onInputChange={setInput}
          onSubmit={handleSubmit}
          onSuggestionClick={handleSuggestionClick}
          onClose={handleClose}
          onDock={() => setMode('docked')}
          placeholder={placeholder}
        />
      )}

      {mode === 'docked' && (
        <DockedPanel
          brandName={brandName}
          messages={messages}
          suggestions={getSuggestions()}
          input={input}
          isLoading={isLoading}
          onInputChange={setInput}
          onSubmit={handleSubmit}
          onSuggestionClick={handleSuggestionClick}
          onMinimize={() => setMode('minimized')}
          onUndock={() => setMode('expanded')}
          placeholder={placeholder}
        />
      )}
    </>
  )
}
