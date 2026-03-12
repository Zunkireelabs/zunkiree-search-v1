import React from 'react'

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
}

export function ProductCard({ product, onAddToCart }: ProductCardProps) {
  const [selectedSize, setSelectedSize] = React.useState(product.sizes[0] || '')
  const [selectedColor, setSelectedColor] = React.useState(product.colors[0] || '')

  const formatPrice = (price: number | null, currency: string) => {
    if (price === null) return ''
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency] || currency + ' '
    return `${sym}${price.toLocaleString()}`
  }

  const imageUrl = product.images[0] || ''

  return (
    <div className="zk-product-card">
      {imageUrl ? (
        <div className="zk-product-card__image">
          <img src={imageUrl} alt={product.name} loading="lazy" />
          {!product.in_stock && <span className="zk-product-card__badge zk-product-card__badge--out">Out of Stock</span>}
          {product.in_stock && <span className="zk-product-card__badge zk-product-card__badge--in">In Stock</span>}
        </div>
      ) : (
        <div className="zk-product-card__image zk-product-card__image--placeholder">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5">
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

        {product.sizes.length > 0 && (
          <div className="zk-product-card__sizes">
            {product.sizes.map(size => (
              <button
                key={size}
                type="button"
                className={`zk-size-pill${selectedSize === size ? ' zk-size-pill--active' : ''}`}
                onClick={() => setSelectedSize(size)}
              >
                {size}
              </button>
            ))}
          </div>
        )}

        {product.colors.length > 0 && (
          <div className="zk-product-card__colors">
            {product.colors.map(color => (
              <button
                key={color}
                type="button"
                className={`zk-color-swatch${selectedColor === color ? ' zk-color-swatch--active' : ''}`}
                onClick={() => setSelectedColor(color)}
                title={color}
              >
                {color}
              </button>
            ))}
          </div>
        )}

        <div className="zk-product-card__actions">
          {product.in_stock ? (
            <button
              type="button"
              className="zk-product-card__add-btn"
              onClick={() => onAddToCart(product.id, selectedSize, selectedColor)}
            >
              Add to Cart
            </button>
          ) : (
            <button type="button" className="zk-product-card__add-btn" disabled>
              Sold Out
            </button>
          )}
          {product.url && (
            <a href={product.url} target="_blank" rel="noopener noreferrer" className="zk-product-card__view-link">
              View
            </a>
          )}
        </div>
      </div>
    </div>
  )
}
