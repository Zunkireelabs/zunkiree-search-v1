interface Props {
  productName: string
  variationLabel?: string | null
  quantity: number
  unitPrice: number
  image?: string | null
  cartItemCount: number
  cartSubtotal: number
  onViewCart?: () => void
  onContinueShopping?: () => void
}

export function AgentCartConfirmation({
  productName,
  variationLabel,
  quantity,
  unitPrice,
  image,
  cartItemCount,
  cartSubtotal,
  onViewCart,
  onContinueShopping,
}: Props) {
  return (
    <div className="zk-cart-confirm">
      <div className="zk-cart-confirm__body">
        {image && (
          <img
            className="zk-cart-confirm__thumb"
            src={image}
            alt={productName}
          />
        )}
        <div className="zk-cart-confirm__info">
          <div className="zk-cart-confirm__badge">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#16a34a" strokeWidth="2.5">
              <path d="M9 12l2 2 4-4" />
              <circle cx="12" cy="12" r="10" />
            </svg>
            Added to Cart
          </div>
          <div className="zk-cart-confirm__name">{productName}</div>
          {variationLabel && (
            <div className="zk-cart-confirm__variation">{variationLabel}</div>
          )}
          <div className="zk-cart-confirm__price">
            Rs {unitPrice.toLocaleString()} × {quantity}
          </div>
        </div>
      </div>
      <div className="zk-cart-confirm__footer">
        <div className="zk-cart-confirm__summary">
          {cartItemCount} item{cartItemCount !== 1 ? 's' : ''} · Rs {cartSubtotal.toLocaleString()}
        </div>
        <div className="zk-cart-confirm__actions">
          {onViewCart && (
            <button type="button" className="zk-cart-confirm__view-btn" onClick={onViewCart}>
              View Cart
            </button>
          )}
          {onContinueShopping && (
            <button type="button" className="zk-cart-confirm__continue-btn" onClick={onContinueShopping}>
              Continue Shopping
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
