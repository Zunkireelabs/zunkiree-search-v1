interface WishlistItem {
  slug: string
  name: string
  price: string
  image: string | null
}

interface Props {
  items: WishlistItem[]
  onRemove: (slug: string) => void
  onAddToCart: (slug: string) => void
}

export function WishlistView({ items, onRemove, onAddToCart }: Props) {
  if (!items.length) {
    return (
      <div className="zk-wishlist zk-wishlist--empty">
        <div className="zk-empty-state">
          <div className="zk-empty-state__icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
          </div>
          <div className="zk-empty-state__text">Your wishlist is empty</div>
        </div>
      </div>
    )
  }

  return (
    <div className="zk-wishlist">
      <div className="zk-wishlist__header">Saved Items ({items.length})</div>
      <div className="zk-wishlist__items">
        {items.map(item => (
          <div key={item.slug} className="zk-wishlist__item">
            {item.image && <img src={item.image} alt={item.name} className="zk-wishlist__thumb" />}
            <div className="zk-wishlist__info">
              <div className="zk-wishlist__name">{item.name}</div>
              <div className="zk-wishlist__price">Rs {parseFloat(item.price).toLocaleString()}</div>
            </div>
            <div className="zk-wishlist__actions">
              <button type="button" className="zk-wishlist__cart-btn" onClick={() => onAddToCart(item.slug)}>
                Add to Cart
              </button>
              <button type="button" className="zk-wishlist__remove-btn" onClick={() => onRemove(item.slug)} aria-label="Remove">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
