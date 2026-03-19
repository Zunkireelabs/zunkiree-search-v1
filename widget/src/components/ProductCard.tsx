export interface Product {
  id: string
  name: string
  description: string
  price: number | null
  currency: string
  original_price: number | null
  images: string[]
  url: string
  brand: string
  category: string
  sizes: string[]
  colors: string[]
  in_stock: boolean
}

interface ProductCardProps {
  product: Product
  onAddToCart: (productId: string, size?: string, color?: string) => void
  onAddToWishlist?: (productId: string) => void
}

export function ProductCard({ product, onAddToCart, onAddToWishlist }: ProductCardProps) {
  const formatPrice = (price: number | null, currency: string) => {
    if (price === null) return ''
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency] || currency + ' '
    return `${sym}${price.toLocaleString()}`
  }

  const imageUrl = product.images[0] || ''

  return (
    <div className="zk-product-card" onClick={() => product.url && window.open(product.url, '_blank')}>
      {imageUrl ? (
        <div className="zk-product-card__image">
          <img src={imageUrl} alt={product.name} loading="lazy" />
          {!product.in_stock && <span className="zk-product-card__badge zk-product-card__badge--out">Out of Stock</span>}
          {onAddToWishlist && (
            <button
              type="button"
              className="zk-product-card__wishlist-btn"
              onClick={(e) => {
                e.stopPropagation()
                onAddToWishlist(product.id)
              }}
              title="Save"
              aria-label="Save"
            >
              {/* Bookmark icon */}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
              </svg>
            </button>
          )}
        </div>
      ) : (
        <div className="zk-product-card__image zk-product-card__image--placeholder">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
        </div>
      )}
      <div className="zk-product-card__info">
        <div className="zk-product-card__name">{product.name}</div>
        <div className="zk-product-card__price-row">
          {product.price !== null && (
            <span className="zk-product-card__price">
              {formatPrice(product.price, product.currency)}
            </span>
          )}
          {product.original_price && product.original_price > (product.price || 0) && (
            <span className="zk-product-card__original-price">
              {formatPrice(product.original_price, product.currency)}
            </span>
          )}
        </div>
        <div className="zk-product-card__actions">
          {product.in_stock ? (
            <button
              type="button"
              className="zk-product-card__add-btn"
              onClick={(e) => {
                e.stopPropagation()
                onAddToCart(product.id)
              }}
            >
              Add to Cart
            </button>
          ) : (
            <button type="button" className="zk-product-card__add-btn" disabled>
              Sold Out
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
