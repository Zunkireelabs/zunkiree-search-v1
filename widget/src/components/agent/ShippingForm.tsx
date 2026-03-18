import React, { useState } from 'react'

export interface ShippingInfo {
  fullName: string
  phone: string
  email: string
  address: string
  city: string
  state: string
}

interface Props {
  onSubmit: (info: ShippingInfo) => void
  isLoading: boolean
}

export function ShippingForm({ onSubmit, isLoading }: Props) {
  const [form, setForm] = useState<ShippingInfo>({
    fullName: '', phone: '', email: '', address: '', city: '', state: '',
  })
  const [errors, setErrors] = useState<Partial<ShippingInfo>>({})

  const validate = (): boolean => {
    const e: Partial<ShippingInfo> = {}
    if (!form.fullName.trim()) e.fullName = 'Required'
    if (!form.phone.trim()) e.phone = 'Required'
    else if (!/^[0-9+\-\s]{7,15}$/.test(form.phone)) e.phone = 'Invalid phone'
    if (!form.email.trim()) e.email = 'Required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) e.email = 'Invalid email'
    if (!form.address.trim()) e.address = 'Required'
    if (!form.city.trim()) e.city = 'Required'
    if (!form.state.trim()) e.state = 'Required'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = (ev: React.FormEvent) => {
    ev.preventDefault()
    if (validate()) onSubmit(form)
  }

  const handleChange = (field: keyof ShippingInfo) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    setForm(prev => ({ ...prev, [field]: e.target.value }))
    if (errors[field]) setErrors(prev => ({ ...prev, [field]: undefined }))
  }

  const NEPAL_STATES = [
    'Koshi', 'Madhesh', 'Bagmati', 'Gandaki', 'Lumbini', 'Karnali', 'Sudurpashchim',
  ]

  return (
    <form className="zk-shipping" onSubmit={handleSubmit}>
      <div className="zk-shipping__title">Shipping Information</div>

      <div className="zk-shipping__field">
        <input placeholder="Full Name *" value={form.fullName} onChange={handleChange('fullName')} className={errors.fullName ? 'zk-shipping__input--error' : ''} />
        {errors.fullName && <span className="zk-shipping__error">{errors.fullName}</span>}
      </div>

      <div className="zk-shipping__row">
        <div className="zk-shipping__field">
          <input placeholder="Phone *" value={form.phone} onChange={handleChange('phone')} type="tel" className={errors.phone ? 'zk-shipping__input--error' : ''} />
          {errors.phone && <span className="zk-shipping__error">{errors.phone}</span>}
        </div>
        <div className="zk-shipping__field">
          <input placeholder="Email *" value={form.email} onChange={handleChange('email')} type="email" className={errors.email ? 'zk-shipping__input--error' : ''} />
          {errors.email && <span className="zk-shipping__error">{errors.email}</span>}
        </div>
      </div>

      <div className="zk-shipping__field">
        <input placeholder="Address *" value={form.address} onChange={handleChange('address')} className={errors.address ? 'zk-shipping__input--error' : ''} />
        {errors.address && <span className="zk-shipping__error">{errors.address}</span>}
      </div>

      <div className="zk-shipping__row">
        <div className="zk-shipping__field">
          <input placeholder="City *" value={form.city} onChange={handleChange('city')} className={errors.city ? 'zk-shipping__input--error' : ''} />
          {errors.city && <span className="zk-shipping__error">{errors.city}</span>}
        </div>
        <div className="zk-shipping__field">
          <select value={form.state} onChange={handleChange('state')} className={errors.state ? 'zk-shipping__input--error' : ''}>
            <option value="">State *</option>
            {NEPAL_STATES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          {errors.state && <span className="zk-shipping__error">{errors.state}</span>}
        </div>
      </div>

      <button type="submit" className="zk-shipping__submit" disabled={isLoading}>
        {isLoading ? 'Processing...' : 'Continue to Payment'}
      </button>
    </form>
  )
}
