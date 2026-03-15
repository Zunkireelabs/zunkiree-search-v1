import { useState } from 'react'

interface CheckoutItem {
  name: string
  price: number
  currency: string
  quantity: number
  size: string
  color: string
  url: string
  image: string
}

export interface CheckoutData {
  items: CheckoutItem[]
  subtotal: number
  currency: string
  item_count: number
}

interface CheckoutViewProps {
  checkout: CheckoutData
  brandName: string
}

function CheckoutThumb({ src, alt }: { src: string; alt: string }) {
  const [error, setError] = useState(false)
  if (!src || error) return null
  return <img src={src} alt={alt} className="zk-checkout-view__thumb" onError={() => setError(true)} />
}

export function CheckoutView({ checkout, brandName }: CheckoutViewProps) {
  const formatPrice = (price: number, currency: string) => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency] || currency + ' '
    return `${sym}${price.toLocaleString()}`
  }

  return (
    <div className="zk-checkout-view">
      <div className="zk-checkout-view__header">
        <p className="zk-checkout-view__note">
          Click each item to complete your purchase on {brandName}'s website
        </p>
      </div>
      <div className="zk-checkout-view__items">
        {checkout.items.map((item, index) => (
          <div key={index} className="zk-checkout-view__item">
            <div className="zk-checkout-view__item-info">
              <CheckoutThumb src={item.image} alt={item.name} />
              <div>
                <div className="zk-checkout-view__item-name">{item.name}</div>
                <div className="zk-checkout-view__item-details">
                  {item.size && <span>Size: {item.size}</span>}
                  {item.color && <span>Color: {item.color}</span>}
                  <span>Qty: {item.quantity}</span>
                  <span>{formatPrice(item.price * item.quantity, item.currency)}</span>
                </div>
              </div>
            </div>
            {item.url && (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="zk-checkout-view__buy-btn"
              >
                Buy on {brandName}
              </a>
            )}
          </div>
        ))}
      </div>
      <div className="zk-checkout-view__total">
        <span>Total</span>
        <span>{formatPrice(checkout.subtotal, checkout.currency)}</span>
      </div>
    </div>
  )
}
