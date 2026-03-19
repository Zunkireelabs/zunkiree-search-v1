export interface WishlistItem {
  product_id: string
  name: string
  price: number | null
  currency: string
  original_price: number | null
  image: string
  url: string
  in_stock: boolean
  sizes: string[]
  colors: string[]
}

interface WishlistViewProps {
  items: WishlistItem[]
  onRemove: (productId: string) => void
  onMoveToCart: (productId: string, size?: string, color?: string) => void
}

export function WishlistView({ items, onRemove, onMoveToCart }: WishlistViewProps) {
  const formatPrice = (price: number | null, currency: string) => {
    if (price === null) return ''
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency] || currency + ' '
    return `${sym}${price.toLocaleString()}`
  }

  if (!items.length) {
    return (
      <div className="zk-wishlist-view zk-wishlist-view--empty">
        <p>Your wishlist is empty</p>
      </div>
    )
  }

  return (
    <div className="zk-wishlist-view">
      <div className="zk-wishlist-view__header">
        <span className="zk-wishlist-view__title">Wishlist ({items.length})</span>
      </div>
      <div className="zk-wishlist-view__items">
        {items.map(item => (
          <div key={item.product_id} className="zk-wishlist-view__item">
            {item.image && (
              <img src={item.image} alt={item.name} className="zk-wishlist-view__thumb" />
            )}
            <div className="zk-wishlist-view__item-info">
              <div className="zk-wishlist-view__item-name">{item.name}</div>
              {item.price !== null && (
                <div className="zk-wishlist-view__item-price">
                  {formatPrice(item.price, item.currency)}
                  {item.original_price && item.original_price > (item.price || 0) && (
                    <span className="zk-wishlist-view__original-price">
                      {formatPrice(item.original_price, item.currency)}
                    </span>
                  )}
                </div>
              )}
            </div>
            <div className="zk-wishlist-view__actions">
              {item.in_stock && (
                <button
                  type="button"
                  className="zk-wishlist-view__cart-btn"
                  onClick={() => onMoveToCart(item.product_id)}
                  title="Move to Cart"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="9" cy="21" r="1" />
                    <circle cx="20" cy="21" r="1" />
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
                  </svg>
                </button>
              )}
              <button
                type="button"
                className="zk-wishlist-view__remove-btn"
                onClick={() => onRemove(item.product_id)}
                aria-label="Remove from wishlist"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
