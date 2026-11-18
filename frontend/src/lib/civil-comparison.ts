import {isLocalAnalysisResult, type LocalAnalysisResult} from './local-analysis-contract.ts';
import {evidenceLabels, evidenceRules} from './expression-evidence.ts';

export const comparisonQuestions = ['wages', 'job_opportunities'] as const;
export const comparisonPolicies = ['legacy', 'updated'] as const;
const metrics = ['matched', 'outside_dates', 'invalid', 'duplicates', 'eligible', 'selected', 'selected_characters',
  'selected_long_documents', 'analyzed', 'characters', 'segments', 'documents_with_expressions'] as const;
const screeningKeys = ['length', 'privacy_or_markup', 'language', 'moderation', 'safety_labels'] as const;
const processingKeys = ['language_or_markup', 'document_limit', 'duplicate', 'collection_limit', 'segment_limit'] as const;
type Label = typeof evidenceLabels[number];
type Quality = {status: 'comparison' | 'nmf_only' | 'insufficient_texts' | 'insufficient_variation'; topics: LocalAnalysisResult | null};
export type PolicySummary = Record<typeof metrics[number], number> & Quality & {
  screening: Record<typeof screeningKeys[number], number>;
  processing_exclusions: Record<typeof processingKeys[number], number>;
  counts: Record<Label, number | null>; evidence_spans: number | null; late_evidence_documents: number | null;
  abstentions: Record<string, number> | null; rule_documents: Record<string, number> | null;
  sensitivity: Quality;
};
type Change = Record<'legacy' | 'updated' | 'retained' | 'gained' | 'lost', number>;
export type CivilComparison = {
  retrieved_at: string;
  questions: Record<typeof comparisonQuestions[number], Record<typeof comparisonPolicies[number], PolicySummary> & {
    query: string; selection: Record<'shared' | 'legacy_only' | 'updated_only', number>;
    paired: {documents: number; legacy_detected_documents: number; updated_detected_documents: number;
      categories: Record<string, Change>; new_categories: Record<string, number>};
  }>;
};
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function count(value: unknown, max = 97320): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max;
}
function numbers<const Key extends string>(value: unknown, keys: readonly Key[], max = 97320): Record<Key, number> | null {
  if (!object(value)) return null;
  const result = {} as Record<Key, number>;
  for (const key of keys) {
    if (!count(value[key], max)) return null;
    result[key] = value[key];
  }
  return result;
}
function quality(status: unknown, topics: unknown, total: number, k: number, minimum: number): Quality | null {
  if (status === 'insufficient_texts' || status === 'insufficient_variation') {
    return topics === null && (status === 'insufficient_texts' ? total < minimum : total >= minimum) ? {status, topics: null} : null;
  }
  if (total < minimum || status !== 'comparison' && status !== 'nmf_only' ||
      !isLocalAnalysisResult(topics, total, k, status === 'comparison' ? 'both' : 'nmf')) return null;
  return {status, topics};
}
function policy(value: unknown, updated: boolean): PolicySummary | null {
  if (!object(value)) return null;
  const totals = numbers(value, metrics, 800000);
  const screening = numbers(value.screening, screeningKeys);
  const processing = numbers(value.processing_exclusions, processingKeys, 100);
  if (!totals || !screening || !processing || !object(value.counts) ||
      totals.matched > 97320 || totals.eligible > totals.matched || totals.selected > Math.min(100, totals.eligible) ||
      totals.analyzed > totals.selected || totals.characters > Math.min(100000, totals.selected_characters) ||
      totals.selected_characters > totals.selected * (updated ? 8000 : 500) ||
      totals.segments < totals.analyzed || totals.segments > 1200 ||
      totals.documents_with_expressions > totals.analyzed || totals.selected_long_documents > totals.selected ||
      !updated && totals.selected_long_documents !== 0 ||
      Object.values(processing).reduce((sum, n) => sum + n, totals.analyzed) !== totals.selected ||
      totals.outside_dates + totals.invalid + totals.duplicates + totals.eligible +
        Object.values(screening).reduce((sum, n) => sum + n, 0) !== totals.matched) return null;
  const counts = {} as PolicySummary['counts'];
  for (const label of evidenceLabels) {
    const number = value.counts[label];
    if (!updated && (label === 'problem' || label === 'reason') ? number !== null : !count(number, totals.analyzed)) return null;
    counts[label] = number as number | null;
  }
  const topics = quality(value.topics_status, value.topics, totals.analyzed, 2, 12);
  const sensitivity = object(value.sensitivity) && value.sensitivity.k === 3
    ? quality(value.sensitivity.status, value.sensitivity.topics, totals.analyzed, 3, 24) : null;
  if (!topics || !sensitivity) return null;
  const abstentions = updated ? numbers(value.abstentions, object(value.abstentions) ? Object.keys(value.abstentions) : [], 100000) : null;
  const rules = updated ? numbers(value.rule_documents, Object.keys(evidenceRules), totals.analyzed) : null;
  if (updated ? !count(value.evidence_spans, totals.analyzed * 64) || !count(value.late_evidence_documents, totals.analyzed) ||
      !abstentions || !rules || Object.keys(abstentions).some(key => !['quoted', 'ambiguous', 'evidence_limit'].includes(key))
    : value.evidence_spans !== null || value.late_evidence_documents !== null || value.abstentions !== null || value.rule_documents !== null) return null;
  return {...totals, ...topics, sensitivity, counts, screening, processing_exclusions: processing,
    evidence_spans: value.evidence_spans as number | null, late_evidence_documents: value.late_evidence_documents as number | null,
    abstentions, rule_documents: rules};
}

export function projectCivilComparison(value: unknown): CivilComparison | null {
  if (!object(value) || value.schema_version !== 1 || value.geography !== 'unknown' || value.article_context !== 'unavailable' ||
      !object(value.dataset) || value.dataset.examined !== 97320 || value.dataset.license !== 'CC0 1.0' ||
      value.dataset.source !== 'https://huggingface.co/datasets/google/jigsaw_unintended_bias' ||
      value.dataset.license_url !== 'https://creativecommons.org/publicdomain/zero/1.0/' ||
      value.dataset.artifact !== 'test_public_expanded.csv.gz' || value.dataset.revision !== '9beb047ad342ac2c3ac209d2d74e0b7c833fe294' ||
      value.dataset.sha256 !== 'a5a8fba390af3f17639b1bcef9b1c1b38373d3e45728f7eb814bfe5f3ea1c3d2' ||
      typeof value.dataset.retrieved_at !== 'string' || !Number.isFinite(Date.parse(value.dataset.retrieved_at)) ||
      JSON.stringify(value.study_window) !== '["2015-01-01","2017-12-31"]' || !object(value.questions)) return null;
  const questions = {} as CivilComparison['questions'];
  const queries = {wages: 'minimum wage | living wage | hourly wages | low wages',
    job_opportunities: 'job opportunities | job creation | create jobs | creating jobs | find a job | finding a job | looking for work'};
  for (const question of comparisonQuestions) {
    const input = value.questions[question];
    if (!object(input) || input.query !== queries[question]) return null;
    const legacy = policy(input.legacy, false), updated = policy(input.updated, true);
    const selection = numbers(input.selection, ['shared', 'legacy_only', 'updated_only'], 100);
    if (!legacy || !updated || legacy.matched !== updated.matched || !selection ||
        selection.shared + selection.legacy_only !== legacy.selected ||
        selection.shared + selection.updated_only !== updated.selected || !object(input.paired)) return null;
    const paired = numbers(input.paired, ['documents', 'legacy_detected_documents', 'updated_detected_documents'], selection.shared);
    if (!paired || paired.documents > Math.min(legacy.analyzed, updated.analyzed) ||
        paired.legacy_detected_documents > paired.documents || paired.updated_detected_documents > paired.documents || !object(input.paired.categories)) return null;
    const categories: Record<string, Change> = {};
    for (const label of evidenceLabels.slice(0, 9)) {
      const changes = numbers(input.paired.categories[label], ['legacy', 'updated', 'retained', 'gained', 'lost'], paired.documents);
      if (!changes || changes.retained + changes.gained !== changes.updated || changes.retained + changes.lost !== changes.legacy) return null;
      categories[label] = changes;
    }
    const newCategories = numbers(input.paired.new_categories, ['problem', 'reason'], paired.documents);
    if (!newCategories) return null;
    questions[question] = {query: queries[question], legacy, updated, selection, paired: {...paired, categories, new_categories: newCategories}};
  }
  return {retrieved_at: value.dataset.retrieved_at, questions};
}
