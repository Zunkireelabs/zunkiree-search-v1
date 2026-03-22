import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getCustomerOrders } from '../api'
import type { Order } from '../types'

const statusColors: Record<string, string> = {
  pending: '#fbbf24', payment_pending: '#f59e0b', paid: '#34d399',
  processing: '#60a5fa', shipped: '#818cf8', delivered: '#10b981',
  cancelled: '#f87171', refunded: '#fb923c',
}

export function CustomerDetail() {
  const { email } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<{ email: string; total_orders: number; total_spent: number; orders: Order[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!email) return
    getCustomerOrders(decodeURIComponent(email))
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [email])

  const formatPrice = (amount: number, currency = 'NPR') => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs ', INR: '₹' }
    return `${symbols[currency] || currency + ' '}${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
  }
  const formatDate = (d: string | null) => d ? new Date(d).toLocaleString() : '-'

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
  if (!data) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Customer not found</div>

  // Extract contact info from the most recent order's address
  const latestAddr = data.orders[0]?.billing_address || data.orders[0]?.shipping_address
  const customerName = latestAddr?.full_name || null
  const customerPhone = latestAddr?.phone || null
  const customerLocation = latestAddr
    ? [latestAddr.city, latestAddr.state, latestAddr.country].filter(Boolean).join(', ')
    : null

  return (
    <div>
      <button onClick={() => navigate('/customers')} style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', fontSize: 13, marginBottom: 16 }}>
        &larr; Back to Customers
      </button>

      {/* Customer header */}
      <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', marginBottom: 24 }}>
        <div style={{ width: 56, height: 56, borderRadius: 28, background: '#e0e7ff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <span style={{ fontSize: 22, fontWeight: 700, color: '#4338ca' }}>
            {(customerName || data.email)[0].toUpperCase()}
          </span>
        </div>
        <div>
          {customerName && <h2 style={{ fontSize: 22, fontWeight: 600 }}>{customerName}</h2>}
          <p style={{ fontSize: 14, color: customerName ? '#6b7280' : '#111827', fontWeight: customerName ? 400 : 600, marginTop: customerName ? 2 : 0 }}>{data.email}</p>
          <div style={{ display: 'flex', gap: 16, marginTop: 6 }}>
            {customerPhone && (
              <span style={{ fontSize: 13, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" />
                </svg>
                {customerPhone}
              </span>
            )}
            {customerLocation && (
              <span style={{ fontSize: 13, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
                {customerLocation}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Stats cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 24 }}>
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Total Orders</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#111827' }}>{data.total_orders}</div>
        </div>
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Total Spent</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#059669' }}>{formatPrice(data.total_spent)}</div>
        </div>
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Avg. Order Value</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#111827' }}>
            {data.total_orders > 0 ? formatPrice(data.total_spent / data.total_orders) : '-'}
          </div>
        </div>
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Phone</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>{customerPhone || '-'}</div>
        </div>
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Location</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: '#111827' }}>{customerLocation || '-'}</div>
        </div>
      </div>

      {/* Orders list */}
      <div style={{ background: 'white', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600 }}>Order History</h3>
        </div>

        {data.orders.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No orders found</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Order</th>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Items</th>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Status</th>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Payment</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Total</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Date</th>
              </tr>
            </thead>
            <tbody>
              {data.orders.map(order => (
                <tr
                  key={order.id}
                  style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }}
                  onClick={() => navigate(`/orders/${order.id}`)}
                >
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: '#2563eb' }}>{order.order_number}</td>
                  <td style={{ padding: '12px 16px', color: '#6b7280' }}>
                    {order.items.map(i => i.name).join(', ').slice(0, 60)}{order.items.map(i => i.name).join(', ').length > 60 ? '...' : ''}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                      background: (statusColors[order.status] || '#9ca3af') + '20',
                      color: statusColors[order.status] || '#6b7280',
                    }}>{order.status}</span>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                      background: order.payment_status === 'paid' ? '#dcfce7' : '#fef3c7',
                      color: order.payment_status === 'paid' ? '#166534' : '#92400e',
                    }}>{order.payment_status}</span>
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600 }}>{formatPrice(order.total, order.currency)}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', color: '#6b7280' }}>{formatDate(order.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
