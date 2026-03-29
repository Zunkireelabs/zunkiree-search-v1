import { useRef } from 'react'
import { RoomCard, Room } from './RoomCard'

interface RoomGridProps {
  rooms: Room[]
  onBookRoom: (roomId: string) => void
}

export function RoomGrid({ rooms, onBookRoom }: RoomGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  const scroll = (direction: 'left' | 'right') => {
    if (!scrollRef.current) return
    const amount = 260
    scrollRef.current.scrollBy({
      left: direction === 'left' ? -amount : amount,
      behavior: 'smooth',
    })
  }

  if (!rooms.length) return null

  return (
    <div className="zk-product-grid">
      <div className="zk-product-grid__header">
        <span className="zk-product-grid__count">
          {rooms.length} room{rooms.length !== 1 ? 's' : ''} available
        </span>
        {rooms.length > 2 && (
          <div className="zk-product-grid__arrows">
            <button type="button" className="zk-product-grid__arrow" onClick={() => scroll('left')} aria-label="Scroll left">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
            <button type="button" className="zk-product-grid__arrow" onClick={() => scroll('right')} aria-label="Scroll right">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
          </div>
        )}
      </div>
      <div className="zk-product-grid__scroll" ref={scrollRef}>
        {rooms.map(room => (
          <RoomCard key={room.id} room={room} onBookRoom={onBookRoom} />
        ))}
      </div>
    </div>
  )
}
