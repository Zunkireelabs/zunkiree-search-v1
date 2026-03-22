import React, { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Overview } from './components/Overview'
import { OrdersTable } from './components/OrdersTable'
import { OrderDetail } from './components/OrderDetail'
import { ProductsTable } from './components/ProductsTable'
import { Analytics } from './components/Analytics'
import { Settings } from './components/Settings'
import { Customers } from './components/Customers'
import { getApiKey, setApiKey } from './api'

function LoginPage() {
  const [key, setKey] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (key.trim()) {
      setApiKey(key.trim())
      window.location.reload()
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: '#f9fafb' }}>
      <form onSubmit={handleSubmit} style={{ background: 'white', padding: 32, borderRadius: 12, boxShadow: '0 4px 16px rgba(0,0,0,0.08)', width: 400 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 8 }}>Zunkiree Ecommerce</h1>
        <p style={{ fontSize: 14, color: '#6b7280', marginBottom: 24 }}>Enter your API key to access the dashboard</p>
        <input
          type="password"
          value={key}
          onChange={e => setKey(e.target.value)}
          placeholder="Your API key"
          style={{ width: '100%', padding: '10px 14px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, marginBottom: 16, boxSizing: 'border-box' }}
        />
        <button type="submit" style={{ width: '100%', padding: 10, background: '#2563eb', color: 'white', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
          Sign In
        </button>
      </form>
    </div>
  )
}

export function App() {
  if (!getApiKey()) {
    return <LoginPage />
  }

  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/orders" element={<OrdersTable />} />
          <Route path="/orders/:id" element={<OrderDetail />} />
          <Route path="/products" element={<ProductsTable />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
