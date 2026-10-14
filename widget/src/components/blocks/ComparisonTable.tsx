import type { BlockComponentProps, ComparisonData } from './types'

// Wide comparisons scroll sideways inside their own box: the row labels stay in view, the box can be scrolled with the
// keyboard (it is focusable and labelled), and the table has a caption for screen readers.
export function ComparisonTable({ block }: BlockComponentProps<ComparisonData>) {
  const { columns, rows } = block.data
  const name = block.title || 'Comparison'
  return (
    <div className="zk-compare" role="region" aria-label={`${name}, scrollable`} tabIndex={0}>
      <table>
        <caption className="zk-sr-only">{name}</caption>
        <thead>
          <tr>
            <th scope="col"><span className="zk-sr-only">Detail</span></th>
            {columns.map(c => <th key={c.id} scope="col">{c.icon} {c.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <th scope="row">{r.label}</th>
              {r.values.map((v, j) => <td key={j}>{v}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
