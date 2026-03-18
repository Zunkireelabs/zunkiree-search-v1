import { useState, useRef, useEffect } from 'react'
import { ShippingForm, type ShippingInfo } from './ShippingForm'
import { PaymentSelector } from './PaymentSelector'
import { OrderConfirmation } from './OrderConfirmation'

interface CartItem {
  productName: string
  variationLabel?: string
  quantity: number
  unitPrice: number
  lineTotal: number
}

interface Props {
  cartId: number
  items: CartItem[]
  subtotal: number
  apiUrl: string
  siteId: string
  sessionId: string
  onContinueShopping?: () => void
}

type Step = 'shipping' | 'payment' | 'awaiting_payment' | 'confirmation' | 'failed'

const POLL_INTERVAL = 3000
const PAYMENT_TIMEOUT = 10 * 60 * 1000 // 10 minutes

export function AgentCheckout({ cartId, items, subtotal, apiUrl, siteId, sessionId, onContinueShopping }: Props) {
  const [step, setStep] = useState<Step>('shipping')
  const [isLoading, setIsLoading] = useState(false)
  const [orderId, setOrderId] = useState('')
  const [error, setError] = useState('')
  const [gateway, setGateway] = useState<'esewa' | 'khalti'>('esewa')
  const pollRef = useRef<number | null>(null)
  const popupRef = useRef<Window | null>(null)
  const timeoutRef = useRef<number | null>(null)

  // Cleanup on unmount
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

  const startPolling = (pId: string) => {
    // Store paymentId for polling (since state may not be updated yet)
    const pollPaymentId = pId

    const poll = async () => {
      // Check if popup was closed
      if (popupRef.current && popupRef.current.closed) {
        stopPolling()
        // Final status check
        try {
          const res = await fetch(`${apiUrl}/v1/sites/${siteId}/payments/${pollPaymentId}/status`)
          const data = await res.json()
          if (data.status === 'completed') {
            setStep('confirmation')
          } else {
            setStep('failed')
          }
        } catch {
          setStep('failed')
        }
        return
      }

      // Regular status check
      try {
        const res = await fetch(`${apiUrl}/v1/sites/${siteId}/payments/${pollPaymentId}/status`)
        const data = await res.json()
        if (data.status === 'completed') {
          stopPolling()
          if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
          setStep('confirmation')
        } else if (data.status === 'failed') {
          stopPolling()
          if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
          setStep('failed')
        }
      } catch {
        // Continue polling on network errors
      }
    }

    pollRef.current = window.setInterval(poll, POLL_INTERVAL)

    // Safety timeout
    timeoutRef.current = window.setTimeout(() => {
      stopPolling()
      if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
      setStep('failed')
    }, PAYMENT_TIMEOUT)
  }

  const handleShippingSubmit = async (info: ShippingInfo) => {
    setIsLoading(true)
    setError('')
    try {
      const res = await fetch(`${apiUrl}/v1/sites/${siteId}/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionId },
        body: JSON.stringify({ sessionId, cartId, shippingInfo: info }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to create order')
      setOrderId(data.order.id.toString())
      setStep('payment')
    } catch (err: any) {
      setError(err.message || 'Something went wrong')
    } finally {
      setIsLoading(false)
    }
  }

  const handlePaymentSelect = async (selectedGateway: 'esewa' | 'khalti') => {
    setGateway(selectedGateway)
    setError('')

    // Open popup immediately (synchronous, in click handler) to avoid popup blockers
    const popup = window.open('about:blank', 'zkPayment', 'width=500,height=700,scrollbars=yes')
    if (!popup) {
      setError('Popup was blocked. Please allow popups for this site and try again.')
      return
    }
    popupRef.current = popup

    setIsLoading(true)
    try {
      const res = await fetch(`${apiUrl}/v1/sites/${siteId}/payments/initiate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionId },
        body: JSON.stringify({ orderId, gateway: selectedGateway, source: 'widget' }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Failed to initiate payment')

      if (selectedGateway === 'esewa' && data.formData && data.paymentUrl) {
        // eSewa: write a form into the popup and submit it
        const doc = popup.document
        doc.open()
        doc.write(`
          <html><body>
            <p style="text-align:center;margin-top:40px;font-family:sans-serif">Redirecting to eSewa...</p>
            <form id="esewaForm" method="POST" action="${data.paymentUrl}">
              ${Object.entries(data.formData).map(([k, v]) =>
                `<input type="hidden" name="${k}" value="${String(v)}" />`
              ).join('')}
            </form>
            <script>document.getElementById('esewaForm').submit();</script>
          </body></html>
        `)
        doc.close()
      } else if (selectedGateway === 'khalti' && data.paymentUrl) {
        // Khalti: navigate popup to payment URL
        popup.location.href = data.paymentUrl
      }

      setStep('awaiting_payment')
      startPolling(data.paymentId.toString())
    } catch (err: any) {
      if (popup && !popup.closed) popup.close()
      setError(err.message || 'Payment initiation failed')
    } finally {
      setIsLoading(false)
    }
  }

  const handleRetryPayment = () => {
    setStep('payment')
    setError('')
  }

  const handleRetryPopup = () => {
    // Re-open popup if it was closed
    if (popupRef.current && popupRef.current.closed) {
      // Need to re-initiate payment
      handlePaymentSelect(gateway)
    }
  }

  const handleCancelPayment = () => {
    stopPolling()
    if (popupRef.current && !popupRef.current.closed) popupRef.current.close()
    setStep('payment')
  }

  const getStepClass = (s: string) => {
    const stepOrder = ['shipping', 'payment', 'awaiting_payment', 'confirmation']
    const currentIdx = stepOrder.indexOf(step === 'failed' ? 'payment' : step)
    const thisIdx = stepOrder.indexOf(s)
    if (thisIdx < currentIdx) return 'zk-checkout__step--done'
    if (thisIdx === currentIdx) return 'zk-checkout__step--active'
    return ''
  }

  return (
    <div className="zk-checkout">
      {/* Progress indicator */}
      <div className="zk-checkout__steps">
        <div className={`zk-checkout__step ${getStepClass('shipping')}`}>
          <span className="zk-checkout__step-num">{getStepClass('shipping') === 'zk-checkout__step--done' ? '\u2713' : '1'}</span>
          <span>Shipping</span>
        </div>
        <div className="zk-checkout__step-line" />
        <div className={`zk-checkout__step ${getStepClass('payment') || getStepClass('awaiting_payment')}`}>
          <span className="zk-checkout__step-num">{getStepClass('payment') === 'zk-checkout__step--done' || getStepClass('awaiting_payment') === 'zk-checkout__step--done' ? '\u2713' : '2'}</span>
          <span>Payment</span>
        </div>
        <div className="zk-checkout__step-line" />
        <div className={`zk-checkout__step ${getStepClass('confirmation')}`}>
          <span className="zk-checkout__step-num">3</span>
          <span>Done</span>
        </div>
      </div>

      {/* Order summary */}
      {step !== 'confirmation' && step !== 'failed' && items.length > 0 && (
        <div className="zk-checkout__summary">
          {items.map((item, i) => (
            <div key={i} className="zk-checkout__item">
              <span>{item.productName}{item.variationLabel ? ` (${item.variationLabel})` : ''} x{item.quantity}</span>
              <span>Rs {item.lineTotal.toLocaleString()}</span>
            </div>
          ))}
          <div className="zk-checkout__total">
            <strong>Total</strong>
            <strong>Rs {subtotal.toLocaleString()}</strong>
          </div>
        </div>
      )}

      {error && <div className="zk-checkout__error">{error}</div>}

      {step === 'shipping' && (
        <ShippingForm onSubmit={handleShippingSubmit} isLoading={isLoading} />
      )}

      {step === 'payment' && (
        <PaymentSelector
          orderId={orderId}
          total={subtotal}
          onSelect={handlePaymentSelect}
          isLoading={isLoading}
        />
      )}

      {step === 'awaiting_payment' && (
        <div className="zk-payment-waiting">
          <div className="zk-payment-waiting__spinner" />
          <div className="zk-payment-waiting__text">
            Completing payment via {gateway === 'esewa' ? 'eSewa' : 'Khalti'}...
          </div>
          <div className="zk-payment-waiting__sub">
            Please complete the payment in the popup window
          </div>
          <button type="button" className="zk-payment-waiting__retry" onClick={handleRetryPopup}>
            Payment window not opening? Click here to retry
          </button>
          <button type="button" className="zk-payment-waiting__cancel" onClick={handleCancelPayment}>
            Cancel
          </button>
        </div>
      )}

      {step === 'confirmation' && (
        <OrderConfirmation
          orderId={orderId}
          total={subtotal}
          gateway={gateway}
          onContinueShopping={onContinueShopping}
        />
      )}

      {step === 'failed' && (
        <div className="zk-payment-failed">
          <div className="zk-payment-failed__icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M15 9l-6 6M9 9l6 6" />
            </svg>
          </div>
          <div className="zk-payment-failed__title">Payment Failed</div>
          <div className="zk-payment-failed__msg">
            The payment could not be completed. Please try again.
          </div>
          <button type="button" className="zk-payment-failed__retry" onClick={handleRetryPayment}>
            Try Again
          </button>
        </div>
      )}
    </div>
  )
}
