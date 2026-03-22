import React, { useEffect, useState } from 'react'
import { getCustomers } from '../api'

interface Customer {
  email: string
  total_orders: number
  total_spent: number
  currency: string
  last_order_date: string | null
}

export function Customers() {
  const [customers, setCustomers] = useState<Customer[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getCustomers(page)
      .then(res => {
        setCustomers(res.customers || [])
        setTotal(res.total || 0)
        setPages(res.pages || 1)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [page])

  const formatPrice = (amount: number, currency = 'NPR') => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs ', INR: '₹' }
    return `${symbols[currency] || currency + ' '}${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
  }

  const formatDate = (d: string | null) => d ? new Date(d).toLocaleDateString() : '-'

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Customers</h2>

      <div style={{ background: 'white', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
        ) : customers.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No customers found</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Email</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Total Orders</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Total Spent</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Last Order</th>
              </tr>
            </thead>
            <tbody>
              {customers.map(customer => (
                <tr key={customer.email} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '12px 16px', fontWeight: 500, color: '#374151' }}>{customer.email}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', color: '#6b7280' }}>{customer.total_orders}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600 }}>{formatPrice(customer.total_spent, customer.currency)}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', color: '#6b7280' }}>{formatDate(customer.last_order_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {pages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderTop: '1px solid #e5e7eb' }}>
            <span style={{ fontSize: 13, color: '#6b7280' }}>Showing {customers.length} of {total}</span>
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
