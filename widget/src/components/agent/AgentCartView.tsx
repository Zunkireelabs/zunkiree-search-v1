interface AgentCartItem {
  id: number
  productSlug: string
  productName: string
  variationLabel: string | null
  quantity: number
  unitPrice: number
  image: string | null
}

interface Props {
  items: AgentCartItem[]
  subtotal: number
  onRemoveItem: (itemId: number) => void
  onCheckout: () => void
  onUpdateQuantity?: (itemId: number, newQty: number) => void
}

export function AgentCartView({ items, subtotal, onRemoveItem, onCheckout, onUpdateQuantity }: Props) {
  if (!items.length) {
    return (
      <div className="zk-agent-cart zk-agent-cart--empty">
        <div className="zk-empty-state">
          <div className="zk-empty-state__icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <path d="M16 10a4 4 0 01-8 0" />
            </svg>
          </div>
          <div className="zk-empty-state__text">Your cart is empty</div>
        </div>
      </div>
    )
  }

  return (
    <div className="zk-agent-cart">
      <div className="zk-agent-cart__items">
        {items.map(item => (
          <div key={item.id} className="zk-agent-cart__item">
            {item.image && <img src={item.image} alt={item.productName} className="zk-agent-cart__thumb" />}
            <div className="zk-agent-cart__item-info">
              <div className="zk-agent-cart__item-name">{item.productName}</div>
              <div className="zk-agent-cart__item-details">
                {item.variationLabel && <span>{item.variationLabel}</span>}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
                {onUpdateQuantity ? (
                  <div className="zk-qty-control">
                    <button type="button" className="zk-qty-control__btn" onClick={() => onUpdateQuantity(item.id, item.quantity - 1)} disabled={item.quantity <= 1}>-</button>
                    <span className="zk-qty-control__count">{item.quantity}</span>
                    <button type="button" className="zk-qty-control__btn" onClick={() => onUpdateQuantity(item.id, item.quantity + 1)}>+</button>
                  </div>
                ) : (
                  <span style={{ fontSize: '11px', color: '#6b7280' }}>Qty: {item.quantity}</span>
                )}
                <span className="zk-agent-cart__item-price" style={{ margin: 0 }}>Rs {(item.unitPrice * item.quantity).toLocaleString()}</span>
              </div>
            </div>
            <button type="button" className="zk-agent-cart__remove" onClick={() => onRemoveItem(item.id)} aria-label="Remove">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        ))}
      </div>
      <div className="zk-agent-cart__footer">
        <div className="zk-agent-cart__subtotal">
          <span>Subtotal ({items.length} item{items.length !== 1 ? 's' : ''})</span>
          <span className="zk-agent-cart__subtotal-price">Rs {subtotal.toLocaleString()}</span>
        </div>
        <button type="button" className="zk-agent-cart__checkout-btn" onClick={onCheckout}>
          Proceed to Checkout
        </button>
      </div>
    </div>
  )
}
