interface Props {
  orderId: string
  total: number
  gateway?: 'esewa' | 'khalti'
  onContinueShopping?: () => void
}

export function OrderConfirmation({ orderId, total, gateway, onContinueShopping }: Props) {
  return (
    <div className="zk-order-confirm">
      <div className="zk-order-confirm__icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M9 12l2 2 4-4" />
        </svg>
      </div>
      <div className="zk-order-confirm__title">Order Confirmed!</div>
      <div className="zk-order-confirm__id">Order #{orderId.slice(0, 8).toUpperCase()}</div>
      <div className="zk-order-confirm__total">Total Paid: Rs {total.toLocaleString()}</div>
      {gateway && (
        <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
          Paid via {gateway === 'esewa' ? 'eSewa' : 'Khalti'}
        </div>
      )}
      <p className="zk-order-confirm__msg">
        Thank you for your purchase! We'll send you updates about your order.
      </p>
      {onContinueShopping && (
        <button type="button" className="zk-order-confirm__continue" onClick={onContinueShopping}>
          Continue Shopping
        </button>
      )}
    </div>
  )
}
