import React from 'react'

// SBAL-Z6: shape matches clinic_agent._services_ui / ui.service_detail
// (backend/app/services/clinic_agent.py) — price/duration are already
// plain numbers (NPR, minutes), image_url is always null today (no image
// data on ClinicMD/Zennly treatments).
export interface ServiceItem {
  id: string
  name: string
  price: number | null
  duration: number | null
  image_url: string | null
  description?: string | null
}

interface ServiceCardProps {
  service: ServiceItem
  onBookService: (name: string) => void
  onServiceDetails?: (name: string) => void
  showDescription?: boolean
}

export const ServiceCard = React.memo(function ServiceCard({
  service, onBookService, onServiceDetails, showDescription,
}: ServiceCardProps) {
  const formatPrice = (price: number | null) => price === null ? '' : `Rs ${price.toLocaleString()}`

  return (
    <div className="zk-product-card">
      {service.image_url ? (
        <div className="zk-product-card__image">
          <img src={service.image_url} alt={service.name} loading="lazy" />
        </div>
      ) : (
        <div className="zk-product-card__image zk-product-card__image--placeholder">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2" />
          </svg>
        </div>
      )}
      <div className="zk-product-card__info">
        <div className="zk-product-card__name">{service.name}</div>
        {showDescription && service.description && (
          <div className="zk-service-card__description">{service.description}</div>
        )}
        <div className="zk-product-card__price-row">
          {service.price !== null && (
            <span className="zk-product-card__price">{formatPrice(service.price)}</span>
          )}
          {service.duration !== null && (
            <span className="zk-room-card__per-night">{service.duration} min</span>
          )}
        </div>
        <div className={`zk-product-card__actions${onServiceDetails ? ' zk-product-card__actions--row' : ''}`}>
          <button
            type="button"
            className="zk-product-card__add-btn"
            onClick={(e) => {
              e.stopPropagation()
              onBookService(service.name)
            }}
          >
            Book
          </button>
          {onServiceDetails && (
            <button
              type="button"
              className="zk-service-card__details-btn"
              onClick={(e) => {
                e.stopPropagation()
                onServiceDetails(service.name)
              }}
            >
              Details
            </button>
          )}
        </div>
      </div>
    </div>
  )
})
