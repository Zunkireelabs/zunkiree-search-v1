import type { BlockComponentProps, CourseResultsData } from './types'
import { idx } from './ui'

// Courses at partner universities. Every value is copied from the catalog by the backend; this component only lays it out.
export function CourseResults({ block, onAction, locked }: BlockComponentProps<CourseResultsData>) {
  const { items, total, universities, filters } = block.data
  const count = total === items.length ? `${total} course${total === 1 ? '' : 's'}` : `Showing ${items.length} of ${total} courses`
  return (
    <div className="zk-courses">
      <p className="zk-courses__count">
        {count} at {universities} universit{universities === 1 ? 'y' : 'ies'}
        {filters.length > 0 && <span className="zk-courses__filters"> · {filters.join(' · ')}</span>}
      </p>
      <ul className="zk-courses__list">
        {items.map((c, i) => (
          <li key={c.course_id} className="zk-course" style={idx(i)}>
            <div className="zk-course__head">
              <span className="zk-course__name">{c.name}</span>
              <span className="zk-course__level">{c.level_label}</span>
            </div>
            <div className="zk-course__uni">{c.university}{c.city ? ` · ${c.city}` : ''}</div>
            <dl className="zk-course__facts">
              {c.fee && <div><dt>Fee</dt><dd>{c.fee}</dd></div>}
              {c.duration && <div><dt>Length</dt><dd>{c.duration}</dd></div>}
              {c.intakes && <div><dt>Intake</dt><dd>{c.intakes}</dd></div>}
              {c.ielts && <div><dt>English</dt><dd>{c.ielts}</dd></div>}
            </dl>
            {!locked && (
              <button
                type="button" className="zk-course__open"
                onClick={() => onAction({
                  blockId: block.block_id, blockType: block.type, actionId: 'open_university',
                  values: { university_id: c.university_id }, displayText: `Tell me about ${c.university}`,
                })}
              >
                About {c.university} →
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
