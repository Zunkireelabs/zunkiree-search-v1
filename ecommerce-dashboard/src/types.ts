export interface Order {
  id: string
  order_number: string
  session_id: string
  shopper_email: string | null
  items: OrderItem[]
  subtotal: number
  tax: number
  shipping_cost: number
  total: number
  currency: string
  status: string
  payment_status: string
  payment_intent_id: string | null
  payment_method: string | null
  billing_address: Address | null
  shipping_address: Address | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export interface OrderItem {
  product_id?: string
  name: string
  price: number
  currency: string
  quantity: number
  size?: string
  color?: string
  image?: string
  url?: string
}

export interface Address {
  full_name: string
  line1: string
  line2?: string
  city: string
  state: string
  postal_code: string
  country: string
  phone?: string
}

export interface Product {
  id: string
  name: string
  description: string | null
  sku: string | null
  brand: string | null
  category: string | null
  price: number | null
  currency: string | null
  original_price: number | null
  images: string[]
  url: string | null
  sizes: string[]
  colors: string[]
  in_stock: boolean
  created_at: string | null
  updated_at: string | null
}

export interface AnalyticsOverview {
  total_revenue: number
  total_orders: number
  paid_orders: number
  pending_orders: number
  avg_order_value: number
}

export interface RevenueDataPoint {
  date: string
  revenue: number
  orders: number
}

export interface TopProduct {
  name: string
  revenue: number
  units_sold: number
}

export interface ProductStats {
  total: number
  out_of_stock: number
  in_stock: number
  price_range: {
    min: number | null
    max: number | null
    avg: number | null
  }
  categories: Record<string, number>
}
