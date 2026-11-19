export type FactKind = 'observed' | 'exploratory' | 'insufficient';
export type EvidenceFact = {id: string; metric: string; unit: 'documents' | 'days' | 'score' | 'periods' | 'metadata' | 'interest_index'; kind: FactKind; values: Record<string, string | number | null>; denominator: number | null; method: string};
export type EvidenceScope = {
  source: string; family: 'discussion' | 'search_interest'; mode: 'topic' | 'event'; query: string;
  start_date: string; end_date: string; date_unit: 'day' | 'month'; geography: string;
  requested_geography: string | null; language_filter: string | null; content: string | null; analyzed_documents: number;
};
export type EvidencePackage = {
  package_id: string; version: 'research_evidence_v1'; created_at: string; scope: EvidenceScope; fictional: boolean;
  status: 'exploratory' | 'insufficient'; source_reference: string | null; facts: EvidenceFact[];
};
export type AIInterpretation = {
  package_id: string; model: 'hissiyat-qwen3-1.7b'; prompt_version: 'research_interpretation_v1';
  verification: 'scope_ids_framing_and_numeric_text_checks';
  result: {language: 'tr' | 'en'; scope: EvidenceScope; status: 'exploratory' | 'insufficient'; overview: {evidence_id: string; text: string};
    findings: {evidence_id: string; kind: FactKind; interpretation: string}[];
    uncertainties: {evidence_id: string; text: string}[]; questions: {evidence_id: string; text: string}[]};
};

const fields: Record<string, string[]> = {
  sample: ['retrieved', 'selected', 'analyzed'], source_scope: ['max_items', 'retrieved_at', 'revision', 'examined', 'eligible'],
  coverage: ['first', 'last', 'active_days'], temporal_comparison: [], expression: ['label', 'matched', 'rules'],
  no_expression_matches: ['matched'], expression_unavailable: [],
  topic_partition: ['group_1', 'group_2', 'group_3', 'terms_1', 'terms_2', 'terms_3', 'unassigned', 'assigned', 'groups_count', 'silhouette'],
  agreement: ['ari'], topic_validity: [], topics_unavailable: ['reason'], expression_validity: [], analysis_unavailable: [],
  search_summary: ['cadence', 'first_period', 'last_period', 'nonzero', 'ambiguous_zero', 'missing', 'suppressed', 'peak_period', 'peak_ties', 'direction'],
  search_unverified: [], search_limits: [], geography: ['geography'], context: [], generalization: [],
  csv_coverage: ['observations', 'observed', 'missing', 'suppressed', 'ambiguous_zero', 'first_period', 'last_period', 'interval'],
  csv_extremes: ['peak', 'peak_date', 'peak_ties', 'trough', 'trough_date', 'trough_ties'],
  csv_change: ['first', 'first_date', 'last', 'last_date', 'change'],
  csv_origin: ['sha256', 'attribution', 'measurement'], csv_limits: ['scale_min', 'scale_max'],
  historical_coverage: ['legacy', 'updated', 'shared', 'legacy_only', 'updated_only', 'long_documents'],
  historical_expressions: ['legacy', 'legacy_denominator', 'updated', 'updated_denominator', 'paired_legacy', 'paired_updated', 'paired_documents'],
  historical_clusters: ['legacy_ari', 'updated_ari', 'updated_nmf_silhouette', 'updated_minilm_silhouette'],
  historical_origin: ['examined', 'report_sha256', 'retrieved_at', 'query', 'license'], historical_limits: [],
};
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function text(value: unknown, max: number): value is string {
  return typeof value === 'string' && value.length <= max && !/[<>\x00-\x08]/.test(value);
}
function count(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max;
}
function kind(value: unknown): value is FactKind {
  return value === 'observed' || value === 'exploratory' || value === 'insufficient';
}
function period(value: unknown, unit: unknown): value is string {
  if (typeof value !== 'string' || !(unit === 'month' ? /^\d{4}-\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/).test(value)) return false;
  const day = unit === 'month' ? value + '-01' : value;
  const date = new Date(day + 'T00:00:00Z');
  return Number.isFinite(+date) && date.toISOString().slice(0, 10) === day;
}

export function projectEvidencePackage(value: unknown): EvidencePackage | null {
  if (!object(value) || !text(value.package_id, 32) || !/^[a-f0-9]{32}$/.test(value.package_id) ||
      value.version !== 'research_evidence_v1' || !text(value.created_at, 40) || !Number.isFinite(Date.parse(value.created_at)) ||
      typeof value.fictional !== 'boolean' || value.status !== 'exploratory' && value.status !== 'insufficient' ||
      !object(value.scope) || !Array.isArray(value.facts) || value.facts.length < 1 || value.facts.length > 24) return null;
  const s = value.scope;
  const csv = s.source === 'google_trends_csv';
  if (!['fictional', 'bluesky', 'lemmy', 'wikimedia', 'civil_comments', 'google_trends', 'google_trends_csv'].includes(String(s.source)) ||
      s.family !== (s.source === 'google_trends' || csv ? 'search_interest' : 'discussion') ||
      s.mode !== 'topic' && s.mode !== 'event' || !text(s.query, 120) || s.query.length < 2 ||
      s.date_unit !== (s.source === 'google_trends' ? 'month' : 'day') || !period(s.start_date, s.date_unit) ||
      !period(s.end_date, s.date_unit) || s.start_date > s.end_date || !['UNKNOWN', 'TR', 'US', 'GB', ...(csv ? ['worldwide'] : [])].includes(String(s.geography)) ||
      s.requested_geography !== null && !['TR', 'US', 'GB', ...(csv ? ['worldwide'] : [])].includes(String(s.requested_geography)) ||
      s.language_filter !== null && s.language_filter !== 'en' && s.language_filter !== 'tr' ||
      s.content !== null && !['posts', 'comments', 'mixed'].includes(String(s.content)) || !count(s.analyzed_documents, 100) ||
      s.family === 'discussion' && s.geography !== 'UNKNOWN' || s.source === 'fictional' && !value.fictional) return null;
  const sources = ['https://trends.googleapis.com', 'https://en.wikipedia.org/wiki/Talk:USB_flash_drive',
    'https://huggingface.co/datasets/google/jigsaw_unintended_bias'];
  if (csv) {
    try {
      if (typeof value.source_reference !== 'string') return null;
      const url = new URL(value.source_reference);
      const params = url.searchParams;
      if (url.origin !== 'https://trends.google.com' || url.pathname !== '/trends/explore' || url.username || url.password || url.hash ||
          [...params.keys()].some(key => !['date', 'geo', 'q', 'hl', 'cat', 'gprop'].includes(key) || params.getAll(key).length !== 1) ||
          (params.get('q') ?? '').split(',').some(term => term !== s.query) ||
          (params.get('date') ?? '').split(',').some(range => range !== `${s.start_date} ${s.end_date}`) ||
          !(params.get('geo') ?? '').split(',').map(code => code || 'worldwide').includes(String(s.geography)) ||
          s.requested_geography !== s.geography || value.fictional) return null;
    } catch {return null;}
  } else if (value.source_reference !== null && !sources.includes(String(value.source_reference))) return null;
  const facts: EvidenceFact[] = [];
  for (const item of value.facts) {
    if (!object(item) || !text(item.id, 3) || !/^E[0-9]{2}$/.test(item.id) || facts.some(fact => fact.id === item.id) ||
        !text(item.metric, 40) || !Object.hasOwn(fields, item.metric) || !kind(item.kind) ||
        !['documents', 'days', 'score', 'periods', 'metadata', 'interest_index'].includes(String(item.unit)) ||
        !text(item.method, 100) || !/^[a-z0-9_]+$/.test(item.method) || !object(item.values) ||
        item.denominator !== null && !count(item.denominator, item.unit === 'periods' ? 2000 : 100)) return null;
    const values: EvidenceFact['values'] = {};
    for (const [key, entry] of Object.entries(item.values)) {
      if (!fields[item.metric].includes(key) || entry !== null &&
          !(typeof entry === 'number' && Number.isFinite(entry) && Math.abs(entry) <= 1000000) &&
          !(text(entry, 160) && !/[<>@]|https?:\/\//i.test(entry))) return null;
      values[key] = entry as string | number | null;
    }
    const required = fields[item.metric].filter(key => item.metric !== 'topic_partition' || key !== 'group_3' && key !== 'terms_3');
    if (required.some(key => !Object.hasOwn(values, key))) return null;
    facts.push({id: item.id, metric: item.metric, unit: item.unit as EvidenceFact['unit'], kind: item.kind,
      values, denominator: item.denominator as number | null, method: item.method});
  }
  const scope = Object.fromEntries(['source', 'family', 'mode', 'query', 'start_date', 'end_date', 'date_unit', 'geography',
    'requested_geography', 'language_filter', 'content', 'analyzed_documents'].map(key => [key, s[key]])) as EvidenceScope;
  const sample = facts.find(fact => fact.metric === 'sample');
  if (scope.family === 'discussion' && (!sample || sample.values.analyzed !== scope.analyzed_documents ||
      !count(sample.values.selected, 100) || sample.denominator !== sample.values.selected)) return null;
  return {package_id: value.package_id, version: value.version, created_at: value.created_at, scope,
    fictional: value.fictional, status: value.status, source_reference: value.source_reference as string | null, facts};
}

export function projectAIInterpretation(value: unknown, evidence: EvidencePackage, language: 'tr' | 'en'): AIInterpretation | null {
  if (!object(value) || value.package_id !== evidence.package_id || value.model !== 'hissiyat-qwen3-1.7b' ||
      value.prompt_version !== 'research_interpretation_v1' || value.verification !== 'scope_ids_framing_and_numeric_text_checks' ||
      !object(value.result)) return null;
  const result = value.result;
  if (result.language !== language || result.status !== evidence.status || !object(result.scope) ||
      Object.entries(evidence.scope).some(([key, entry]) => (result.scope as Record<string, unknown>)[key] !== entry) ||
      !object(result.overview) || !text(result.overview.text, 200) || result.overview.text.length < 10 ||
      typeof result.overview.evidence_id !== 'string' || !evidence.facts.some(fact => fact.id === (result.overview as Record<string, unknown>).evidence_id) ||
      !Array.isArray(result.findings) || result.findings.length < 1 || result.findings.length > 3) return null;
  const findings: AIInterpretation['result']['findings'] = [];
  for (const item of result.findings) {
    if (!object(item) || !text(item.interpretation, 240) || item.interpretation.length < 10 ||
        !text(item.evidence_id, 3) || findings.some(finding => finding.evidence_id === item.evidence_id) ||
        !evidence.facts.some(fact => fact.id === item.evidence_id && fact.kind === item.kind)) return null;
    findings.push({evidence_id: item.evidence_id, kind: item.kind as FactKind, interpretation: item.interpretation});
  }
  function notes(input: unknown): AIInterpretation['result']['uncertainties'] | null {
    if (!Array.isArray(input) || input.length !== 1) return null;
    const item = input[0];
    return object(item) && text(item.text, 200) && item.text.length >= 10 && typeof item.evidence_id === 'string' &&
      evidence.facts.some(fact => fact.id === item.evidence_id && fact.kind === 'insufficient') ? [{evidence_id: item.evidence_id, text: item.text}] : null;
  }
  const uncertainties = notes(result.uncertainties), questions = notes(result.questions);
  if (!uncertainties || !questions || !questions[0].text.endsWith('?')) return null;
  return {package_id: evidence.package_id, model: value.model, prompt_version: value.prompt_version, verification: value.verification,
    result: {language, scope: evidence.scope, status: evidence.status,
      overview: {evidence_id: result.overview.evidence_id, text: result.overview.text}, findings, uncertainties, questions}};
}
