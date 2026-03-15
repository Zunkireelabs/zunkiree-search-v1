import { useState } from 'react'

export interface CartItem {
  product_id: string
  name: string
  price: number
  currency: string
  quantity: number
  size: string
  color: string
  image: string
  url: string
}

export interface CartState {
  items: CartItem[]
  item_count: number
  subtotal: number
  currency: string
}

interface CartViewProps {
  cart: CartState
  onRemoveItem: (index: number) => void
  onCheckout: () => void
}

function CartThumb({ src, alt }: { src: string; alt: string }) {
  const [error, setError] = useState(false)
  if (!src || error) return null
  return <img src={src} alt={alt} className="zk-cart-view__thumb" onError={() => setError(true)} />
}

export function CartView({ cart, onRemoveItem, onCheckout }: CartViewProps) {
  const formatPrice = (price: number, currency: string) => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency] || currency + ' '
    return `${sym}${price.toLocaleString()}`
  }

  if (!cart.items.length) {
    return (
      <div className="zk-cart-view zk-cart-view--empty">
        <p>Your cart is empty</p>
      </div>
    )
  }

  return (
    <div className="zk-cart-view">
      <div className="zk-cart-view__items">
        {cart.items.map((item, index) => (
          <div key={`${item.product_id}-${index}`} className="zk-cart-view__item">
            <CartThumb src={item.image} alt={item.name} />
            <div className="zk-cart-view__item-info">
              <div className="zk-cart-view__item-name">{item.name}</div>
              <div className="zk-cart-view__item-details">
                {item.size && <span>Size: {item.size}</span>}
                {item.color && <span>Color: {item.color}</span>}
                <span>Qty: {item.quantity}</span>
              </div>
              <div className="zk-cart-view__item-price">
                {formatPrice(item.price * item.quantity, item.currency)}
              </div>
            </div>
            <button
              type="button"
              className="zk-cart-view__remove"
              onClick={() => onRemoveItem(index)}
              aria-label="Remove item"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        ))}
      </div>
      <div className="zk-cart-view__footer">
        <div className="zk-cart-view__subtotal">
          <span>Subtotal ({cart.item_count} item{cart.item_count !== 1 ? 's' : ''})</span>
          <span className="zk-cart-view__subtotal-price">
            {formatPrice(cart.subtotal, cart.currency)}
          </span>
        </div>
        <button type="button" className="zk-cart-view__checkout-btn" onClick={onCheckout}>
          Checkout
        </button>
      </div>
    </div>
  )
}
