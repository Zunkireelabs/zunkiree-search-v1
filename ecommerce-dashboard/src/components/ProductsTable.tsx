import React, { useEffect, useState } from 'react'
import { getProducts, updateProduct, createProduct, deleteProduct } from '../api'
import type { Product } from '../types'

interface ProductFormData {
  name: string
  description: string
  price: string
  currency: string
  category: string
  sku: string
  brand: string
  images: string
  sizes: string
  colors: string
  in_stock: boolean
}

const emptyForm: ProductFormData = {
  name: '',
  description: '',
  price: '',
  currency: 'NPR',
  category: '',
  sku: '',
  brand: '',
  images: '',
  sizes: '',
  colors: '',
  in_stock: true,
}

function productToForm(product: Product): ProductFormData {
  return {
    name: product.name || '',
    description: product.description || '',
    price: product.price !== null ? String(product.price) : '',
    currency: product.currency || 'NPR',
    category: product.category || '',
    sku: product.sku || '',
    brand: product.brand || '',
    images: (product.images || []).join(', '),
    sizes: (product.sizes || []).join(', '),
    colors: (product.colors || []).join(', '),
    in_stock: product.in_stock,
  }
}

export function ProductsTable() {
  const [products, setProducts] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [loading, setLoading] = useState(true)

  // Modal state
  const [modalOpen, setModalOpen] = useState(false)
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [form, setForm] = useState<ProductFormData>(emptyForm)
  const [saving, setSaving] = useState(false)

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

  const formatPrice = (price: number | null, currency: string | null) => {
    if (price === null) return '-'
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs ', INR: '₹' }
    const sym = symbols[currency || 'USD'] || (currency || '') + ' '
    return `${sym}${price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
  }

  const openAddModal = () => {
    setEditingProduct(null)
    setForm(emptyForm)
    setModalOpen(true)
  }

  const openEditModal = (product: Product) => {
    setEditingProduct(product)
    setForm(productToForm(product))
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditingProduct(null)
    setForm(emptyForm)
  }

  const handleFormChange = (field: keyof ProductFormData, value: string | boolean) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  const handleSave = async () => {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        price: form.price ? parseFloat(form.price) : null,
        currency: form.currency || 'NPR',
        category: form.category.trim() || null,
        sku: form.sku.trim() || null,
        brand: form.brand.trim() || null,
        images: form.images ? form.images.split(',').map(s => s.trim()).filter(Boolean) : [],
        sizes: form.sizes ? form.sizes.split(',').map(s => s.trim()).filter(Boolean) : [],
        colors: form.colors ? form.colors.split(',').map(s => s.trim()).filter(Boolean) : [],
        in_stock: form.in_stock,
      }

      if (editingProduct) {
        const res = await updateProduct(editingProduct.id, payload)
        setProducts(prev => prev.map(p => p.id === editingProduct.id ? res.product : p))
      } else {
        await createProduct(payload)
        // Refresh list to show new product
        const res = await getProducts(page, search || undefined)
        setProducts(res.products || [])
        setTotal(res.total || 0)
        setPages(res.pages || 1)
      }
      closeModal()
    } catch (err) {
      console.error(err)
      alert('Failed to save product. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (product: Product) => {
    if (!window.confirm(`Are you sure you want to delete "${product.name}"?`)) return
    try {
      await deleteProduct(product.id)
      setProducts(prev => prev.filter(p => p.id !== product.id))
      setTotal(prev => prev - 1)
    } catch (err) {
      console.error(err)
      alert('Failed to delete product.')
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    border: '1px solid #d1d5db',
    borderRadius: 6,
    fontSize: 13,
    boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 500,
    color: '#374151',
    marginBottom: 4,
    display: 'block',
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h2 style={{ fontSize: 22, fontWeight: 600 }}>Products</h2>
        <button
          onClick={openAddModal}
          style={{ padding: '8px 16px', background: '#2563eb', color: 'white', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer' }}
        >
          + Add Product
        </button>
      </div>

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
                <th style={{ textAlign: 'right', padding: '10px 16px', color: '#6b7280', fontWeight: 500 }}>Actions</th>
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
                  <td style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600 }}>
                    {formatPrice(product.price, product.currency)}
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
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button
                        onClick={() => openEditModal(product)}
                        style={{ padding: '4px 10px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 11, cursor: 'pointer', background: 'white', color: '#374151' }}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(product)}
                        style={{ padding: '4px 10px', border: '1px solid #fca5a5', borderRadius: 4, fontSize: 11, cursor: 'pointer', background: '#fef2f2', color: '#dc2626' }}
                      >
                        Delete
                      </button>
                    </div>
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

      {/* Product Form Modal */}
      {modalOpen && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={(e) => { if (e.target === e.currentTarget) closeModal() }}
        >
          <div style={{
            background: 'white', borderRadius: 12, padding: 28, width: 520, maxHeight: '85vh', overflow: 'auto',
            boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ fontSize: 18, fontWeight: 600, color: '#374151' }}>
                {editingProduct ? 'Edit Product' : 'Add Product'}
              </h3>
              <button onClick={closeModal} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#6b7280', padding: '4px 8px' }}>
                X
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={labelStyle}>Name *</label>
                <input style={inputStyle} value={form.name} onChange={e => handleFormChange('name', e.target.value)} placeholder="Product name" />
              </div>

              <div>
                <label style={labelStyle}>Description</label>
                <textarea
                  style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
                  value={form.description}
                  onChange={e => handleFormChange('description', e.target.value)}
                  placeholder="Product description"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Price</label>
                  <input style={inputStyle} type="number" step="0.01" value={form.price} onChange={e => handleFormChange('price', e.target.value)} placeholder="0.00" />
                </div>
                <div>
                  <label style={labelStyle}>Currency</label>
                  <select style={inputStyle} value={form.currency} onChange={e => handleFormChange('currency', e.target.value)}>
                    <option value="NPR">NPR</option>
                    <option value="USD">USD</option>
                    <option value="EUR">EUR</option>
                    <option value="GBP">GBP</option>
                    <option value="INR">INR</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Category</label>
                  <input style={inputStyle} value={form.category} onChange={e => handleFormChange('category', e.target.value)} placeholder="e.g. Clothing" />
                </div>
                <div>
                  <label style={labelStyle}>SKU</label>
                  <input style={inputStyle} value={form.sku} onChange={e => handleFormChange('sku', e.target.value)} placeholder="e.g. SKU-001" />
                </div>
              </div>

              <div>
                <label style={labelStyle}>Brand</label>
                <input style={inputStyle} value={form.brand} onChange={e => handleFormChange('brand', e.target.value)} placeholder="Brand name" />
              </div>

              <div>
                <label style={labelStyle}>Images (comma-separated URLs)</label>
                <input style={inputStyle} value={form.images} onChange={e => handleFormChange('images', e.target.value)} placeholder="https://example.com/img1.jpg, https://example.com/img2.jpg" />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Sizes (comma-separated)</label>
                  <input style={inputStyle} value={form.sizes} onChange={e => handleFormChange('sizes', e.target.value)} placeholder="S, M, L, XL" />
                </div>
                <div>
                  <label style={labelStyle}>Colors (comma-separated)</label>
                  <input style={inputStyle} value={form.colors} onChange={e => handleFormChange('colors', e.target.value)} placeholder="Red, Blue, Black" />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <label style={{ ...labelStyle, marginBottom: 0 }}>In Stock</label>
                <button
                  type="button"
                  onClick={() => handleFormChange('in_stock', !form.in_stock)}
                  style={{
                    width: 40, height: 22, borderRadius: 11, border: 'none', cursor: 'pointer',
                    background: form.in_stock ? '#2563eb' : '#d1d5db',
                    position: 'relative', transition: 'background 150ms',
                  }}
                >
                  <span style={{
                    position: 'absolute', top: 2, left: form.in_stock ? 20 : 2,
                    width: 18, height: 18, borderRadius: '50%', background: 'white',
                    transition: 'left 150ms', boxShadow: '0 1px 2px rgba(0,0,0,0.15)',
                  }} />
                </button>
                <span style={{ fontSize: 12, color: '#6b7280' }}>{form.in_stock ? 'Yes' : 'No'}</span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
              <button
                onClick={closeModal}
                style={{ padding: '8px 16px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, cursor: 'pointer', background: 'white', color: '#374151' }}
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name.trim()}
                style={{
                  padding: '8px 20px', background: saving ? '#93c5fd' : '#2563eb', color: 'white',
                  border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: saving ? 'default' : 'pointer',
                }}
              >
                {saving ? 'Saving...' : (editingProduct ? 'Save Changes' : 'Create Product')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
