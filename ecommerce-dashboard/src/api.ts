const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

let apiKey = localStorage.getItem('zk_api_key') || ''

export function setApiKey(key: string) {
  apiKey = key
  localStorage.setItem('zk_api_key', key)
}

export function getApiKey(): string {
  return apiKey
}

async function request(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_URL}/api/v1/ecommerce${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      ...options.headers,
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('zk_api_key')
    window.location.reload()
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

// Orders
export const getOrders = (page = 1, status?: string) =>
  request(`/orders?page=${page}${status ? `&status=${status}` : ''}`)

export const getOrder = (id: string) => request(`/orders/${id}`)

export const updateOrderStatus = (id: string, status: string) =>
  request(`/orders/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status }),
  })

// Products
export const getProducts = (page = 1, search?: string) =>
  request(`/products?page=${page}${search ? `&search=${search}` : ''}`)

export const createProduct = (data: Record<string, unknown>) =>
  request('/products', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const updateProduct = (id: string, data: Record<string, unknown>) =>
  request(`/products/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })

export const deleteProduct = (id: string) =>
  request(`/products/${id}`, { method: 'DELETE' })

export const getProductStats = () => request('/products/stats')

// Analytics
export const getAnalyticsOverview = () => request('/analytics/overview')
export const getRevenueData = (days = 30) => request(`/analytics/revenue?days=${days}`)
export const getTopProducts = (limit = 10) => request(`/analytics/top-products?limit=${limit}`)

// Customers
export const getCustomers = (page = 1) => request(`/customers?page=${page}`)

// Settings
export const getSettings = () => request('/settings')
export const updateSettings = (data: Record<string, unknown>) =>
  request('/settings', { method: 'PUT', body: JSON.stringify(data) })
