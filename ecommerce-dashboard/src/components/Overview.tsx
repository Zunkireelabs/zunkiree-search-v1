import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAnalyticsOverview, getOrders, getProductStats } from '../api'
import type { AnalyticsOverview, Order, ProductStats } from '../types'

export function Overview() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [recentOrders, setRecentOrders] = useState<Order[]>([])
  const [productStats, setProductStats] = useState<ProductStats | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      getAnalyticsOverview(),
      getOrders(1),
      getProductStats(),
    ]).then(([ov, ordersRes, ps]) => {
      setOverview(ov)
      setRecentOrders(ordersRes.orders?.slice(0, 5) || [])
      setProductStats(ps)
    }).catch(console.error).finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>

  const formatPrice = (amount: number, currency = 'NPR') => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs ', INR: '₹' }
    return `${symbols[currency] || currency + ' '}${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
  }

  const kpis = overview ? [
    { label: 'Total Revenue', value: formatPrice(overview.total_revenue), color: '#059669' },
    { label: 'Total Orders', value: overview.total_orders.toString(), color: '#2563eb' },
    { label: 'Avg Order Value', value: formatPrice(overview.avg_order_value), color: '#7c3aed' },
    { label: 'Pending Orders', value: overview.pending_orders.toString(), color: '#d97706' },
  ] : []

  const statusColors: Record<string, string> = {
    pending: '#fbbf24', payment_pending: '#f59e0b', paid: '#34d399',
    processing: '#60a5fa', shipped: '#818cf8', delivered: '#10b981',
    cancelled: '#f87171', refunded: '#fb923c',
  }

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Overview</h2>

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 32 }}>
        {kpis.map(kpi => (
          <div key={kpi.label} style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
            <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>{kpi.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: kpi.color }}>{kpi.value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        {/* Recent Orders */}
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600 }}>Recent Orders</h3>
            <button onClick={() => navigate('/orders')} style={{ fontSize: 13, color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer' }}>View All</button>
          </div>
          {recentOrders.length === 0 ? (
            <p style={{ color: '#6b7280', fontSize: 14 }}>No orders yet</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ textAlign: 'left', padding: '8px 0', color: '#6b7280', fontWeight: 500 }}>Order</th>
                  <th style={{ textAlign: 'left', padding: '8px 0', color: '#6b7280', fontWeight: 500 }}>Status</th>
                  <th style={{ textAlign: 'right', padding: '8px 0', color: '#6b7280', fontWeight: 500 }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {recentOrders.map(order => (
                  <tr key={order.id} style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }} onClick={() => navigate(`/orders/${order.id}`)}>
                    <td style={{ padding: '10px 0' }}>
                      <div style={{ fontWeight: 500 }}>{order.order_number}</div>
                      <div style={{ fontSize: 12, color: '#6b7280' }}>{order.shopper_email || 'No email'}</div>
                    </td>
                    <td style={{ padding: '10px 0' }}>
                      <span style={{
                        padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                        background: (statusColors[order.status] || '#9ca3af') + '20',
                        color: statusColors[order.status] || '#6b7280',
                      }}>{order.status}</span>
                    </td>
                    <td style={{ padding: '10px 0', textAlign: 'right', fontWeight: 600 }}>{formatPrice(order.total, order.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Product Stats */}
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Products</h3>
          {productStats && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280', fontSize: 13 }}>Total Products</span>
                <span style={{ fontWeight: 600 }}>{productStats.total}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280', fontSize: 13 }}>In Stock</span>
                <span style={{ fontWeight: 600, color: '#059669' }}>{productStats.in_stock}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#6b7280', fontSize: 13 }}>Out of Stock</span>
                <span style={{ fontWeight: 600, color: '#ef4444' }}>{productStats.out_of_stock}</span>
              </div>
              {productStats.price_range.avg && (
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280', fontSize: 13 }}>Avg Price</span>
                  <span style={{ fontWeight: 600 }}>{formatPrice(productStats.price_range.avg)}</span>
                </div>
              )}
              {productStats.out_of_stock > 0 && (
                <div style={{ marginTop: 8, padding: 10, background: '#fef2f2', borderRadius: 8, fontSize: 12, color: '#b91c1c' }}>
                  {productStats.out_of_stock} product{productStats.out_of_stock !== 1 ? 's' : ''} out of stock
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
