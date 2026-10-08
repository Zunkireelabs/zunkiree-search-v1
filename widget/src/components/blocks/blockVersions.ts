// Which block versions this widget can render, per block type. A block whose type or version is not listed here is
// shown as its plain-text `fallback_text` instead, so an older bundle never mis-renders a newer block.
//
// Rollout rule: when the backend bumps a type's `version` (UISpec in backend/app/schemas/ui_blocks.py), ship a widget
// that lists the new version FIRST, then the backend that emits it. A backend test fails if this table is behind.
export const SUPPORTED_VERSIONS: Record<string, number[]> = {
  choice_cards: [1],
  quick_chips: [1],
  range_slider: [1],
  match_cards: [2],
  info_card: [1],
  comparison_table: [1],
  eligibility_meter: [2],
  profile_summary: [1],
  lead_form: [1],
  stepper: [1],
  accordion: [1],
  checklist: [1],
  timeline: [1],
  cost_calculator: [1],
  journey_cards: [1],
}

// Blocks stored before versions existed carry no `schema_version`; they are v1.
export function isSupported(type: string, version: number | undefined): boolean {
  return SUPPORTED_VERSIONS[type]?.includes(version ?? 1) ?? false
}
