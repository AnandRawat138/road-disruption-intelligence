// Display metadata. Colours are always paired with text/glyphs so meaning never relies on colour alone.
// Map markers encode SEVERITY with one ordinal orange ramp (light = low, dark = critical); the category is
// carried by a text glyph, because 12 categorical hues cannot be told apart reliably (palette validator FAIL).
export const SEVERITY_RAMP: Record<string, string> = {
  LOW: '#f6c3a5', MODERATE: '#ee8f5f', HIGH: '#d95926', CRITICAL: '#8f3210', UNKNOWN: '#98a2b3',
}
export const SEVERITY_GLYPH_INK: Record<string, string> = {
  LOW: '#3b1d0c', MODERATE: '#2a1206', HIGH: '#ffffff', CRITICAL: '#ffffff', UNKNOWN: '#101828',
}
export const CATEGORY_META: Record<string, { label: string; color: string; glyph: string }> = {
  ACCIDENT: { label: 'Accident', color: '#c2410c', glyph: 'AC' },
  CONGESTION: { label: 'Congestion', color: '#a16207', glyph: 'CG' },
  CLOSURE: { label: 'Closure', color: '#b91c1c', glyph: 'CL' },
  DIVERSION: { label: 'Diversion', color: '#7c3aed', glyph: 'DV' },
  FLOODING: { label: 'Flooding / waterlogging', color: '#0369a1', glyph: 'FL' },
  LANDSLIDE: { label: 'Landslide', color: '#78350f', glyph: 'LS' },
  PROTEST: { label: 'Protest / blockade', color: '#be185d', glyph: 'PR' },
  CONSTRUCTION: { label: 'Construction / maintenance', color: '#4d7c0f', glyph: 'CN' },
  WEATHER: { label: 'Weather disruption', color: '#0e7490', glyph: 'WX' },
  INFRASTRUCTURE: { label: 'Infrastructure damage', color: '#57534e', glyph: 'IN' },
  SECURITY_VIP: { label: 'Security / VIP movement', color: '#1e3a8a', glyph: 'VP' },
  OTHER: { label: 'Other', color: '#475569', glyph: 'OT' },
  UNKNOWN: { label: 'Unknown', color: '#94a3b8', glyph: '?' },
}

export const SEVERITIES = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'UNKNOWN']
export const SEVERITY_META: Record<string, { label: string; level: number; color: string }> = {
  CRITICAL: { label: 'Critical', level: 4, color: '#7f1d1d' },
  HIGH: { label: 'High', level: 3, color: '#b42318' },
  MODERATE: { label: 'Moderate', level: 2, color: '#9a5b00' },
  LOW: { label: 'Low', level: 1, color: '#157f3b' },
  UNKNOWN: { label: 'Unknown', level: 0, color: '#64748b' },
}

export const INCIDENT_STATUSES = ['NEW', 'MONITORING', 'CONFIRMED', 'RESOLVED', 'DISMISSED']
export const STATUS_TONE: Record<string, string> = {
  NEW: 'blue', MONITORING: 'warn', CONFIRMED: 'danger', RESOLVED: 'ok', DISMISSED: 'neutral',
}
export const RELEVANCE_LABEL: Record<string, string> = {
  RELEVANT: 'Relevant', RELATED: 'Related transport', IRRELEVANT: 'Irrelevant', NEEDS_REVIEW: 'Needs review',
}
export const CLASS_STATUS_LABEL: Record<string, string> = {
  UNCLASSIFIED: 'Unclassified', QUEUED: 'Queued', PROCESSING: 'Processing', CLASSIFIED: 'Classified', FAILED: 'Failed',
}
export const REVIEW_LABEL: Record<string, string> = {
  UNREVIEWED: 'Not reviewed', PENDING_REVIEW: 'Awaiting review', APPROVED: 'Approved', REJECTED: 'Rejected',
  NOT_REQUIRED: 'No review needed',
}
export const PREFILTER_LABEL: Record<string, string> = {
  LIKELY_RELEVANT: 'Likely relevant', POSSIBLY_RELEVANT: 'Possibly relevant', UNLIKELY: 'Unlikely',
}
export const PRECISION_LABEL: Record<string, string> = {
  LOCALITY: '≈ Locality', CITY: '≈ City centroid', STATE: '≈ State only', MANUAL: 'Operator-placed',
}
export const TIME_STATUS = ['ONGOING', 'UPCOMING', 'RESOLVED', 'UNKNOWN']
export const catLabel = (c?: string | null) => (c ? CATEGORY_META[c]?.label || c : '—')
