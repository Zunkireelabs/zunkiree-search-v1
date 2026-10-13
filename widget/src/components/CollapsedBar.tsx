import { useEffect, useState, useRef } from 'react'

interface CollapsedBarProps {
  brandName: string
  launcherName: string
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
  launcherName,
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
        aria-label={`Talk to ${launcherName}`}
        type="button"
      >
        <span className="zk-orb zk-orb--lg" aria-hidden="true" />
        <span className="zk-fab__label">Talk to {launcherName}</span>
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
                <span className="zk-orb zk-orb--md" aria-hidden="true" />
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
