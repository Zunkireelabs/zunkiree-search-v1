import { useState } from 'react'

interface Props {
  orderId: string
  total: number
  onSelect: (gateway: 'esewa' | 'khalti') => void
  isLoading: boolean
}

export function PaymentSelector({ total, onSelect, isLoading }: Props) {
  const [selected, setSelected] = useState<'esewa' | 'khalti' | null>(null)

  return (
    <div className="zk-payment">
      <div className="zk-payment__title">Choose Payment Method</div>
      <div className="zk-payment__total">Total: Rs {total.toLocaleString()}</div>

      <div className="zk-payment__options">
        <button
          type="button"
          className={`zk-payment__option${selected === 'esewa' ? ' zk-payment__option--selected' : ''}`}
          onClick={() => setSelected('esewa')}
        >
          <div className="zk-payment__logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <rect width="24" height="24" rx="4" fill="#60BB46"/>
              <text x="12" y="16" textAnchor="middle" fill="white" fontSize="10" fontWeight="700" fontFamily="sans-serif">eS</text>
            </svg>
            <div>
              <div className="zk-payment__option-name">eSewa</div>
              <div className="zk-payment__option-desc">Pay with your eSewa wallet</div>
            </div>
          </div>
        </button>

        <button
          type="button"
          className={`zk-payment__option${selected === 'khalti' ? ' zk-payment__option--selected' : ''}`}
          onClick={() => setSelected('khalti')}
        >
          <div className="zk-payment__logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <rect width="24" height="24" rx="4" fill="#5C2D91"/>
              <text x="12" y="16" textAnchor="middle" fill="white" fontSize="10" fontWeight="700" fontFamily="sans-serif">K</text>
            </svg>
            <div>
              <div className="zk-payment__option-name">Khalti</div>
              <div className="zk-payment__option-desc">Pay with Khalti digital wallet</div>
            </div>
          </div>
        </button>
      </div>

      <button
        type="button"
        className="zk-payment__pay-btn"
        disabled={!selected || isLoading}
        onClick={() => selected && onSelect(selected)}
      >
        {isLoading ? 'Initiating Payment...' : selected ? `Pay Rs ${total.toLocaleString()} with ${selected === 'esewa' ? 'eSewa' : 'Khalti'}` : 'Select a payment method'}
      </button>

      <div className="zk-payment__secure">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="11" width="18" height="11" rx="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        Secure payment — your data is encrypted
      </div>
    </div>
  )
}
