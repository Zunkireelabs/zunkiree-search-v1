import React, { useEffect, useState } from 'react'
import { getProducts, updateProduct } from '../api'
import type { Product } from '../types'

export function ProductsTable() {
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editPrice, setEditPrice] = useState('')

  useEffect(() => {
    setLoading(true)
    getProducts(page, search || undefined)
      .then(res => {
        setProducts(res.products || [])
        setTotal(res.total || 0)
        setPages(res.pages || 1)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [page, search])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setPage(1)
  }

  const handleToggleStock = async (product: Product) => {
    try {
      const res = await updateProduct(product.id, { in_stock: !product.in_stock })
      setProducts(prev => prev.map(p => p.id === product.id ? res.product : p))
    } catch (err) {
      console.error(err)
    }
  }

  const handlePriceSave = async (productId: string) => {
    const price = parseFloat(editPrice)
    if (isNaN(price) || price < 0) return
    try {
      const res = await updateProduct(productId, { price })
      setProducts(prev => prev.map(p => p.id === productId ? res.product : p))
      setEditingId(null)
    } catch (err) {
      console.error(err)
    }
  }

  const formatPrice = (price: number | null, currency: string | null) => {
    if (price === null) return '-'
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency || 'USD'] || (currency || '') + ' '
    return `${sym}${price.toLocaleString()}`
  }

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 24 }}>Products</h2>

      <form onSubmit={handleSearch} style={{ marginBottom: 20, display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          placeholder="Search products..."
          style={{ flex: 1, maxWidth: 300, padding: '8px 14px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13 }}
        />
        <button type="submit" style={{ padding: '8px 16px', background: '#2563eb', color: 'white', border: 'none', borderRadius: 8, fontSize: 13, cursor: 'pointer' }}>Search</button>
        {search && (
          <button type="button" onClick={() => { setSearch(''); setSearchInput(''); setPage(1) }} style={{ padding: '8px 16px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, cursor: 'pointer', background: 'white' }}>Clear</button>
        )}
      </form>

      <div style={{ background: 'white', borderRadius: 12, boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
        ) : products.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No products found</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Product</th>
                <th style={{ textAlign: 'left', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Category</th>
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Price</th>
                <th style={{ textAlign: 'center', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Stock</th>
              </tr>
            </thead>
            <tbody>
              {products.map(product => (
                <tr key={product.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      {product.images[0] && (
                        <img src={product.images[0]} alt="" style={{ width: 36, height: 36, borderRadius: 6, objectFit: 'cover' }} />
                      )}
                      <div>
                        <div style={{ fontWeight: 500 }}>{product.name}</div>
                        {product.sku && <div style={{ fontSize: 11, color: '#9ca3af' }}>SKU: {product.sku}</div>}
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', color: '#6b7280' }}>{product.category || '-'}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    {editingId === product.id ? (
                      <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                        <input
                          type="number"
                          value={editPrice}
                          onChange={e => setEditPrice(e.target.value)}
                          style={{ width: 80, padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}
                          autoFocus
                          onKeyDown={e => e.key === 'Enter' && handlePriceSave(product.id)}
                        />
                        <button onClick={() => handlePriceSave(product.id)} style={{ padding: '4px 8px', background: '#2563eb', color: 'white', border: 'none', borderRadius: 4, fontSize: 11, cursor: 'pointer' }}>Save</button>
                        <button onClick={() => setEditingId(null)} style={{ padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 11, cursor: 'pointer', background: 'white' }}>X</button>
                      </div>
                    ) : (
                      <span
                        style={{ cursor: 'pointer', fontWeight: 600 }}
                        onClick={() => { setEditingId(product.id); setEditPrice(String(product.price || 0)) }}
                        title="Click to edit price"
                      >
                        {formatPrice(product.price, product.currency)}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                    <button
                      onClick={() => handleToggleStock(product)}
                      style={{
                        padding: '4px 12px', borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                        border: 'none',
                        background: product.in_stock ? '#dcfce7' : '#f3f4f6',
                        color: product.in_stock ? '#166534' : '#6b7280',
                      }}
                    >
                      {product.in_stock ? 'In Stock' : 'Out of Stock'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {pages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderTop: '1px solid #e5e7eb' }}>
            <span style={{ fontSize: 13, color: '#6b7280' }}>Showing {products.length} of {total}</span>
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
