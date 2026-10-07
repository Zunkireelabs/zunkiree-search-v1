import { useState } from 'react'
import type { BlockComponentProps, RangeSliderData } from './types'
import { fillPct, useCountUp } from './ui'

export function RangeSlider({ block, onAction, locked }: BlockComponentProps<RangeSliderData>) {
  const { field, min, max, step, unit } = block.data
  const [value, setValue] = useState(block.data.value)
  const shown = useCountUp(value, 180)
  const fmt = (n: number) => `${unit}${Math.round(n).toLocaleString()}`

  return (
    <div>
      <div className="zk-slider__value">{fmt(shown)}<span> / year</span></div>
      <input
        className="zk-range" type="range" min={min} max={max} step={step} value={value} disabled={locked}
        style={fillPct(value, min, max)} aria-label="Yearly budget"
        onChange={e => setValue(Number(e.target.value))}
      />
      <div className="zk-slider__scale"><span>{fmt(min)}</span><span>{fmt(max)}</span></div>
      {!locked && (
        <button
          type="button" className="zk-block__cta"
          onClick={() => onAction({
            blockId: block.block_id, blockType: block.type, actionId: 'set_value',
            values: { field, value }, displayText: `My budget is ${fmt(value)} per year`,
          })}
        >
          Set budget
        </button>
      )}
    </div>
  )
}
