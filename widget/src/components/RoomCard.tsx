export interface Room {
  id: string
  name: string
  description: string
  price: number | null
  currency: string
  original_price: number | null
  images: string[]
  amenities: string[]
  capacity: number
  room_type: string
  available: boolean
}

interface RoomCardProps {
  room: Room
  onBookRoom: (roomId: string) => void
}

export function RoomCard({ room, onBookRoom }: RoomCardProps) {
  const formatPrice = (price: number | null, currency: string) => {
    if (price === null) return ''
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency] || currency + ' '
    return `${sym}${price.toLocaleString()}`
  }

  const imageUrl = room.images[0] || ''

  return (
    <div className="zk-product-card">
      {imageUrl ? (
        <div className="zk-product-card__image">
          <img src={imageUrl} alt={room.name} loading="lazy" />
          {!room.available && <span className="zk-product-card__badge zk-product-card__badge--out">Unavailable</span>}
        </div>
      ) : (
        <div className="zk-product-card__image zk-product-card__image--placeholder">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
        </div>
      )}
      <div className="zk-product-card__info">
        <div className="zk-product-card__name">{room.name}</div>
        {room.amenities.length > 0 && (
          <div className="zk-room-card__amenities">
            {room.amenities.slice(0, 3).map((a, i) => (
              <span key={i} className="zk-room-card__amenity">{a}</span>
            ))}
          </div>
        )}
        <div className="zk-product-card__price-row">
          {room.price !== null && (
            <span className="zk-product-card__price">
              {formatPrice(room.price, room.currency)}<span className="zk-room-card__per-night">/night</span>
            </span>
          )}
          {room.original_price && room.original_price > (room.price || 0) && (
            <span className="zk-product-card__original-price">
              {formatPrice(room.original_price, room.currency)}
            </span>
          )}
        </div>
        <div className="zk-product-card__actions">
          {room.available ? (
            <button
              type="button"
              className="zk-product-card__add-btn"
              onClick={(e) => {
                e.stopPropagation()
                onBookRoom(room.id)
              }}
            >
              Book Now
            </button>
          ) : (
            <button type="button" className="zk-product-card__add-btn" disabled>
              Unavailable
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
