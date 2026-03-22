import React, { useEffect, useState } from 'react'
import { getAnalyticsOverview, getRevenueData, getTopProducts } from '../api'
import type { AnalyticsOverview, RevenueDataPoint, TopProduct } from '../types'

export function Analytics() {
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null)
  const [revenue, setRevenue] = useState<RevenueDataPoint[]>([])
  const [topProducts, setTopProducts] = useState<TopProduct[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      getAnalyticsOverview(),
      getRevenueData(30),
      getTopProducts(10),
    ]).then(([ov, rev, tp]) => {
      setOverview(ov)
      setRevenue(rev.data || [])
      setTopProducts(tp.products || [])
    }).catch(console.error).finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>

  const formatPrice = (amount: number, currency = 'NPR') => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs ', INR: '₹' }
    return `${symbols[currency] || currency + ' '}${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
  }
  const maxRevenue = Math.max(...revenue.map(d => d.revenue), 1)

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Analytics</h2>

      {/* KPIs */}
      {overview && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16, marginBottom: 32 }}>
          {[
            { label: 'Total Revenue', value: formatPrice(overview.total_revenue) },
            { label: 'Paid Orders', value: overview.paid_orders.toString() },
            { label: 'Avg Order Value', value: formatPrice(overview.avg_order_value) },
          ].map(kpi => (
            <div key={kpi.label} style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 6 }}>{kpi.label}</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{kpi.value}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* Revenue Chart (simple bar chart) */}
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Revenue (Last 30 Days)</h3>
          {revenue.length === 0 ? (
            <p style={{ color: '#6b7280', fontSize: 14 }}>No revenue data yet</p>
          ) : (
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 200 }}>
              {revenue.map(d => (
                <div
                  key={d.date}
                  title={`${d.date}: ${formatPrice(d.revenue)} (${d.orders} orders)`}
                  style={{
                    flex: 1,
                    height: `${(d.revenue / maxRevenue) * 100}%`,
                    minHeight: 2,
                    background: '#3b82f6',
                    borderRadius: '2px 2px 0 0',
                    cursor: 'pointer',
                    transition: 'opacity 150ms',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.opacity = '0.7')}
                  onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
                />
              ))}
            </div>
          )}
        </div>

        {/* Top Products */}
        <div style={{ background: 'white', borderRadius: 12, padding: 20, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Top Products by Revenue</h3>
          {topProducts.length === 0 ? (
            <p style={{ color: '#6b7280', fontSize: 14 }}>No product data yet</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {topProducts.map((p, idx) => {
                const maxRev = topProducts[0]?.revenue || 1
                return (
                  <div key={idx}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                      <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60%' }}>{p.name}</span>
                      <span style={{ color: '#6b7280' }}>{formatPrice(p.revenue)} ({p.units_sold} sold)</span>
                    </div>
                    <div style={{ height: 6, background: '#f3f4f6', borderRadius: 3 }}>
                      <div style={{ height: '100%', width: `${(p.revenue / maxRev) * 100}%`, background: '#3b82f6', borderRadius: 3 }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
