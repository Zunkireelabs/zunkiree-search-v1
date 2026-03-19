import React, { useEffect, useState } from 'react'
import { getSettings, updateSettings } from '../api'

export function Settings() {
  const [settings, setSettingsState] = useState<Record<string, any> | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [stripeAccountId, setStripeAccountId] = useState('')
  const [paymentEnabled, setPaymentEnabled] = useState(false)
  const [checkoutMode, setCheckoutMode] = useState('redirect')
  const [message, setMessage] = useState('')

  useEffect(() => {
    getSettings()
      .then(s => {
        setSettingsState(s)
        setStripeAccountId(s.stripe_account_id || '')
        setPaymentEnabled(s.payment_enabled || false)
        setCheckoutMode(s.checkout_mode || 'redirect')
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    try {
      const res = await updateSettings({
        stripe_account_id: stripeAccountId || null,
        payment_enabled: paymentEnabled,
        checkout_mode: checkoutMode,
      })
      setSettingsState(res)
      setMessage('Settings saved successfully')
      setTimeout(() => setMessage(''), 3000)
    } catch (err) {
      setMessage('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Settings</h2>

      <div style={{ maxWidth: 600, background: 'white', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
        {/* Stripe */}
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Stripe Integration</h3>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Stripe Account ID</label>
            <input
              type="text"
              value={stripeAccountId}
              onChange={e => setStripeAccountId(e.target.value)}
              placeholder="acct_..."
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, boxSizing: 'border-box' }}
            />
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>Your Stripe Connect account ID for receiving payments</p>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={paymentEnabled} onChange={e => setPaymentEnabled(e.target.checked)} style={{ width: 16, height: 16 }} />
            <span style={{ fontSize: 14 }}>Enable payment processing</span>
          </label>
        </div>

        {/* Checkout Mode */}
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Checkout Mode</h3>
          <div style={{ display: 'flex', gap: 12 }}>
            {[
              { value: 'redirect', label: 'Redirect', desc: 'Redirect to product page for checkout' },
              { value: 'in-app', label: 'In-App', desc: 'Checkout with Stripe directly in the chat' },
            ].map(opt => (
              <label
                key={opt.value}
                style={{
                  flex: 1, padding: 16, border: `2px solid ${checkoutMode === opt.value ? '#2563eb' : '#e5e7eb'}`,
                  borderRadius: 10, cursor: 'pointer', background: checkoutMode === opt.value ? '#eff6ff' : 'white',
                }}
              >
                <input type="radio" name="checkout_mode" value={opt.value} checked={checkoutMode === opt.value} onChange={() => setCheckoutMode(opt.value)} style={{ display: 'none' }} />
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{opt.label}</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{opt.desc}</div>
              </label>
            ))}
          </div>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '10px 24px', background: '#2563eb', color: 'white', border: 'none', borderRadius: 8,
            fontSize: 14, fontWeight: 500, cursor: 'pointer', opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>

        {message && (
          <div style={{ marginTop: 12, padding: '8px 12px', borderRadius: 6, fontSize: 13, background: message.includes('Failed') ? '#fef2f2' : '#f0fdf4', color: message.includes('Failed') ? '#b91c1c' : '#166534' }}>
            {message}
          </div>
        )}
      </div>
    </div>
  )
}
