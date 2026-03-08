import React, { useState, useEffect, useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { styles } from './styles'
import { CollapsedBar } from './CollapsedBar'
import { ExpandedPanel } from './ExpandedPanel'
import { DockedPanel } from './DockedPanel'
import { bootstrap, destroy, getDockPanel } from '../layout/LayoutManager'
import { enterDock, exitDock, DOCK_MIN_WIDTH } from '../layout/DockStateManager'

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

export function Widget({ siteId, apiUrl }: WidgetProps) {
  const [mode, setMode] = useState<WidgetMode>('bottom-minimized')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [config, setConfig] = useState<WidgetConfig | null>(null)
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [dockPortalTarget, setDockPortalTarget] = useState<HTMLElement | null>(null)
  const hasAnimated = useRef(false)

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

  // Bootstrap layout wrapper once (synchronous, before paint)
  useLayoutEffect(() => {
    bootstrap()
    setDockPortalTarget(getDockPanel())
    return () => {
      destroy()
    }
  }, [])

  // Dock state: enter/exit via CSS class toggle only (no DOM mutation)
  useEffect(() => {
    if (mode === 'right-docked') {
      enterDock(() => setMode('bottom-expanded'))
    } else {
      exitDock()
    }
  }, [mode])

  // Query API — SSE streaming
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    if (mode === 'bottom-minimized') setMode('bottom-expanded')

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    }

    const assistantId = (Date.now() + 1).toString()

    setMessages(prev => {
      const filtered = prev.filter(m => !m.isError)
      return [...filtered, userMessage]
    })
    setInput('')
    setIsLoading(true)

    const payload = {
      site_id: siteId,
      question: userMessage.content,
      session_id: sessionId,
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
              streamingContent += event.data
              if (!addedMessage) {
                addedMessage = true
                setMessages(prev => [...prev, {
                  id: assistantId,
                  role: 'assistant',
                  content: streamingContent,
                }])
              } else {
                setMessages(prev =>
                  prev.map(m => m.id === assistantId ? { ...m, content: streamingContent } : m)
                )
              }
            } else if (event.type === 'done') {
              if (event.session_id) setSessionId(event.session_id)
              setMessages(prev =>
                prev.map(m => m.id === assistantId ? {
                  ...m,
                  content: event.answer,
                  suggestions: event.suggestions,
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
      console.error('[Zunkiree] Stream error:', error)
      setMessages(prev => [...prev, {
        id: (Date.now() + 2).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        isError: true,
      }])
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
          apiUrl={apiUrl}
          siteId={siteId}
        />
      )}

      {mode === 'right-docked' && dockPortalTarget && createPortal(
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
          apiUrl={apiUrl}
          siteId={siteId}
        />,
        dockPortalTarget,
      )}
    </>
  )
}
