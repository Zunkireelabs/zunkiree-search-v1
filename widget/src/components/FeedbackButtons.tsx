import React, { useState } from 'react'

interface FeedbackButtonsProps {
  queryLogId: string
  apiUrl: string
}

export const FeedbackButtons = React.memo(function FeedbackButtons({ queryLogId, apiUrl }: FeedbackButtonsProps) {
  const [voted, setVoted] = useState<1 | -1 | null>(null)

  const submitFeedback = async (vote: 1 | -1) => {
    setVoted(vote)
    try {
      await fetch(`${apiUrl}/api/v1/query/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_log_id: queryLogId, vote }),
      })
    } catch { /* fire-and-forget */ }
  }

  if (voted) {
    return <span className="zk-feedback-thanks">{voted === 1 ? 'Glad it helped!' : 'Thanks for the feedback'}</span>
  }

  return (
    <div className="zk-feedback">
      <button type="button" className="zk-feedback-btn" onClick={() => submitFeedback(1)} aria-label="Helpful" title="Helpful">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z" />
          <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
        </svg>
      </button>
      <button type="button" className="zk-feedback-btn" onClick={() => submitFeedback(-1)} aria-label="Not helpful" title="Not helpful">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z" />
          <path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3" />
        </svg>
      </button>
    </div>
  )
})
