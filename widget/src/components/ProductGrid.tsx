import { ProductCard, Product } from './ProductCard'

interface ProductGridProps {
  products: Product[]
  onAddToCart: (productId: string, size?: string, color?: string) => Promise<void>
}

export function ProductGrid({ products, onAddToCart }: ProductGridProps) {
  if (!products.length) return null

  return (
    <div className="zk-product-grid">
      <div className="zk-product-grid__header">
        <span className="zk-product-grid__count">
          {products.length} product{products.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="zk-product-grid__scroll">
        {products.map(product => (
          <ProductCard
            key={product.id}
            product={product}
            onAddToCart={onAddToCart}
          />
        ))}
      </div>
    </div>
  )
}
