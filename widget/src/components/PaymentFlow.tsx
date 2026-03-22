import { useState, useRef, useEffect } from 'react'

interface Props {
  orderId: string
  total: number
  currency: string
  apiUrl: string
  onComplete: (gateway: string) => void
  onFailed: () => void
}

const POLL_INTERVAL = 3000
const PAYMENT_TIMEOUT = 10 * 60 * 1000

export function PaymentFlow({ orderId, total, currency, apiUrl, onComplete, onFailed }: Props) {
  const [step, setStep] = useState<'select' | 'waiting' | 'done' | 'failed'>('select')
  const [selected, setSelected] = useState<'esewa' | 'khalti' | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const pollRef = useRef<number | null>(null)
  const popupRef = useRef<Window | null>(null)
  const timeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
    }
  }, [])

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    if (timeoutRef.current) { clearTimeout(timeoutRef.current); timeoutRef.current = null }
  }

  const startPolling = (paymentId: string) => {
    const poll = async () => {
      if (popupRef.current && popupRef.current.closed) {
        stopPolling()
        try {
          const res = await fetch(`${apiUrl}/api/v1/payments/${paymentId}/status`)
          const data = await res.json()
          if (data.status === 'completed') {
            setStep('done')
            onComplete(data.gateway)
          } else {
            setStep('failed')
            onFailed()
          }
        } catch {
          setStep('failed')
          onFailed()
        }
        return
      }
      try {
        const res = await fetch(`${apiUrl}/api/v1/payments/${paymentId}/status`)
        const data = await res.json()
        if (data.status === 'completed') {
          stopPolling()
          if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
          setStep('done')
          onComplete(data.gateway)
        } else if (data.status === 'failed') {
          stopPolling()
          if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
          setStep('failed')
          onFailed()
        }
      } catch { /* continue polling */ }
    }

    pollRef.current = window.setInterval(poll, POLL_INTERVAL)
    timeoutRef.current = window.setTimeout(() => {
      stopPolling()
      if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
      setStep('failed')
      onFailed()
    }, PAYMENT_TIMEOUT)
  }

  const handlePay = async (gateway: 'esewa' | 'khalti') => {
    setSelected(gateway)
    setError('')

    const popup = window.open('about:blank', 'zkPayment', 'width=500,height=700,scrollbars=yes')
    if (!popup) {
      setError('Popup was blocked. Please allow popups and try again.')
      return
    }
    popupRef.current = popup

    setIsLoading(true)
    try {
      const res = await fetch(`${apiUrl}/api/v1/payments/initiate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: orderId, gateway, site_id: '' }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Payment initiation failed')

      if (gateway === 'esewa' && data.formData && data.paymentUrl) {
        const doc = popup.document
        doc.open()
        doc.write(`<html><body>
          <p style="text-align:center;margin-top:40px;font-family:sans-serif">Redirecting to eSewa...</p>
          <form id="f" method="POST" action="${data.paymentUrl}">
            ${Object.entries(data.formData).map(([k, v]) =>
              `<input type="hidden" name="${k}" value="${String(v)}" />`
            ).join('')}
          </form>
          <script>document.getElementById('f').submit();</script>
        </body></html>`)
        doc.close()
      } else if (gateway === 'khalti' && data.paymentUrl) {
        popup.location.href = data.paymentUrl
      }

      setStep('waiting')
      startPolling(data.paymentId)
    } catch (err: any) {
      if (popup && !popup.closed) popup.close()
      setError(err.message || 'Payment failed')
    } finally {
      setIsLoading(false)
    }
  }

  const sym = currency === 'NPR' ? 'Rs ' : currency === 'INR' ? '₹' : currency + ' '

  if (step === 'done') {
    return (
      <div style={{ textAlign: 'center', padding: '12px 0' }}>
        <div style={{ fontSize: '24px', marginBottom: '4px' }}>✓</div>
        <div style={{ fontWeight: 600, color: '#16a34a' }}>Payment successful!</div>
        <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
          Paid via {selected === 'esewa' ? 'eSewa' : 'Khalti'}
        </div>
      </div>
    )
  }

  if (step === 'failed') {
    return (
      <div style={{ textAlign: 'center', padding: '12px 0' }}>
        <div style={{ fontSize: '24px', marginBottom: '4px' }}>✗</div>
        <div style={{ fontWeight: 600, color: '#dc2626' }}>Payment failed</div>
        <button
          type="button"
          onClick={() => { setStep('select'); setError('') }}
          style={{
            marginTop: '8px', padding: '6px 16px', border: '1px solid #d1d5db',
            borderRadius: '6px', background: '#fff', cursor: 'pointer', fontSize: '13px',
          }}
        >
          Try again
        </button>
      </div>
    )
  }

  if (step === 'waiting') {
    return (
      <div style={{ textAlign: 'center', padding: '12px 0' }}>
        <div style={{ fontSize: '14px', fontWeight: 500 }}>
          Completing payment via {selected === 'esewa' ? 'eSewa' : 'Khalti'}...
        </div>
        <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
          Please complete payment in the popup window
        </div>
        <button
          type="button"
          onClick={() => { stopPolling(); if (popupRef.current && !popupRef.current.closed) popupRef.current.close(); setStep('select') }}
          style={{
            marginTop: '8px', padding: '4px 12px', border: 'none',
            background: 'transparent', color: '#6b7280', cursor: 'pointer', fontSize: '12px',
            textDecoration: 'underline',
          }}
        >
          Cancel
        </button>
      </div>
    )
  }

  // step === 'select'
  return (
    <div style={{ padding: '8px 0' }}>
      <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>
        Pay {sym}{total.toLocaleString()}
      </div>

      {error && (
        <div style={{ fontSize: '12px', color: '#dc2626', marginBottom: '6px' }}>{error}</div>
      )}

      <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
        <button
          type="button"
          onClick={() => handlePay('esewa')}
          disabled={isLoading}
          style={{
            flex: 1, padding: '10px 8px', border: '1.5px solid #60BB46',
            borderRadius: '8px', background: '#f0fdf4', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
            fontSize: '13px', fontWeight: 600, color: '#15803d',
            opacity: isLoading ? 0.6 : 1,
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <rect width="24" height="24" rx="4" fill="#60BB46"/>
            <text x="12" y="16" textAnchor="middle" fill="white" fontSize="10" fontWeight="700" fontFamily="sans-serif">eS</text>
          </svg>
          eSewa
        </button>

        <button
          type="button"
          onClick={() => handlePay('khalti')}
          disabled={isLoading}
          style={{
            flex: 1, padding: '10px 8px', border: '1.5px solid #5C2D91',
            borderRadius: '8px', background: '#faf5ff', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
            fontSize: '13px', fontWeight: 600, color: '#5C2D91',
            opacity: isLoading ? 0.6 : 1,
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <rect width="24" height="24" rx="4" fill="#5C2D91"/>
            <text x="12" y="16" textAnchor="middle" fill="white" fontSize="10" fontWeight="700" fontFamily="sans-serif">K</text>
          </svg>
          Khalti
        </button>
      </div>

      <div style={{ fontSize: '11px', color: '#9ca3af', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        Secure payment
      </div>
    </div>
  )
}
