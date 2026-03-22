import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getOrders, updateOrderStatus } from '../api'
import type { Order } from '../types'

const STATUS_FILTERS = ['all', 'pending', 'payment_pending', 'paid', 'processing', 'shipped', 'delivered', 'cancelled']

const statusColors: Record<string, string> = {
  pending: '#fbbf24', payment_pending: '#f59e0b', paid: '#34d399',
  processing: '#60a5fa', shipped: '#818cf8', delivered: '#10b981',
  cancelled: '#f87171', refunded: '#fb923c',
}

const statusTransitions: Record<string, string[]> = {
  pending: ['processing', 'cancelled'],
  paid: ['processing', 'cancelled', 'refunded'],
  processing: ['shipped', 'cancelled'],
  shipped: ['delivered'],
}

export function OrdersTable() {
  const [orders, setOrders] = useState<Order[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [statusFilter, setStatusFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    getOrders(page, statusFilter === 'all' ? undefined : statusFilter)
      .then(res => {
        setOrders(res.orders || [])
        setTotal(res.total || 0)
        setPages(res.pages || 1)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [page, statusFilter])

  const formatPrice = (amount: number, currency = 'NPR') => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs ', INR: '₹' }
    return `${symbols[currency] || currency + ' '}${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
  }
  const formatDate = (d: string | null) => d ? new Date(d).toLocaleDateString() : '-'

  const handleStatusChange = async (order: Order, newStatus: string) => {
    if (!newStatus || newStatus === order.status) return
    setUpdatingId(order.id)
    try {
      const res = await updateOrderStatus(order.id, newStatus)
      setOrders(prev => prev.map(o => o.id === order.id ? { ...o, status: res.order?.status || newStatus } : o))
    } catch (err) {
      console.error(err)
      alert('Failed to update order status.')
    } finally {
      setUpdatingId(null)
    }
  }

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Orders</h2>

      {/* Status filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        {STATUS_FILTERS.map(s => (
          <button
            key={s}
            onClick={() => { setStatusFilter(s); setPage(1) }}
            style={{
              padding: '6px 14px', borderRadius: 6, fontSize: 13, cursor: 'pointer',
              border: '1px solid #e5e7eb', fontWeight: statusFilter === s ? 600 : 400,
              background: statusFilter === s ? '#2563eb' : 'white',
              color: statusFilter === s ? 'white' : '#374151',
            }}
          >
            {s === 'all' ? 'All' : s.replace('_', ' ')}
          </button>
        ))}
      </div>

      <div style={{ background: 'white', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
        ) : orders.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No orders found</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Order</th>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Customer</th>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Status</th>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Payment</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Total</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Date</th>
                <th style={{ textAlign: 'center', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Update Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map(order => {
                const transitions = statusTransitions[order.status] || []
                return (
                  <tr key={order.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td
                      style={{ padding: '12px 16px', fontWeight: 500, cursor: 'pointer', color: '#2563eb' }}
                      onClick={() => navigate(`/orders/${order.id}`)}
                    >
                      {order.order_number}
                    </td>
                    <td style={{ padding: '12px 16px', color: '#6b7280' }}>{order.shopper_email || '-'}</td>
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
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      {transitions.length > 0 ? (
                        <select
                          value=""
                          disabled={updatingId === order.id}
                          onChange={e => handleStatusChange(order, e.target.value)}
                          style={{
                            padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4,
                            fontSize: 11, cursor: updatingId === order.id ? 'default' : 'pointer',
                            background: 'white', color: '#374151',
                            opacity: updatingId === order.id ? 0.5 : 1,
                          }}
                        >
                          <option value="">
                            {updatingId === order.id ? 'Updating...' : 'Change...'}
                          </option>
                          {transitions.map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      ) : (
                        <span style={{ fontSize: 11, color: '#9ca3af' }}>--</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {pages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderTop: '1px solid #e5e7eb' }}>
            <span style={{ fontSize: 13, color: '#6b7280' }}>Showing {orders.length} of {total}</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={{ padding: '6px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, cursor: page <= 1 ? 'default' : 'pointer', opacity: page <= 1 ? 0.5 : 1, background: 'white' }}>Previous</button>
              <button disabled={page >= pages} onClick={() => setPage(p => p + 1)} style={{ padding: '6px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, cursor: page >= pages ? 'default' : 'pointer', opacity: page >= pages ? 0.5 : 1, background: 'white' }}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
