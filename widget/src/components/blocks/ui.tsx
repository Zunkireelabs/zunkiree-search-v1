import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

export function CheckIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  )
}

// Animated score ring (matches and eligibility).
export function Ring({ value, size = 56, stroke = 6 }: { value: number; size?: number; stroke?: number }) {
  const r = (size - stroke) / 2
  const len = 2 * Math.PI * r
  const style = { '--len': len, '--off': len * (1 - value / 100) } as CSSProperties
  return (
    <div className="zk-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={style} aria-hidden="true">
        <circle className="zk-ring__bg" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} />
        <circle className="zk-ring__fg" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} />
      </svg>
      <span className="zk-ring__num" style={{ fontSize: size * 0.3 }} aria-label={`${value} percent`}>{value}<small>%</small></span>
    </div>
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
