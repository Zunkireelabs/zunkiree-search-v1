// Generative-UI blocks. The backend picks the block TYPE and fills `data`;
// the widget owns how each type looks (one component per type).

export interface BlockAction {
  id: string
  label: string
}

export interface UIBlock<T = any> {
  block_id: string
  type: string
  schema_version: number
  title?: string
  subtitle?: string
  data: T
  actions?: BlockAction[]
  fallback_text: string
  // Set when the same block is re-shown with different content because the profile changed.
  changed_because?: string
  // Knowledge-base pages the content came from.
  sources?: string[]
  // What the student submitted on this block; the card collapses to a summary once set.
  answered?: Record<string, any>
}

export interface BlockActionEvent {
  blockId: string
  blockType: string
  actionId: string
  values: Record<string, unknown>
  displayText: string
}

export type OnBlockAction = (event: BlockActionEvent) => void

export interface BlockComponentProps<T = any> {
  block: UIBlock<T>
  onAction: OnBlockAction
  // True once the student has acted on this block (or it is no longer the latest).
  locked: boolean
}

// ---- per-type data shapes ----
export interface ChoiceOption { id: string; label: string; icon?: string; hint?: string }
export interface ChoiceCardsData { multi: boolean; options: ChoiceOption[]; selected?: string[]; field: string }
export interface QuickChipsData { chips: { id: string; label: string }[] }
export interface RangeSliderData { field: string; min: number; max: number; step: number; value: number; unit: string }
export type FitTier = 'strong' | 'good' | 'possible' | 'needs_review'
export type ReasonStatus = 'pass' | 'partial' | 'fail' | 'info'
export interface MatchReason { text: string; status: ReasonStatus }
// A fit tier describes how the student's own details line up with the catalog. It is never a chance of admission.
export interface MatchItem { id: string; label: string; icon?: string; tier: FitTier; tier_label: string; reasons: MatchReason[] }
export interface MatchCardsData { items: MatchItem[] }
export interface InfoCardData { icon?: string; heading: string; rows: { label: string; value: string }[] }
export interface CourseRow {
  course_id: string; name: string; level_label: string; university_id: string; university: string
  city?: string; duration?: string; fee?: string; intakes?: string; ielts?: string
}
export interface CourseResultsData { total: number; universities: number; filters: string[]; items: CourseRow[] }
export interface UniversityCardData { university_id: string; name: string; city?: string; rows: { label: string; value: string }[] }
export interface ComparisonData { columns: { id: string; label: string; icon?: string }[]; rows: { label: string; values: string[] }[] }
export interface EligibilityData { verdict: string; checks: { label: string; ok: boolean; detail: string }[] }
export interface ProfileSummaryData { welcome_back?: boolean; rows: { label: string; value: string }[]; missing?: string[] }
export interface LeadFormData { fields: { id: string; label: string; type: 'text' | 'email' | 'tel'; required: boolean; value?: string }[] }
export interface StepperData { steps: { title: string; detail?: string }[] }
export interface AccordionData { items: { title: string; summary?: string; detail: string }[] }
export interface ChecklistData { items: { label: string; note?: string }[] }
export interface TimelineData { events: { when: string; title: string; detail?: string }[] }
export interface CostCalculatorData {
  country_id?: string
  currency: string
  parts: { id: string; label: string; min: number; max: number; step: number; value: number }[]
  note?: string
}
export interface JourneyCardsData { tiles: { id: string; icon?: string; title: string; description: string }[] }
