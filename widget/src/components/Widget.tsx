import React, { useState, useEffect, useLayoutEffect, useRef } from 'react'
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

type WidgetMode = 'bottom-minimized' | 'bottom-expanded' | 'right-docked'

const DOCK_MIN_WIDTH = 1200
const WIDGET_ROOT_ID = 'zunkiree-widget-root'

export function Widget({ siteId, apiUrl }: WidgetProps) {
  const [mode, setMode] = useState<WidgetMode>('bottom-minimized')
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

  // ── Dock mode: toggle class on widget root only ──
  // Pure overlay — never touches host DOM/body/html
  useLayoutEffect(() => {
    const root = document.getElementById(WIDGET_ROOT_ID)
    if (mode === 'right-docked') {
      root?.classList.add('zk-docked-mode')
    } else {
      root?.classList.remove('zk-docked-mode')
    }
    return () => {
      root?.classList.remove('zk-docked-mode')
    }
  }, [mode])

  // ── Exit dock if viewport shrinks below threshold ──
  useEffect(() => {
    function handleResize() {
      if (mode === 'right-docked' && window.innerWidth < DOCK_MIN_WIDTH) {
        setMode('bottom-expanded')
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [mode])

  // Query API — UNCHANGED
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    if (mode === 'bottom-minimized') setMode('bottom-expanded')

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
    <>
      <style>{styles(primaryColor)}</style>

      {mode === 'bottom-minimized' && (
        <CollapsedBar
          brandName={brandName}
          suggestions={getSuggestions()}
          animate={!hasAnimated.current}
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
        />
      )}

      {mode === 'right-docked' && (
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
        />
      )}
    </>
  )
}
