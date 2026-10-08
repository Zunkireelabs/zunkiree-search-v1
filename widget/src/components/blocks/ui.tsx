import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

export function CheckIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  )
}

// Eases a displayed number towards its target (totals that count up/down as sliders move).
export function useCountUp(target: number, ms = 320): number {
  const [shown, setShown] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) { setShown(target); from.current = target; return }
    const start = performance.now()
    const begin = from.current
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      const eased = 1 - Math.pow(1 - t, 3)
      const v = begin + (target - begin) * eased
      setShown(v)
      from.current = v
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return shown
}

export const idx = (i: number) => ({ '--i': i }) as CSSProperties
export const fillPct = (value: number, min: number, max: number) => ({ '--fill': `${((value - min) / (max - min || 1)) * 100}%` }) as CSSProperties
