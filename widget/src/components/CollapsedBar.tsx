import { useEffect, useState, useRef } from 'react'

interface CollapsedBarProps {
  brandName: string
  suggestions: string[]
  animate: boolean
  hasMessages: boolean
  minimized?: boolean
  scrollTransition?: boolean
  onClick: () => void
  onMinimize: () => void
  onSuggestionClick: (suggestion: string) => void
}

const SCROLL_THRESHOLD = 200

export function CollapsedBar({
  brandName,
  suggestions,
  animate,
  hasMessages,
  minimized,
  scrollTransition,
  onClick,
  onMinimize,
  onSuggestionClick,
}: CollapsedBarProps) {
  const [visible, setVisible] = useState(!animate)
  const [scrolledDown, setScrolledDown] = useState(false)
  const rafRef = useRef(0)

  useEffect(() => {
    if (animate) {
      requestAnimationFrame(() => setVisible(true))
    }
  }, [animate])

  // Scroll listener for card→pill transition (only on initial load, disabled after interaction)
  useEffect(() => {
    if (minimized || !scrollTransition) {
      setScrolledDown(false)
      return
    }
    const onScroll = () => {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(() => {
        setScrolledDown(window.scrollY > SCROLL_THRESHOLD)
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll() // check initial position
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(rafRef.current)
    }
  }, [minimized, scrollTransition])

  const showPill = minimized || scrolledDown

  return (
    <>
      {/* FAB — pill button, bottom-right (mobile always, desktop on scroll/minimize) */}
      <button
        className={`zk-fab ${showPill ? 'zk-fab--desktop' : ''} ${visible ? 'zk-fab--visible' : ''}`}
        onClick={onClick}
        aria-label={`Ask ${brandName} a question`}
        type="button"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M10 2l1.5 4.5L16 8l-4.5 1.5L10 14l-1.5-4.5L4 8l4.5-1.5L10 2z" />
          <path d="M18 12l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3z" />
          <path d="M6 16l.75 2.25L9 19l-2.25.75L6 22l-.75-2.25L3 19l2.25-.75L6 16z" opacity="0.7" />
        </svg>
        <span className="zk-fab__label">Ask {brandName}</span>
      </button>

      {/* Desktop full bar — always rendered, hidden via CSS when pill is showing */}
      <div className={`zk-collapsed-bar ${visible ? 'zk-collapsed-bar--visible' : ''} ${showPill ? 'zk-collapsed-bar--hidden' : ''}`}>
        <div className="zk-collapsed-bar__card">
          {/* Minimize button */}
          <button
            className="zk-collapsed-bar__minimize"
            onClick={(e) => {
              e.stopPropagation()
              onMinimize()
            }}
            aria-label="Minimize"
            type="button"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>

          {/* Input area - clicking opens expanded panel */}
          <div className="zk-collapsed-bar__input-wrap" onClick={onClick}>
            <div className="zk-input-container">
              <div className="zk-input-inner zk-collapsed-bar__input-inner">
                <svg
                  className="zk-collapsed-bar__icon"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M10 2l1.5 4.5L16 8l-4.5 1.5L10 14l-1.5-4.5L4 8l4.5-1.5L10 2z" />
                  <path d="M18 12l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3z" />
                  <path d="M6 16l.75 2.25L9 19l-2.25.75L6 22l-.75-2.25L3 19l2.25-.75L6 16z" opacity="0.7" />
                </svg>
                <span className="zk-collapsed-bar__placeholder">
                  Ask {brandName} a question&hellip;
                </span>
                <div className="zk-collapsed-bar__send">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            </div>
          </div>

          {/* Suggestion chips — only before conversation starts */}
          {!hasMessages && suggestions.length > 0 && (
            <div className="zk-collapsed-bar__chips">
              {suggestions.slice(0, 3).map((suggestion, idx) => (
                <button
                  key={idx}
                  className="zk-chip zk-chip--card"
                  onClick={(e) => {
                    e.stopPropagation()
                    onSuggestionClick(suggestion)
                  }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
