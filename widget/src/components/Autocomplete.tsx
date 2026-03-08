import { useState, useEffect, useRef, useCallback } from 'react'

interface AutocompleteProps {
  apiUrl: string
  siteId: string
  query: string
  onSelect: (suggestion: string) => void
  visible: boolean
}

export function Autocomplete({ apiUrl, siteId, query, onSelect, visible }: AutocompleteProps) {
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()
  const abortRef = useRef<AbortController>()

  const fetchSuggestions = useCallback(async (q: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch(
        `${apiUrl}/api/v1/query/autocomplete?site_id=${encodeURIComponent(siteId)}&q=${encodeURIComponent(q)}`,
        { signal: controller.signal }
      )
      if (!res.ok) return
      const data = await res.json()
      if (!controller.signal.aborted) {
        setSuggestions(data.suggestions || [])
        setActiveIndex(-1)
      }
    } catch {
      // aborted or network error — ignore
    }
  }, [apiUrl, siteId])

  useEffect(() => {
    if (!visible || query.trim().length < 2) {
      setSuggestions([])
      return
    }

    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchSuggestions(query.trim()), 250)

    return () => clearTimeout(debounceRef.current)
  }, [query, visible, fetchSuggestions])

  // Clean up on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      clearTimeout(debounceRef.current)
    }
  }, [])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!suggestions.length) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex(prev => (prev + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(prev => (prev <= 0 ? suggestions.length - 1 : prev - 1))
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault()
      e.stopPropagation()
      onSelect(suggestions[activeIndex])
      setSuggestions([])
    } else if (e.key === 'Escape') {
      setSuggestions([])
    }
  }, [suggestions, activeIndex, onSelect])

  useEffect(() => {
    if (suggestions.length > 0) {
      document.addEventListener('keydown', handleKeyDown, true)
      return () => document.removeEventListener('keydown', handleKeyDown, true)
    }
  }, [suggestions, handleKeyDown])

  if (!visible || suggestions.length === 0) return null

  return (
    <div className="zk-autocomplete">
      {suggestions.map((suggestion, idx) => (
        <button
          key={idx}
          className={`zk-autocomplete__item ${idx === activeIndex ? 'zk-autocomplete__item--active' : ''}`}
          onMouseDown={(e) => {
            e.preventDefault() // Prevent input blur
            onSelect(suggestion)
            setSuggestions([])
          }}
          onMouseEnter={() => setActiveIndex(idx)}
          type="button"
        >
          <svg className="zk-autocomplete__icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span className="zk-autocomplete__text">{suggestion}</span>
        </button>
      ))}
    </div>
  )
}
