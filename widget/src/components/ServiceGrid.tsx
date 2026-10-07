import { useRef } from 'react'
import { ServiceCard, ServiceItem } from './ServiceCard'

interface ServiceGridProps {
  services: ServiceItem[]
  onBookService: (name: string) => void
  onServiceDetails: (name: string) => void
}

export function ServiceGrid({ services, onBookService, onServiceDetails }: ServiceGridProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  const scroll = (direction: 'left' | 'right') => {
    if (!scrollRef.current) return
    const amount = 260
    scrollRef.current.scrollBy({
      left: direction === 'left' ? -amount : amount,
      behavior: 'smooth',
    })
  }

  if (!services.length) return null

  return (
    <div className="zk-product-grid">
      <div className="zk-product-grid__header">
        <span className="zk-product-grid__count">
          {services.length} service{services.length !== 1 ? 's' : ''}
        </span>
        {services.length > 2 && (
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
        {services.map(service => (
          <ServiceCard
            key={service.id}
            service={service}
            onBookService={onBookService}
            onServiceDetails={onServiceDetails}
          />
        ))}
      </div>
    </div>
  )
}
