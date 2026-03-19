import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getOrder, updateOrderStatus } from '../api'
import type { Order } from '../types'

const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  pending: ['processing', 'cancelled'],
  payment_pending: ['cancelled'],
  paid: ['processing', 'cancelled', 'refunded'],
  processing: ['shipped', 'cancelled'],
  shipped: ['delivered'],
  delivered: [],
  cancelled: [],
  refunded: [],
}

export function OrderDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    if (!id) return
    getOrder(id).then(res => setOrder(res.order)).catch(console.error).finally(() => setLoading(false))
  }, [id])

  const handleStatusUpdate = async (newStatus: string) => {
    if (!order || updating) return
    setUpdating(true)
    try {
      const res = await updateOrderStatus(order.id, newStatus)
      setOrder(res.order)
    } catch (err) {
      console.error(err)
    } finally {
      setUpdating(false)
    }
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
  if (!order) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Order not found</div>

  const formatPrice = (amount: number) => `$${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
  const transitions = ALLOWED_TRANSITIONS[order.status] || []

  const renderAddress = (addr: Order['billing_address'], title: string) => {
    if (!addr) return null
    return (
      <div style={{ flex: 1 }}>
        <h4 style={{ fontSize: 13, fontWeight: 600, color: '#6b7280', marginBottom: 8 }}>{title}</h4>
        <div style={{ fontSize: 13, lineHeight: 1.6, color: '#374151' }}>
          <div style={{ fontWeight: 500 }}>{addr.full_name}</div>
          <div>{addr.line1}</div>
          {addr.line2 && <div>{addr.line2}</div>}
          <div>{addr.city}, {addr.state} {addr.postal_code}</div>
          <div>{addr.country}</div>
          {addr.phone && <div>{addr.phone}</div>}
        </div>
      </div>
    )
  }

  return (
    <div>
      <button onClick={() => navigate('/orders')} style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', fontSize: 13, marginBottom: 16 }}>
        &larr; Back to Orders
      </button>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 22, fontWeight: 600 }}>Order {order.order_number}</h2>
          <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
            {order.created_at ? new Date(order.created_at).toLocaleString() : ''}
          </p>
        </div>
        {transitions.length > 0 && (
          <div style={{ display: 'flex', gap: 8 }}>
            {transitions.map(status => (
              <button
                key={status}
                onClick={() => handleStatusUpdate(status)}
                disabled={updating}
                style={{
                  padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer',
                  border: '1px solid #d1d5db', background: 'white', color: '#374151',
                  opacity: updating ? 0.6 : 1,
                }}
              >
                Mark as {status}
              </button>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        {/* Items */}
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Items</h3>
          {order.items.map((item, idx) => (
            <div key={idx} style={{ display: 'flex', gap: 12, padding: '12px 0', borderBottom: idx < order.items.length - 1 ? '1px solid #f3f4f6' : 'none' }}>
              {item.image && (
                <img src={item.image} alt={item.name} style={{ width: 48, height: 48, borderRadius: 6, objectFit: 'cover' }} />
              )}
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{item.name}</div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                  {item.size && `Size: ${item.size} `}
                  {item.color && `Color: ${item.color} `}
                  Qty: {item.quantity}
                </div>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{formatPrice(item.price * item.quantity)}</div>
            </div>
          ))}
          <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 12, marginTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
              <span style={{ color: '#6b7280' }}>Subtotal</span><span>{formatPrice(order.subtotal)}</span>
            </div>
            {order.tax > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                <span style={{ color: '#6b7280' }}>Tax</span><span>{formatPrice(order.tax)}</span>
              </div>
            )}
            {order.shipping_cost > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                <span style={{ color: '#6b7280' }}>Shipping</span><span>{formatPrice(order.shipping_cost)}</span>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 16, fontWeight: 700, marginTop: 8 }}>
              <span>Total</span><span>{formatPrice(order.total)}</span>
            </div>
          </div>
        </div>

        {/* Order Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Status</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280' }}>Order Status</span>
                <span style={{ fontWeight: 600 }}>{order.status}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280' }}>Payment</span>
                <span style={{ fontWeight: 600 }}>{order.payment_status}</span>
              </div>
              {order.payment_method && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>Method</span>
                  <span style={{ fontWeight: 500 }}>{order.payment_method}</span>
                </div>
              )}
              {order.shopper_email && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>Email</span>
                  <span style={{ fontWeight: 500 }}>{order.shopper_email}</span>
                </div>
              )}
            </div>
          </div>

          {(order.billing_address || order.shipping_address) && (
            <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Addresses</h3>
              <div style={{ display: 'flex', gap: 24 }}>
                {renderAddress(order.billing_address, 'Billing')}
                {renderAddress(order.shipping_address, 'Shipping')}
              </div>
            </div>
          )}

          {order.notes && (
            <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Notes</h3>
              <p style={{ fontSize: 13, color: '#374151' }}>{order.notes}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
