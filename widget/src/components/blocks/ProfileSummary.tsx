import type { BlockComponentProps, ProfileSummaryData } from './types'

export function ProfileSummary({ block, onAction, locked }: BlockComponentProps<ProfileSummaryData>) {
  const { rows, missing } = block.data
  return (
    <div className="zk-info">
      <dl className="zk-info__rows">
        {rows.map((r, i) => (
          <div key={i} className="zk-info__row"><dt>{r.label}</dt><dd>{r.value}</dd></div>
        ))}
      </dl>
      {missing && missing.length > 0 && (
        <div className="zk-info__missing">Still helpful to know: {missing.join(', ')}</div>
      )}
      {!locked && block.actions?.map(a => (
        <button
          key={a.id}
          type="button"
          className="zk-block__cta zk-block__cta--ghost"
          onClick={() => onAction({
            blockId: block.block_id, blockType: block.type, actionId: a.id,
            values: {}, displayText: a.label,
          })}
        >
          {a.label}
        </button>
      ))}
    </div>
  )
}
