import { useEffect, useState } from 'react'

interface CollapsedBarProps {
  brandName: string
  suggestions: string[]
  animate: boolean
  onClick: () => void
  onSuggestionClick: (suggestion: string) => void
}

export function CollapsedBar({
  brandName,
  suggestions,
  animate,
  onClick,
  onSuggestionClick,
}: CollapsedBarProps) {
  const [visible, setVisible] = useState(!animate)

  useEffect(() => {
    if (animate) {
      requestAnimationFrame(() => setVisible(true))
    }
  }, [animate])

  return (
    <div className={`zk-collapsed-bar ${visible ? 'zk-collapsed-bar--visible' : ''}`}>
      <div className="zk-collapsed-bar__border" onClick={onClick}>
        <div className="zk-collapsed-bar__inner">
          <svg
            className="zk-collapsed-bar__icon"
            width="20"
            height="20"
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
        </div>
      </div>
      {suggestions.length > 0 && (
        <div className="zk-collapsed-bar__chips">
          {suggestions.slice(0, 2).map((suggestion, idx) => (
            <button
              key={idx}
              className="zk-chip"
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
  )
}
