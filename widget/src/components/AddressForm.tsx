import React, { useState } from 'react'

interface AddressData {
  full_name: string
  line1: string
  line2: string
  city: string
  state: string
  postal_code: string
  country: string
  phone: string
}

export type PaymentMethod = 'cod' | 'online'

interface AddressFormProps {
  checkout: {
    items: Array<{ name: string; price: number; currency: string; quantity: number }>
    subtotal: number
    currency: string
    item_count: number
  }
  onSubmit: (billing: AddressData, shipping: AddressData | null, email: string, sameAsBilling: boolean, paymentMethod: PaymentMethod) => void
  isSubmitting: boolean
}

const COUNTRIES = [
  { code: 'US', name: 'United States' },
  { code: 'CA', name: 'Canada' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'AU', name: 'Australia' },
  { code: 'DE', name: 'Germany' },
  { code: 'FR', name: 'France' },
  { code: 'IN', name: 'India' },
  { code: 'NP', name: 'Nepal' },
  { code: 'JP', name: 'Japan' },
  { code: 'SG', name: 'Singapore' },
]

const emptyAddress: AddressData = {
  full_name: '', line1: '', line2: '', city: '', state: '', postal_code: '', country: 'US', phone: '',
}

export function AddressForm({ checkout, onSubmit, isSubmitting }: AddressFormProps) {
  const [email, setEmail] = useState('')
  const [billing, setBilling] = useState<AddressData>({ ...emptyAddress })
  const [sameAsBilling, setSameAsBilling] = useState(true)
  const [shipping, setShipping] = useState<AddressData>({ ...emptyAddress })
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cod')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const formatPrice = (price: number, currency: string) => {
    const symbols: Record<string, string> = { USD: '$', EUR: '€', GBP: '£', NPR: 'Rs', INR: '₹' }
    const sym = symbols[currency] || currency + ' '
    return `${sym}${price.toLocaleString()}`
  }

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!email.includes('@')) errs.email = 'Valid email required'
    if (!billing.full_name.trim()) errs.full_name = 'Required'
    if (!billing.line1.trim()) errs.line1 = 'Required'
    if (!billing.city.trim()) errs.city = 'Required'
    if (!billing.state.trim()) errs.state = 'Required'
    if (!billing.postal_code.trim()) errs.postal_code = 'Required'
    if (!sameAsBilling) {
      if (!shipping.full_name.trim()) errs.ship_full_name = 'Required'
      if (!shipping.line1.trim()) errs.ship_line1 = 'Required'
      if (!shipping.city.trim()) errs.ship_city = 'Required'
      if (!shipping.state.trim()) errs.ship_state = 'Required'
      if (!shipping.postal_code.trim()) errs.ship_postal_code = 'Required'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return
    onSubmit(billing, sameAsBilling ? null : shipping, email, sameAsBilling, paymentMethod)
  }

  const updateBilling = (field: keyof AddressData, value: string) => {
    setBilling(prev => ({ ...prev, [field]: value }))
  }

  const updateShipping = (field: keyof AddressData, value: string) => {
    setShipping(prev => ({ ...prev, [field]: value }))
  }

  const renderField = (
    label: string,
    value: string,
    onChange: (v: string) => void,
    errorKey: string,
    required = true,
    type = 'text',
    half = false,
  ) => (
    <div className={`zk-address-form__field${half ? ' zk-address-form__field--half' : ''}`}>
      <label className="zk-address-form__label">
        {label}{required && <span className="zk-address-form__required">*</span>}
      </label>
      <input
        type={type}
        className={`zk-address-form__input${errors[errorKey] ? ' zk-address-form__input--error' : ''}`}
        value={value}
        onChange={e => onChange(e.target.value)}
      />
      {errors[errorKey] && <span className="zk-address-form__error">{errors[errorKey]}</span>}
    </div>
  )

  const renderCountrySelect = (value: string, onChange: (v: string) => void, half = false) => (
    <div className={`zk-address-form__field${half ? ' zk-address-form__field--half' : ''}`}>
      <label className="zk-address-form__label">Country<span className="zk-address-form__required">*</span></label>
      <select className="zk-address-form__input" value={value} onChange={e => onChange(e.target.value)}>
        {COUNTRIES.map(c => (
          <option key={c.code} value={c.code}>{c.name}</option>
        ))}
      </select>
    </div>
  )

  return (
    <div className="zk-address-form">
      <div className="zk-address-form__header">
        <span className="zk-address-form__title">Shipping & Billing</span>
        <span className="zk-address-form__summary">
          {checkout.item_count} item{checkout.item_count !== 1 ? 's' : ''} - {formatPrice(checkout.subtotal, checkout.currency)}
        </span>
      </div>
      <form onSubmit={handleSubmit}>
        {/* Email */}
        <div className="zk-address-form__section">
          {renderField('Email', email, setEmail, 'email', true, 'email')}
        </div>

        {/* Billing Address */}
        <div className="zk-address-form__section">
          <div className="zk-address-form__section-title">Billing Address</div>
          {renderField('Full Name', billing.full_name, v => updateBilling('full_name', v), 'full_name')}
          {renderField('Address Line 1', billing.line1, v => updateBilling('line1', v), 'line1')}
          {renderField('Address Line 2', billing.line2, v => updateBilling('line2', v), 'line2', false)}
          <div className="zk-address-form__row">
            {renderField('City', billing.city, v => updateBilling('city', v), 'city', true, 'text', true)}
            {renderField('State', billing.state, v => updateBilling('state', v), 'state', true, 'text', true)}
          </div>
          <div className="zk-address-form__row">
            {renderField('Postal Code', billing.postal_code, v => updateBilling('postal_code', v), 'postal_code', true, 'text', true)}
            {renderCountrySelect(billing.country, v => updateBilling('country', v), true)}
          </div>
          {renderField('Phone', billing.phone, v => updateBilling('phone', v), 'phone', false, 'tel')}
        </div>

        {/* Shipping toggle */}
        <div className="zk-address-form__section">
          <label className="zk-address-form__checkbox">
            <input
              type="checkbox"
              checked={sameAsBilling}
              onChange={e => setSameAsBilling(e.target.checked)}
            />
            <span>Shipping address same as billing</span>
          </label>
        </div>

        {/* Shipping Address (if different) */}
        {!sameAsBilling && (
          <div className="zk-address-form__section">
            <div className="zk-address-form__section-title">Shipping Address</div>
            {renderField('Full Name', shipping.full_name, v => updateShipping('full_name', v), 'ship_full_name')}
            {renderField('Address Line 1', shipping.line1, v => updateShipping('line1', v), 'ship_line1')}
            {renderField('Address Line 2', shipping.line2, v => updateShipping('line2', v), 'ship_line2', false)}
            <div className="zk-address-form__row">
              {renderField('City', shipping.city, v => updateShipping('city', v), 'ship_city', true, 'text', true)}
              {renderField('State', shipping.state, v => updateShipping('state', v), 'ship_state', true, 'text', true)}
            </div>
            <div className="zk-address-form__row">
              {renderField('Postal Code', shipping.postal_code, v => updateShipping('postal_code', v), 'ship_postal_code', true, 'text', true)}
              {renderCountrySelect(shipping.country, v => updateShipping('country', v), true)}
            </div>
            {renderField('Phone', shipping.phone, v => updateShipping('phone', v), 'ship_phone', false, 'tel')}
          </div>
        )}

        {/* Payment Method */}
        <div className="zk-address-form__section">
          <div className="zk-address-form__section-title">Payment Method</div>
          <div className="zk-address-form__payment-options">
            <label
              className={`zk-address-form__payment-option${paymentMethod === 'cod' ? ' zk-address-form__payment-option--active' : ''}`}
            >
              <input
                type="radio"
                name="payment_method"
                value="cod"
                checked={paymentMethod === 'cod'}
                onChange={() => setPaymentMethod('cod')}
              />
              <div className="zk-address-form__payment-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <rect x="1" y="4" width="22" height="16" rx="2" />
                  <path d="M1 10h22" />
                </svg>
              </div>
              <div>
                <div className="zk-address-form__payment-label">Cash on Delivery</div>
                <div className="zk-address-form__payment-desc">Pay when you receive your order</div>
              </div>
            </label>
            <label
              className={`zk-address-form__payment-option${paymentMethod === 'online' ? ' zk-address-form__payment-option--active' : ''}`}
            >
              <input
                type="radio"
                name="payment_method"
                value="online"
                checked={paymentMethod === 'online'}
                onChange={() => setPaymentMethod('online')}
              />
              <div className="zk-address-form__payment-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <rect x="1" y="4" width="22" height="16" rx="2" />
                  <circle cx="12" cy="12" r="3" />
                  <path d="M1 10h3M20 10h3" />
                </svg>
              </div>
              <div>
                <div className="zk-address-form__payment-label">Online Payment</div>
                <div className="zk-address-form__payment-desc">Pay securely with card via Stripe</div>
              </div>
            </label>
          </div>
        </div>

        <button
          type="submit"
          className="zk-address-form__submit"
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Processing...' : paymentMethod === 'cod' ? 'Place Order (COD)' : 'Continue to Payment'}
        </button>
      </form>
    </div>
  )
}
