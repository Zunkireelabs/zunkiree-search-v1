// Shown while a component is being built, shaped like what's coming so the screen never feels frozen.
export function BlockSkeleton({ blockType, label }: { blockType: string; label: string }) {
  const rows = blockType === 'stepper' ? 'circle' : blockType === 'checklist' ? 'box' : 'bar'
  return (
    <div className="zk-skel" role="status" aria-live="polite" aria-busy="true" aria-label={label}>
      <div className="zk-skel__label"><span className="zk-skel__dot" />{label}</div>
      {[78, 92, 64].map((w, i) => (
        <div key={i} className="zk-skel__row">
          {rows === 'circle' && <span className="zk-skel__circle" />}
          {rows === 'box' && <span className="zk-skel__box" />}
          <span className="zk-skel__bar" style={{ maxWidth: `${w}%` }} />
        </div>
      ))}
    </div>
  )
}
