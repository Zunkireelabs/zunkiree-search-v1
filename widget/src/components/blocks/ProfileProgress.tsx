export interface ProfileProgressData { filled: number; total: number }

// Slim "how far along am I" strip at the top of the conversation (education tenants).
export function ProfileProgress({ progress }: { progress: ProfileProgressData }) {
  const pct = Math.round((progress.filled / Math.max(progress.total, 1)) * 100)
  return (
    <div className="zk-progress-strip" role="progressbar" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.filled} aria-label="Your profile">
      <div className="zk-progress-strip__row"><span>Your profile</span><span>{progress.filled} of {progress.total}</span></div>
      <div className="zk-progress-strip__bar"><div style={{ width: `${pct}%` }} /></div>
    </div>
  )
}
