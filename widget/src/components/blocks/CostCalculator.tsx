import { useState } from 'react'
import type { BlockComponentProps, CostCalculatorData } from './types'
import { fillPct, useCountUp } from './ui'

// Live calculator: drag any part and the bar and total move. The sliders always work;
// only "use as my budget" talks to the chat, so it hides on older (locked) blocks.
export function CostCalculator({ block, onAction, locked }: BlockComponentProps<CostCalculatorData>) {
  const { currency, parts, note } = block.data
  const [values, setValues] = useState<Record<string, number>>(() => Object.fromEntries(parts.map(p => [p.id, p.value])))
  const total = parts.reduce((sum, p) => sum + values[p.id], 0)
  const shown = useCountUp(total)
  const fmt = (n: number) => `${currency}${Math.round(n).toLocaleString()}`
  const shades = ['var(--zk-accent)', 'color-mix(in srgb, var(--zk-accent) 45%, #fff)', 'color-mix(in srgb, var(--zk-accent) 22%, #fff)']

  return (
    <div>
      <div className="zk-calc__bar" aria-hidden="true">
        {parts.map(p => <div key={p.id} style={{ width: `${total ? (values[p.id] / total) * 100 : 0}%` }} />)}
      </div>
      {parts.map((p, i) => (
        <div key={p.id} className="zk-calc__part">
          <div className="zk-calc__row">
            <span><i className="zk-calc__swatch" style={{ background: shades[i % shades.length] }} />{p.label}</span>
            <strong>{fmt(values[p.id])}</strong>
          </div>
          <input
            className="zk-range" type="range" min={p.min} max={p.max} step={p.step} value={values[p.id]}
            style={fillPct(values[p.id], p.min, p.max)} aria-label={p.label}
            onChange={e => setValues(v => ({ ...v, [p.id]: Number(e.target.value) }))}
          />
          <div className="zk-slider__scale"><span>{fmt(p.min)}</span><span>{fmt(p.max)}</span></div>
        </div>
      ))}
      <div className="zk-calc__total"><span>Estimated per year</span><strong>{fmt(shown)}</strong></div>
      {note && <div className="zk-calc__note">{note}</div>}
      {!locked && (
        <button
          type="button" className="zk-block__cta"
          onClick={() => onAction({
            blockId: block.block_id, blockType: block.type, actionId: 'set_value',
            values: { field: 'budget', value: Math.round(total) }, displayText: `My budget is ${fmt(total)} per year`,
          })}
        >
          Use {fmt(total)} as my budget
        </button>
      )}
    </div>
  )
}
