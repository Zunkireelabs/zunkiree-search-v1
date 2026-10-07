// Dev-only preview: renders every block type with mock data so the UI can be
// reviewed without the backend. Not part of the widget bundle (not an entry in vite.config.ts).
import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import { styles } from '../components/styles'
import { BlockRenderer } from '../components/blocks/BlockRenderer'
import type { UIBlock, BlockActionEvent } from '../components/blocks/types'
import { BlockSkeleton } from '../components/blocks/BlockSkeleton'
import { ProfileProgress } from '../components/blocks/ProfileProgress'

const PRIMARY = '#2563eb'

const COUNTRIES = [
  { id: 'ca', label: 'Canada', icon: '🇨🇦' }, { id: 'uk', label: 'U.K.', icon: '🇬🇧' },
  { id: 'us', label: 'U.S.A.', icon: '🇺🇸' }, { id: 'au', label: 'Australia', icon: '🇦🇺' },
  { id: 'de', label: 'Germany', icon: '🇩🇪' }, { id: 'ie', label: 'Ireland', icon: '🇮🇪' },
]

const base = { schema_version: 1 }

const FLOW: { say: string; block: UIBlock }[] = [
  { say: 'Hi! I’m Admizz. Where would you like to start?', block: { ...base, block_id: 'w1', type: 'journey_cards', title: 'How can I help you today?', fallback_text: 'Find a country, check eligibility, estimate costs, learn how to apply, or talk to a counselor.', data: { tiles: [
    { id: 'find', icon: '🌍', title: 'Find the right country', description: 'Match countries to your budget and scores' },
    { id: 'eligibility', icon: '🎓', title: 'Check my eligibility', description: 'See if you meet a country’s requirements' },
    { id: 'costs', icon: '💰', title: 'Estimate my costs', description: 'Tuition and living costs in a live calculator' },
    { id: 'apply', icon: '📝', title: 'How to apply', description: 'The application process, step by step' },
    { id: 'counselor', icon: '💬', title: 'Talk to a counselor', description: 'Get personal help from the Admizz team' },
  ] } } },
  { say: 'Here is how applying works.', block: { ...base, block_id: 'p1', type: 'stepper', title: 'Applying through Admizz', sources: ['What is the process to apply…'], fallback_text: 'Book a consultation, discuss options, get help with documents and visa.', data: { steps: [
    { title: 'Book a consultation', detail: 'Start with a free consultation with an Admizz counselor.' },
    { title: 'Discuss your options', detail: 'Talk through countries, universities and programs that fit you.' },
    { title: 'Prepare application documents', detail: 'Get help with your application documents.' },
    { title: 'Get visa support', detail: 'Receive guidance through the student visa process.' },
  ] } } },
  { say: 'These are the documents you’ll generally need.', block: { ...base, block_id: 'c1', type: 'checklist', title: 'Admission requirements', sources: ['What are the admission requirements?'], fallback_text: 'Application form, transcripts, test scores; sometimes essays or recommendation letters.', data: { items: [
    { label: 'Application form' }, { label: 'Academic transcripts' }, { label: 'Standardized test scores' },
    { label: 'Essays or letters of recommendation', note: 'Only for some programs' },
  ] } } },
  { say: 'Here is what Admizz can help with.', block: { ...base, block_id: 'o1', type: 'accordion', title: 'Admizz services', sources: ['Auto-FAQ'], fallback_text: 'Shortlisting, documents, scholarships, visa guidance.', data: { items: [
    { title: 'University shortlisting', summary: 'Find universities that fit you', detail: 'Admizz provides assistance with university shortlisting.' },
    { title: 'Application documents', summary: 'SOP, LOR and more', detail: 'Admizz offers application document assistance including SOP and LOR.' },
    { title: 'Scholarships and fee waivers', summary: 'Guidance on funding', detail: 'Admizz provides guidance on scholarships and fee waivers.' },
    { title: 'Visa guidance', summary: 'For international students', detail: 'Admizz offers visa guidance for international students.' },
  ] } } },
  { say: 'Key dates for the UK:', block: { ...base, block_id: 't1', type: 'timeline', title: 'Intake timeline', fallback_text: 'Intakes and deadlines.', data: { events: [
    { when: 'Sep', title: 'Main intake', detail: 'Most programs start in September.' }, { when: 'Jan', title: 'Second intake', detail: 'Fewer programs start in January.' },
  ] } } },
  { say: 'Play with the numbers:', block: { ...base, block_id: 'k1', type: 'cost_calculator', title: 'U.K. cost calculator', fallback_text: 'Tuition plus living costs.', data: { country_id: 'uk', currency: '$', note: 'Typical ranges: your total depends on the university and city.', parts: [
    { id: 'tuition', label: 'Tuition / year', min: 14000, max: 28000, step: 500, value: 21000 },
    { id: 'living', label: 'Living / year', min: 11000, max: 15000, step: 500, value: 13000 },
  ] } } },
  { say: 'Great! Which countries are you interested in?', block: { ...base, block_id: 'b1', type: 'choice_cards', title: 'Destination countries', subtitle: 'Pick one or more', fallback_text: 'Which countries are you interested in?', data: { field: 'countries', multi: true, options: COUNTRIES } } },
  { say: 'What is your budget per year (tuition + living)?', block: { ...base, block_id: 'b2', type: 'range_slider', title: 'Yearly budget', fallback_text: 'What is your yearly budget?', data: { field: 'budget', min: 10000, max: 60000, step: 1000, value: 25000, unit: '$' } } },
  { say: 'Here are the countries that match your profile.', block: { ...base, block_id: 'b3', type: 'match_cards', title: 'Countries that match your profile', fallback_text: 'Best matches: Australia 92%, U.K. 85%, Canada 78%.', data: { items: [
    { id: 'au', label: 'Australia', icon: '🇦🇺', score: 92, reasons: ['Fits your $25k budget', 'Post-study work visa up to 3 years', 'Feb & July intakes'] },
    { id: 'uk', label: 'U.K.', icon: '🇬🇧', score: 85, reasons: ['1-year master’s programs', 'IELTS 6.5 accepted'] },
    { id: 'ca', label: 'Canada', icon: '🇨🇦', score: 78, reasons: ['Work while studying', 'Slightly above your budget'] },
  ] } } },
  { say: 'UK vs Australia, side by side:', block: { ...base, block_id: 'b4', type: 'comparison_table', title: 'U.K. vs Australia', fallback_text: 'Comparison of UK and Australia.', data: { columns: [{ id: 'uk', label: 'U.K.', icon: '🇬🇧' }, { id: 'au', label: 'Australia', icon: '🇦🇺' }], rows: [
    { label: 'Tuition / year', values: ['£15,000', 'A$30,000'] }, { label: 'Living / year', values: ['£12,000', 'A$24,000'] },
    { label: 'Intakes', values: ['Sep, Jan', 'Feb, Jul'] }, { label: 'Work visa', values: ['2 years', '2–3 years'] },
  ] } } },
  { say: 'Let me check your eligibility for Australia.', block: { ...base, block_id: 'b5', type: 'eligibility_meter', title: 'Australia eligibility', fallback_text: 'You meet most requirements for Australia.', data: { score: 80, verdict: 'You meet most requirements', checks: [
    { label: 'English (IELTS 6.5)', ok: true, detail: 'Meets the 6.5 minimum' },
    { label: 'Academic score', ok: true, detail: '72% — above the 60% cutoff' },
    { label: 'Funds', ok: false, detail: 'Proof of A$29,710 living costs needed' },
  ] } } },
  { say: 'Here is what I know about you so far.', block: { ...base, block_id: 'b6', type: 'profile_summary', title: 'Your profile', fallback_text: 'Your profile summary.', actions: [{ id: 'edit', label: 'Update my details' }], data: { rows: [
    { label: 'Countries', value: 'U.K., Australia' }, { label: 'Level', value: "Master's" }, { label: 'Budget', value: '$25,000 / year' }, { label: 'IELTS', value: '6.5' },
  ], missing: ['intake', 'field of study'] } } },
  { say: 'Want a counselor to help with applications?', block: { ...base, block_id: 'b7', type: 'lead_form', title: 'Talk to a counselor', subtitle: 'Pre-filled from your profile', fallback_text: 'Share your name, email and phone.', data: { fields: [
    { id: 'name', label: 'Full name', type: 'text', required: true }, { id: 'email', label: 'Email', type: 'email', required: true }, { id: 'phone', label: 'Phone', type: 'tel', required: true },
  ] } } },
  { say: 'Or jump to a topic:', block: { ...base, block_id: 'b8', type: 'quick_chips', fallback_text: 'Pick a topic.', data: { chips: [{ id: 'visa', label: 'Visa process' }, { id: 'scholar', label: 'Scholarships' }, { id: 'cost', label: 'Cost of living' }] } } },
  { say: '', block: { ...base, block_id: 'b9', type: 'info_card', fallback_text: 'Australia quick facts.', data: { icon: '🇦🇺', heading: 'Australia quick facts', rows: [
    { label: 'Avg. tuition', value: 'A$20–45k / yr' }, { label: 'Intakes', value: 'Feb, Jul' }, { label: 'Work rights', value: '48 hrs / fortnight' }, { label: 'Post-study visa', value: 'Up to 3 years' },
  ] } } },
]

function Preview() {
  const [step, setStep] = useState(1)
  const [log, setLog] = useState<string[]>([])
  const [locked, setLocked] = useState(false)
  const [showAll, setShowAll] = useState(true)
  const [answers, setAnswers] = useState<Record<string, Record<string, unknown>>>({})
  const params = new URLSearchParams(window.location.search)
  const mobile = params.get('mobile') === '1'
  // ?answered=1 pre-answers the input cards so the collapsed state can be reviewed
  const preAnswered: Record<string, Record<string, unknown>> = params.get('answered') === '1' ? {
    'b1': { field: 'countries', selected: ['uk', 'au'] }, 'b2': { field: 'budget', value: 25000 }, 'w1': { journey: 'apply' }, 'b7': { name: 'x' },
  } : {}

  const onAction = (e: BlockActionEvent) => {
    setLog(l => [`${e.blockType} → ${e.actionId} ${JSON.stringify(e.values)}`, ...l].slice(0, 6))
    if (['select', 'set_value', 'start', 'submit'].includes(e.actionId)) setAnswers(a => ({ ...a, [e.blockId]: e.values }))
    setLocked(true)
    setTimeout(() => { setLocked(false); setStep(s => Math.min(s + 1, FLOW.length)) }, 400)
  }

  const items = showAll ? FLOW : FLOW.slice(0, step)

  return (
    <div className={mobile ? 'zk-mobile' : ''} style={{ display: 'flex', gap: 24, padding: mobile ? 8 : 24, flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'center' }}>
      <style>{styles(PRIMARY)}</style>
      <div style={{ width: mobile ? 359 : 440, background: '#fff', borderRadius: 16, boxShadow: '0 8px 30px rgba(0,0,0,.12)', padding: 16 }}>
        <ProfileProgress progress={{ filled: 3, total: 6 }} />
        <div className="zk-message zk-message--rich zk-message-assistant" style={{ marginBottom: 14 }}>
          <div className="zk-message-content">Finding the steps for you…</div>
          <BlockSkeleton blockType="stepper" label="Finding the steps…" />
        </div>
        {items.map(({ say, block }, i) => (
          <div key={block.block_id} className="zk-message zk-message--rich zk-message-assistant" style={{ marginBottom: 14 }}>
            {say && <div className="zk-message-content">{say}</div>}
            <BlockRenderer
              block={{ ...block, answered: answers[block.block_id] ?? preAnswered[block.block_id] }}
              onAction={onAction} busy={locked} locked={locked || (!showAll && i !== items.length - 1)}
            />
          </div>
        ))}
      </div>
      <div style={{ width: 300, font: '13px/1.5 monospace' }}>
        <label style={{ display: 'block', marginBottom: 12 }}>
          <input type="checkbox" checked={showAll} onChange={e => { setShowAll(e.target.checked); setStep(1) }} /> Show all block types
        </label>
        <strong>Last actions sent to backend:</strong>
        {log.length === 0 && <div style={{ color: '#9ca3af' }}>(tap something)</div>}
        {log.map((l, i) => <div key={i} style={{ margin: '4px 0', wordBreak: 'break-all' }}>{l}</div>)}
      </div>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><Preview /></React.StrictMode>)
