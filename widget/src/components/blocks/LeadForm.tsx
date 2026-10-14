import { useState } from 'react'
import type { BlockComponentProps, LeadFormData } from './types'

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const PHONE = /^[+\d][\d\s\-()]{6,}$/

function problem(type: string, value: string): string | null {
  if (!value.trim()) return null
  if (type === 'email' && !EMAIL.test(value.trim())) return 'Enter a valid email address'
  if (type === 'tel' && !PHONE.test(value.trim())) return 'Enter a valid phone number'
  return null
}

export function LeadForm({ block, onAction, locked }: BlockComponentProps<LeadFormData>) {
  const fields = block.data.fields
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(fields.map(f => [f.id, f.value || ''])))
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const errors = Object.fromEntries(fields.map(f => [f.id, problem(f.type, values[f.id])]))
  const valid = fields.every(f => (!f.required || values[f.id]?.trim()) && !errors[f.id])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (locked || !valid) return
    onAction({
      blockId: block.block_id, blockType: block.type, actionId: 'submit',
      values, displayText: 'Please have a counselor contact me',
    })
  }

  return (
    <form className="zk-leadform" onSubmit={submit} noValidate>
      {fields.map(f => {
        const err = touched[f.id] ? errors[f.id] : null
        return (
          <label key={f.id} className={`zk-leadform__field${err ? ' zk-leadform__field--bad' : ''}`}>
            <span>{f.label}{f.required && ' *'}</span>
            <input
              type={f.type} value={values[f.id]} disabled={locked} required={f.required} autoComplete={f.type === 'email' ? 'email' : f.type === 'tel' ? 'tel' : 'name'}
              aria-invalid={!!err}
              onBlur={() => setTouched(t => ({ ...t, [f.id]: true }))}
              onChange={e => setValues(v => ({ ...v, [f.id]: e.target.value }))}
            />
            {err && <span className="zk-leadform__err">{err}</span>}
          </label>
        )
      })}
      {!locked && <button type="submit" className="zk-block__cta" disabled={!valid}>Talk to a counselor</button>}
    </form>
  )
}
