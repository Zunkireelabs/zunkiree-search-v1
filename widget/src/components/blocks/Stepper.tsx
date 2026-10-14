import { useState } from 'react'
import type { BlockComponentProps, StepperData } from './types'
import { CheckIcon, idx } from './ui'

// Interactive on its own: expand a step, tick steps off, watch the line fill.
export function Stepper({ block }: BlockComponentProps<StepperData>) {
  const { steps } = block.data
  const [open, setOpen] = useState<number | null>(0)
  const [done, setDone] = useState<Set<number>>(new Set())

  const toggleDone = (i: number) => setDone(prev => {
    const next = new Set(prev)
    if (next.has(i)) { next.delete(i) } else {
      next.add(i)
      // finishing a step moves you to the next one
      if (i + 1 < steps.length && !next.has(i + 1)) setOpen(i + 1)
    }
    return next
  })

  const allDone = done.size === steps.length

  return (
    <div>
      <div className="zk-progress"><div style={{ width: `${(done.size / steps.length) * 100}%` }} /></div>
      <div className="zk-progress__label">{done.size} of {steps.length} done</div>
      <ol className="zk-stepper__list">
        {steps.map((step, i) => {
          const isDone = done.has(i)
          const isOpen = open === i
          return (
            <li key={i} style={idx(i)} className={`zk-step${isDone ? ' zk-step--done' : ''}${isOpen ? ' zk-step--open' : ''}`}>
              <button type="button" className="zk-step__head" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : i)}>
                <span className="zk-step__num">{isDone ? <CheckIcon size={14} /> : i + 1}</span>
                <span className="zk-step__title">{step.title}</span>
                <span className="zk-step__chevron">▸</span>
              </button>
              <div className="zk-step__panel"><div>
                <div className="zk-step__body">
                  {step.detail && <p>{step.detail}</p>}
                  <button type="button" className="zk-step__done" tabIndex={isOpen ? 0 : -1} onClick={() => toggleDone(i)}>
                    {isDone ? 'Mark as not done' : 'Mark as done'}
                  </button>
                </div>
              </div></div>
            </li>
          )
        })}
      </ol>
      {allDone && <div className="zk-celebrate">🎉 All steps done. You're ready for the next move.</div>}
    </div>
  )
}
