export const evidenceRules = {
  self_emotion_v2: ['worry', 'excitement', 'frustration', 'confidence', 'curiosity'],
  stated_need_v2: ['information', 'guidance', 'support'],
  direct_request_v2: ['information', 'guidance', 'support'],
  first_person_past_v2: ['reported'],
  stated_problem_v1: ['problem'],
  explicit_reason_v1: ['reason'],
} as const;
export const evidenceLabels = ['worry', 'excitement', 'frustration', 'confidence', 'curiosity',
  'information', 'guidance', 'support', 'reported', 'problem', 'reason'] as const;
type EvidenceLabel = typeof evidenceLabels[number];
type EvidenceRule = keyof typeof evidenceRules;
export type ExpressionEvidence = {
  method: 'explicit_english_spans_v2'; documents: number; counts: Record<EvidenceLabel, number>;
  abstentions: Partial<Record<'quoted' | 'ambiguous' | 'evidence_limit', number>>;
  evidence: {row: number; start: number; end: number; rule: EvidenceRule; label: EvidenceLabel; text?: string}[];
};
export type Processing = {
  documents: number; segments: number; characters: number;
  excluded: Record<'language_or_markup' | 'document_limit' | 'duplicate' | 'collection_limit' | 'segment_limit', number>;
};
type RecordMetadata = {source: string; text?: string};
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function integer(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max;
}
export function projectProcessing(value: unknown, documents: number, records: number): Processing | null {
  if (!object(value) || value.documents !== documents || !integer(value.segments, 1200) ||
      value.segments < documents || !integer(value.characters, 100000) || !object(value.excluded)) return null;
  const {language_or_markup, document_limit, duplicate, collection_limit, segment_limit} = value.excluded;
  if (![language_or_markup, document_limit, duplicate, collection_limit, segment_limit].every(count => integer(count, records)) ||
      Number(language_or_markup) + Number(document_limit) + Number(duplicate) + Number(collection_limit) +
        Number(segment_limit) + documents !== records) return null;
  return {documents, segments: value.segments, characters: value.characters,
    excluded: {language_or_markup, document_limit, duplicate, collection_limit, segment_limit} as Processing['excluded']};
}

export function projectExpressionEvidence(value: unknown, rows: number[], records: RecordMetadata[]): ExpressionEvidence | null {
  if (!object(value) || value.method !== 'explicit_english_spans_v2' || value.documents !== rows.length ||
      !object(value.counts) || !object(value.abstentions) || !Array.isArray(value.evidence) || value.evidence.length > rows.length * 64) return null;
  const counts = {} as ExpressionEvidence['counts'];
  for (const label of evidenceLabels) {
    const count = value.counts[label];
    if (!integer(count, rows.length)) return null;
    counts[label] = count;
  }
  const abstentions: ExpressionEvidence['abstentions'] = {};
  for (const [key, count] of Object.entries(value.abstentions)) {
    if (!['quoted', 'ambiguous', 'evidence_limit'].includes(key) || !integer(count, 100000)) return null;
    abstentions[key as keyof typeof abstentions] = count;
  }
  const evidence: ExpressionEvidence['evidence'] = [];
  const labels = new Map<string, Set<number>>();
  const rowCounts = new Map<number, number>();
  const seen = new Set<string>();
  for (const item of value.evidence) {
    if (!object(item) || !integer(item.row, records.length - 1) || !rows.includes(item.row) ||
        !integer(item.start, 8000) || !integer(item.end, 8000) || item.start >= item.end || item.end - item.start > 400 ||
        typeof item.rule !== 'string' || !Object.hasOwn(evidenceRules, item.rule) || typeof item.label !== 'string') return null;
    const rule = item.rule as EvidenceRule;
    const label = item.label as EvidenceLabel;
    const allowed: readonly string[] = evidenceRules[rule];
    if (!allowed.includes(label)) return null;
    const key = `${item.row}:${item.start}:${item.end}:${rule}:${label}`;
    if (seen.has(key)) return null;
    seen.add(key);
    rowCounts.set(item.row, (rowCounts.get(item.row) ?? 0) + 1);
    if (rowCounts.get(item.row)! > 64) return null;
    const projected = {row: item.row, start: item.start, end: item.end, rule, label};
    if (records[item.row].source === 'fictional') {
      const original = records[item.row].text;
      if (typeof original !== 'string' || item.end > [...original].length ||
          item.text !== [...original].slice(item.start, item.end).join('')) return null;
      evidence.push({...projected, text: item.text as string});
    } else {
      if (item.text !== undefined) return null;
      evidence.push(projected);
    }
    if (!labels.has(label)) labels.set(label, new Set());
    labels.get(label)!.add(item.row);
  }
  if (evidenceLabels.some(label => (labels.get(label)?.size ?? 0) !== counts[label])) return null;
  return {method: value.method, documents: rows.length, counts, abstentions, evidence};
}
