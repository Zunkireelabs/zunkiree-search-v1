import { useRef, useState } from 'react'
import type { AgentProduct } from './AgentProductDetail'

interface Props {
  products: AgentProduct[]
  title?: string
  onViewProduct: (slug: string) => void
  onAddToCart: (slug: string) => void
}

function ProductImage({ src, alt }: { src: string; alt: string }) {
  const [loaded, setLoaded] = useState(false)
  return (
    <>
      {!loaded && <div className="zk-agent-card__image--skeleton" style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0 }} />}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        onLoad={() => setLoaded(true)}
        style={{ opacity: loaded ? 1 : 0, transition: 'opacity 200ms' }}
      />
    </>
  )
}

export function AgentProductGrid({ products, title, onViewProduct }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)

  const scroll = (direction: 'left' | 'right') => {
    if (!scrollRef.current) return
    scrollRef.current.scrollBy({
      left: direction === 'left' ? -260 : 260,
      behavior: 'smooth',
    })
  }

  if (!products.length) return null

  return (
    <div className="zk-agent-grid">
      <div className="zk-agent-grid__header">
        <span className="zk-agent-grid__count">
          {title || `${products.length} product${products.length !== 1 ? 's' : ''}`}
        </span>
        {products.length > 2 && (
          <div className="zk-agent-grid__arrows">
            <button type="button" className="zk-agent-grid__arrow" onClick={() => scroll('left')} aria-label="Scroll left">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <button type="button" className="zk-agent-grid__arrow" onClick={() => scroll('right')} aria-label="Scroll right">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg>
            </button>
          </div>
        )}
      </div>
      <div className="zk-agent-grid__scroll" ref={scrollRef}>
        {products.map(product => (
          <div key={product.slug} className="zk-agent-card">
            <div className="zk-agent-card__image" onClick={() => onViewProduct(product.slug)} style={{ position: 'relative' }}>
              {product.images[0] ? (
                <ProductImage src={product.images[0]} alt={product.name} />
              ) : (
                <div className="zk-agent-card__no-image">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>
                </div>
              )}
            </div>
            <div className="zk-agent-card__info">
              <div className="zk-agent-card__name" onClick={() => onViewProduct(product.slug)}>{product.name}</div>
              <div className="zk-agent-card__price">
                Rs {parseFloat(product.price).toLocaleString()}
                {product.priceHigh && (
                  <span className="zk-agent-card__price-high"> - Rs {parseFloat(product.priceHigh).toLocaleString()}</span>
                )}
              </div>
              <div className="zk-agent-card__actions">
                <button type="button" className="zk-agent-card__add-btn" onClick={() => onViewProduct(product.slug)}>
                  View Details
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
