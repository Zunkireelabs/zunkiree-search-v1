import React, { useEffect, useState } from 'react'
import { getSettings, updateSettings } from '../api'

export function Settings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [paymentEnabled, setPaymentEnabled] = useState(false)
  const [checkoutMode, setCheckoutMode] = useState('redirect')
  const [message, setMessage] = useState('')

  useEffect(() => {
    getSettings()
      .then(s => {
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
      await updateSettings({
        payment_enabled: paymentEnabled,
        checkout_mode: checkoutMode,
      })
      setMessage('Settings saved successfully')
      setTimeout(() => setMessage(''), 3000)
    } catch {
      setMessage('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Settings</h2>

      <div style={{ maxWidth: 600, display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Payment Gateways */}
        <div style={{ background: 'white', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Payment Gateways</h3>

          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <div style={{
              flex: 1, padding: 16, borderRadius: 10, border: '1.5px solid #60BB46',
              background: '#f0fdf4', display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <rect width="24" height="24" rx="6" fill="#60BB46"/>
                <text x="12" y="16" textAnchor="middle" fill="white" fontSize="10" fontWeight="700" fontFamily="sans-serif">eS</text>
              </svg>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#166534' }}>eSewa</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>Sandbox mode active</div>
              </div>
              <div style={{ marginLeft: 'auto', padding: '3px 10px', borderRadius: 20, background: '#dcfce7', color: '#166534', fontSize: 11, fontWeight: 600 }}>Active</div>
            </div>

            <div style={{
              flex: 1, padding: 16, borderRadius: 10, border: '1.5px solid #5C2D91',
              background: '#faf5ff', display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <rect width="24" height="24" rx="6" fill="#5C2D91"/>
                <text x="12" y="16" textAnchor="middle" fill="white" fontSize="10" fontWeight="700" fontFamily="sans-serif">K</text>
              </svg>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#5C2D91' }}>Khalti</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>Sandbox mode active</div>
              </div>
              <div style={{ marginLeft: 'auto', padding: '3px 10px', borderRadius: 20, background: '#f3e8ff', color: '#5C2D91', fontSize: 11, fontWeight: 600 }}>Active</div>
            </div>
          </div>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={paymentEnabled} onChange={e => setPaymentEnabled(e.target.checked)} style={{ width: 16, height: 16 }} />
            <span style={{ fontSize: 14 }}>Enable online payment at checkout</span>
          </label>
          <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4, marginLeft: 24 }}>
            When enabled, customers can pay via eSewa or Khalti. Otherwise only Cash on Delivery is available.
          </p>
        </div>

        {/* Checkout Mode */}
        <div style={{ background: 'white', borderRadius: 12, padding: 24, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Checkout Mode</h3>
          <div style={{ display: 'flex', gap: 12 }}>
            {[
              { value: 'redirect', label: 'Redirect', desc: 'Redirect to your product page for checkout' },
              { value: 'in-app', label: 'In-App', desc: 'Complete checkout directly in the chat widget' },
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

        {/* Save */}
        <div>
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
    </div>
  )
}
