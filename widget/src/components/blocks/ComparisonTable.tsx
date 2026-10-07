import type { BlockComponentProps, ComparisonData } from './types'

export function ComparisonTable({ block }: BlockComponentProps<ComparisonData>) {
  const { columns, rows } = block.data
  return (
    <div className="zk-compare">
      <table>
        <thead>
          <tr>
            <th />
            {columns.map(c => <th key={c.id}>{c.icon} {c.label}</th>)}
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
