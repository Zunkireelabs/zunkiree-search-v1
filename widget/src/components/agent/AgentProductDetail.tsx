import { useState } from 'react'

interface Variation {
  variationId: number
  attributes: Record<string, string>
  displayPrice: number
  displayRegularPrice: number
  isInStock: boolean
  image: string | null
}

export interface AgentProduct {
  id: number
  slug: string
  name: string
  description: string | null
  price: string
  priceHigh: string | null
  currency: string
  availability: string
  productType: string
  categories: string[]
  images: string[]
  variations?: Variation[]
}

interface Props {
  product: AgentProduct
  onAddToCart: (slug: string, variationId?: number, variationLabel?: string, quantity?: number) => void
  onAddToWishlist: (slug: string) => void
  onBack?: () => void
}

export function AgentProductDetail({ product, onAddToCart, onAddToWishlist, onBack }: Props) {
  const [selectedImage, setSelectedImage] = useState(0)
  const [selectedVariation, setSelectedVariation] = useState<Variation | null>(null)
  const [quantity, setQuantity] = useState(1)
  const [imageKey, setImageKey] = useState(0)

  const price = selectedVariation
    ? selectedVariation.displayPrice
    : parseFloat(product.price)
  const hasVariations = product.variations && product.variations.length > 0

  const getVariationLabel = (v: Variation) => {
    return Object.values(v.attributes).join(' / ').toUpperCase()
  }

  const handleImageSelect = (idx: number) => {
    setSelectedImage(idx)
    setImageKey(prev => prev + 1)
  }

  const handleAddToCart = () => {
    if (hasVariations && !selectedVariation) return
    onAddToCart(
      product.slug,
      selectedVariation?.variationId,
      selectedVariation ? getVariationLabel(selectedVariation) : undefined,
      quantity
    )
  }

  return (
    <div className="zk-agent-detail">
      {onBack && (
        <button type="button" className="zk-agent-detail__back" onClick={onBack}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
          Back to results
        </button>
      )}

      <div className="zk-agent-detail__gallery">
        {product.images.length > 0 && (
          <>
            <div className="zk-agent-detail__main-image">
              <img
                key={imageKey}
                src={product.images[selectedImage]}
                alt={product.name}
                style={{ animation: 'zk-fade-in 250ms ease' }}
              />
            </div>
            {product.images.length > 1 && (
              <div className="zk-agent-detail__thumbs">
                {product.images.slice(0, 5).map((img, i) => (
                  <button
                    key={i}
                    type="button"
                    className={`zk-agent-detail__thumb${i === selectedImage ? ' zk-agent-detail__thumb--active' : ''}`}
                    onClick={() => handleImageSelect(i)}
                  >
                    <img src={img} alt={`${product.name} ${i + 1}`} />
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="zk-agent-detail__info">
        <h3 className="zk-agent-detail__name">{product.name}</h3>
        <div className="zk-agent-detail__price">
          Rs {price.toLocaleString()}
          {product.priceHigh && !selectedVariation && (
            <span className="zk-agent-detail__price-range"> - Rs {parseFloat(product.priceHigh).toLocaleString()}</span>
          )}
        </div>

        {product.categories.length > 0 && (
          <div className="zk-agent-detail__categories">
            {product.categories.map(cat => (
              <span key={cat} className="zk-agent-detail__cat-tag">{cat.replace(/-/g, ' ')}</span>
            ))}
          </div>
        )}

        {product.description && (
          <p className="zk-agent-detail__desc">{product.description}</p>
        )}

        {hasVariations && (
          <div className="zk-agent-detail__variations">
            <div className="zk-agent-detail__var-label">
              {Object.keys(product.variations![0].attributes)[0]?.replace('attribute_pa_', '').toUpperCase() || 'Option'}
            </div>
            <div className="zk-agent-detail__var-options">
              {product.variations!.map(v => (
                <button
                  key={v.variationId}
                  type="button"
                  className={`zk-var-pill${selectedVariation?.variationId === v.variationId ? ' zk-var-pill--active' : ''}${!v.isInStock ? ' zk-var-pill--disabled' : ''}`}
                  onClick={() => v.isInStock && setSelectedVariation(v)}
                  disabled={!v.isInStock}
                >
                  {getVariationLabel(v)}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Quantity selector */}
        <div className="zk-agent-detail__qty-section">
          <div className="zk-agent-detail__qty-label">QUANTITY</div>
          <div className="zk-qty-control">
            <button type="button" className="zk-qty-control__btn" onClick={() => setQuantity(q => Math.max(1, q - 1))} disabled={quantity <= 1}>-</button>
            <span className="zk-qty-control__count">{quantity}</span>
            <button type="button" className="zk-qty-control__btn" onClick={() => setQuantity(q => q + 1)}>+</button>
          </div>
        </div>

        <div className="zk-agent-detail__actions">
          <button
            type="button"
            className="zk-agent-detail__add-btn"
            onClick={handleAddToCart}
            disabled={hasVariations && !selectedVariation}
          >
            {hasVariations && !selectedVariation ? 'Select a size' : `Add to Cart${quantity > 1 ? ` (${quantity})` : ''}`}
          </button>
          <button
            type="button"
            className="zk-agent-detail__wishlist-btn"
            onClick={() => onAddToWishlist(product.slug)}
            title="Save to wishlist"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}
