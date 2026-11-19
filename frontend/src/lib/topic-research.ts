import {analysisLimits, isExpressionSignals, isLocalAnalysisResult, type ExpressionSignals,
  type LocalAnalysisResult} from './local-analysis-contract.ts';
import type {TrendsCountry} from './trends-research.ts';
import {projectExpressionEvidence, projectProcessing, type ExpressionEvidence, type Processing} from './expression-evidence.ts';
import {projectEvidencePackage, type EvidencePackage} from './research-interpretation.ts';

export const researchSources = ['google_trends', 'google_trends_csv', 'fictional', 'civil_comments', 'wikimedia', 'lemmy', 'bluesky'] as const;
export const wikimediaTitle = 'Talk:USB flash drive';
export const civilDates = {first: '2015-01-01', last: '2017-12-31'};
const civilRows = 97320;
const civilSource = 'https://huggingface.co/datasets/google/jigsaw_unintended_bias';
const civilLicense = 'https://creativecommons.org/publicdomain/zero/1.0/';
const civilArtifact = 'test_public_expanded.csv.gz';
const civilRevision = '9beb047ad342ac2c3ac209d2d74e0b7c833fe294';
const civilChecksum = 'a5a8fba390af3f17639b1bcef9b1c1b38373d3e45728f7eb814bfe5f3ea1c3d2';
export const civilScreeningReasons = ['length', 'privacy_or_markup', 'language', 'moderation', 'safety_labels'] as const;
type CivilScreening = Record<typeof civilScreeningReasons[number], number>;
export const civilDistribution = `https://huggingface.co/datasets/shuttie/jigsaw-unintended-bias/tree/${civilRevision}/data`;
const wikimediaPage = 'https://en.wikipedia.org/wiki/Talk:USB_flash_drive';
const wikimediaHistory = 'https://en.wikipedia.org/w/index.php?title=Talk:USB_flash_drive&action=history';
const wikimediaLicense = 'https://creativecommons.org/licenses/by-sa/4.0/';
export type ResearchSource = typeof researchSources[number];

export type ResearchScope = {
  mode: 'topic' | 'event';
  query: string;
  start_date: string;
  end_date: string;
  source: ResearchSource;
  language: 'en' | 'tr' | null;
  geography: TrendsCountry | null;
  content?: 'posts' | 'comments' | 'mixed';
  analyze_discussion?: true;
};

type ResearchRecord = {
  published_at: string;
  languages: string[];
  country: 'UNKNOWN';
  geography_attribution: 'unknown';
  kind: 'post' | 'comment';
  thread_reference: string | null;
} & ({source: 'bluesky'; reference: string} | {source: 'lemmy'; reference: string; source_language_id: number | null}
  | {source: 'wikimedia'; reference: string} | {source: 'fictional'; reference: null; text: string}
  | {source: 'civil_comments'; reference: null; article_id: string | null; publication_id: string | null});

export type ResearchResult = {
  evidence_package?: EvidencePackage;
  scope: ResearchScope;
  capabilities: {status: 'public_api' | 'synthetic' | 'historical'; languages: string[]; geography: false; max_items: 25 | 100};
  retrieved: number;
  outside_dates: number;
  invalid_records: number;
  duplicates: number;
  excluded_records: number;
  records: ResearchRecord[];
  discussion_analysis?: DiscussionAnalysis;
  source_document?: {page: string; history: string; license: 'CC BY-SA 4.0'; license_url: string; retrieved_at: string};
  dataset_document?: {source: string; license: 'CC0 1.0'; license_url: string; artifact: string; revision: string;
    sha256: string; examined: number; eligible: number; retrieved_at: string; screening: CivilScreening};
};

type DiscussionAnalysis = {
  evidence_rows: number[];
  topics_status: 'comparison' | 'nmf_only' | 'insufficient_texts' | 'insufficient_variation';
  topics: LocalAnalysisResult | null;
  expression_signals: ExpressionSignals;
  expression_evidence?: ExpressionEvidence;
  processing?: Processing;
};

export const researchErrors = {
  400: ['invalid_input'], 403: ['approval_required', 'forbidden', 'analysis_permission_unverified'], 404: ['not_found'], 413: ['too_large'],
  422: ['source_unavailable', 'discussion_missing'], 429: ['rate_limited', 'busy'],
  502: ['provider_auth_required', 'provider_denied', 'provider_unavailable', 'invalid_response', 'trends_contract_error'],
  503: ['trends_not_configured'], 504: ['provider_timeout'],
} as const satisfies Record<number, readonly string[]>;

export type ResearchError = typeof researchErrors[keyof typeof researchErrors][number] | 'unavailable';

export function isResearchEnabled(environment: string | undefined, flag: string | undefined) {
  return environment === 'development' && flag === '1';
}

export function researchErrorFor(status: number, value: unknown): ResearchError {
  const allowed: readonly string[] | undefined = researchErrors[status as keyof typeof researchErrors];
  return isObject(value) && typeof value.code === 'string' && allowed?.includes(value.code)
    ? value.code as ResearchError : 'unavailable';
}

export function researchUpstreamStatus(code: ResearchError, value: unknown): number | null {
  if (!isObject(value) || typeof value.upstream_status !== 'number') return null;
  const status = value.upstream_status;
  switch (code) {
    case 'provider_auth_required': return status === 401 ? status : null;
    case 'provider_denied': return status === 403 ? status : null;
    case 'rate_limited': return status === 429 ? status : null;
    case 'invalid_response':
    case 'discussion_missing':
    case 'provider_timeout': return status === 200 ? status : null;
    case 'provider_unavailable': return Number.isInteger(status) && status >= 100 && status <= 599 ? status : null;
    default: return null;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

const datePattern = /^\d{4}-\d{2}-\d{2}$/;
const dateTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+00:00$/;
const linkPattern = /^https:\/\/bsky\.app\/profile\/did:(?:plc:[a-z2-7]{24}|web:[A-Za-z0-9._:%-]{1,600})\/post\/[A-Za-z0-9._~:-]{1,128}$/;
const lemmyLink = /^https:\/\/lemmy\.world\/post\/[1-9][0-9]{0,9}$/;
const lemmyCommentLink = /^https:\/\/lemmy\.world\/comment\/[1-9][0-9]{0,9}$/;
const languagePattern = /^[a-z]{2,8}(?:-[a-z0-9]{1,8}){0,4}$/;

function isLemmyIdentifier(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 && value <= 2_147_483_647;
}

function isLemmyLink(value: unknown, pattern = lemmyLink): value is string {
  return typeof value === 'string' && pattern.test(value) && isLemmyIdentifier(Number(value.split('/').at(-1)));
}

function projectDiscussion(value: unknown, records: ResearchRecord[]): DiscussionAnalysis | null {
  if (!isObject(value) || !Array.isArray(value.evidence_rows)) return null;
  const rows: number[] = [];
  for (const index of value.evidence_rows) {
    if (!validCount(index, records.length - 1) || index <= (rows.at(-1) ?? -1) || !records[index]?.languages.includes('en')) return null;
    rows.push(index);
  }
  const {topics_status, topics, expression_signals} = value;
  if (!isExpressionSignals(expression_signals, rows.length)) return null;
  switch (topics_status) {
    case 'insufficient_texts':
      if (topics !== null || rows.length >= analysisLimits.minTexts) return null;
      break;
    case 'insufficient_variation':
      if (topics !== null || rows.length < analysisLimits.minTexts) return null;
      break;
    case 'comparison':
    case 'nmf_only':
      if (!isLocalAnalysisResult(topics, rows.length, 2, topics_status === 'comparison' ? 'both' : 'nmf') ||
          topics.expression_signals) return null;
      break;
    default: return null;
  }
  const result: DiscussionAnalysis = {evidence_rows: rows, topics_status, topics, expression_signals};
  if (value.expression_evidence !== undefined || value.processing !== undefined) {
    const checked = projectExpressionEvidence(value.expression_evidence, rows, records);
    const processing = projectProcessing(value.processing, rows.length, records.length);
    if (!checked || !processing) return null;
    const signals = {...expression_signals.emotions, ...expression_signals.needs, ...expression_signals.experiences};
    if (Object.entries(signals).some(([label, count]) => checked.counts[label as keyof typeof checked.counts] !== count)) return null;
    result.expression_evidence = checked;
    result.processing = processing;
  }
  return result;
}

function validCount(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max;
}

export function topicEvidence(topics: LocalAnalysisResult) {
  const methods = Object.entries(topics.methods);
  const uneven = methods.filter(([, group]) => {
    const assigned = group.groups.reduce((total, item) => total + item.size, 0);
    return assigned > 0 && group.groups.some(item => 10 * item.size < assigned);
  }).map(([name]) => name);
  return {
    uneven,
    weakAgreement: topics.agreement?.ari != null && topics.agreement.ari <= 0.1,
    limitedTerms: methods.some(([, method]) => method.groups.some(group => group.size > 0 && group.keywords.length === 0)),
    iterationLimit: methods.some(([, method]) => method.iteration_limit),
    weakSeparation: Object.entries(topics.separation ?? {}).filter(([, score]) => score !== null && score <= 0.1)
      .map(([method]) => method),
  };
}

function projectCivilScreening(value: unknown, excluded: number): CivilScreening | null {
  if (!isObject(value)) return null;
  const {length, privacy_or_markup, language, moderation, safety_labels} = value;
  if (!validCount(length, excluded) || !validCount(privacy_or_markup, excluded) || !validCount(language, excluded) ||
      !validCount(moderation, excluded) || !validCount(safety_labels, excluded) ||
      length + privacy_or_markup + language + moderation + safety_labels !== excluded) return null;
  return {length, privacy_or_markup, language, moderation, safety_labels};
}

function isArchiveIdentifier(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && /^[1-9][0-9]{0,11}$/.test(value));
}

// Build a new response from allowed fields, including when the local provider sends extra fields.
export function projectResearchResult(value: unknown): ResearchResult | null {
  if (!isObject(value) || !isObject(value.scope) || !isObject(value.capabilities) || !Array.isArray(value.records)) return null;
  const {mode, query, start_date, end_date, source, language, geography, content, analyze_discussion} = value.scope;
  const {retrieved, outside_dates, invalid_records, duplicates, excluded_records} = value;
  const {status, max_items} = value.capabilities;
  const historical = source === 'civil_comments';
  const expectedStatus = historical ? 'historical' : source === 'fictional' ? 'synthetic' : 'public_api';
  const countLimit = historical ? civilRows : 25;
  if ((mode !== 'topic' && mode !== 'event') ||
      (source !== 'bluesky' && source !== 'lemmy' && source !== 'fictional' && source !== 'wikimedia' && !historical) ||
      typeof query !== 'string' || !query.length || Array.from(query).length > 120 ||
      typeof start_date !== 'string' || !datePattern.test(start_date) ||
      typeof end_date !== 'string' || !datePattern.test(end_date) || start_date > end_date ||
      (language !== null && (source === 'lemmy' || source === 'wikimedia' || (language !== 'en' && language !== 'tr'))) || geography !== null ||
      (source === 'wikimedia' && (mode !== 'topic' || query !== wikimediaTitle || content !== 'comments')) ||
      (historical && (start_date < civilDates.first || end_date > civilDates.last || language !== 'en' ||
        content !== 'comments' || analyze_discussion !== true)) ||
      (content !== undefined && ((source !== 'fictional' && source !== 'lemmy' && source !== 'wikimedia' && !historical) ||
        (content !== 'posts' && content !== 'comments' && (source !== 'fictional' || content !== 'mixed')))) ||
      (analyze_discussion !== undefined && ((source !== 'fictional' && source !== 'wikimedia' && !historical) || analyze_discussion !== true)) ||
      status !== expectedStatus ||
      (max_items !== 25 && max_items !== 100) || max_items !== (historical ? 100 : 25) ||
      value.records.length > max_items || value.capabilities.geography !== false ||
      !validCount(retrieved, countLimit) || !validCount(outside_dates, countLimit) || !validCount(invalid_records, countLimit) ||
      !validCount(duplicates, countLimit) || !validCount(excluded_records, countLimit)) return null;
  const eligible = retrieved - outside_dates - invalid_records - duplicates - excluded_records;
  if (eligible < value.records.length || (!historical && eligible !== value.records.length)) return null;

  const records: ResearchRecord[] = [];
  const articleCounts = new Map<string | null, number>();
  for (const item of value.records) {
    if (!isObject(item) || item.source !== source || typeof item.published_at !== 'string' ||
        !dateTimePattern.test(item.published_at) || !Number.isFinite(Date.parse(item.published_at)) ||
        item.published_at.slice(0, 10) < start_date || item.published_at.slice(0, 10) > end_date ||
        item.country !== 'UNKNOWN' || item.geography_attribution !== 'unknown' ||
        !Array.isArray(item.languages) || item.languages.length > 3 ||
        !item.languages.every((tag: unknown) => typeof tag === 'string' && languagePattern.test(tag))) return null;
    const kind = item.kind ?? 'post';
    if ((kind !== 'post' && kind !== 'comment') || (content === 'posts' && kind !== 'post') ||
        (content === 'comments' && kind !== 'comment')) return null;
    const basic = {published_at: item.published_at, languages: item.languages, country: 'UNKNOWN', geography_attribution: 'unknown', kind} as const;
    if (source === 'bluesky' && kind === 'post' && typeof item.reference === 'string' && linkPattern.test(item.reference) &&
        !/\/\.{1,2}$/.test(item.reference)) {
      records.push({...basic, source, reference: item.reference, thread_reference: null});
    } else if (source === 'lemmy' && item.languages.length === 0 &&
        (item.source_language_id === null || isLemmyIdentifier(item.source_language_id))) {
      if (kind === 'comment' && content === 'comments' && isLemmyLink(item.reference, lemmyCommentLink) && isLemmyLink(item.thread_reference)) {
        records.push({...basic, source, reference: item.reference, source_language_id: item.source_language_id, thread_reference: item.thread_reference});
      } else if (kind === 'post' && isLemmyLink(item.reference)) {
        records.push({...basic, source, reference: item.reference, source_language_id: item.source_language_id, thread_reference: null});
      } else return null;
    } else if (source === 'wikimedia' && kind === 'comment' && item.reference === wikimediaPage && item.thread_reference === null &&
        item.languages.length === 1 && item.languages[0] === 'en') {
      records.push({...basic, source, reference: wikimediaPage, thread_reference: null});
    } else if (source === 'civil_comments' && kind === 'comment' && item.reference === null && item.thread_reference === null &&
        item.languages.length === 1 && item.languages[0] === 'en' &&
        isArchiveIdentifier(item.article_id) && isArchiveIdentifier(item.publication_id)) {
      const articleCount = (articleCounts.get(item.article_id) ?? 0) + 1;
      if (articleCount > 4) return null;
      articleCounts.set(item.article_id, articleCount);
      records.push({...basic, source, reference: null, thread_reference: null, article_id: item.article_id, publication_id: item.publication_id});
    } else if (source === 'fictional' && item.reference === null && typeof item.text === 'string' && [...item.text].length <= 8000) {
      records.push({...basic, source, reference: null, text: item.text, thread_reference: null});
    } else return null;
  }
  const result: ResearchResult = {scope: {mode, query, start_date, end_date, source, language, geography, content, analyze_discussion},
    capabilities: {status: expectedStatus, languages: historical ? ['en'] : source === 'lemmy' || source === 'wikimedia' ? [] : ['en', 'tr'],
      geography: false, max_items},
    retrieved, outside_dates, invalid_records, duplicates, excluded_records, records};
  if (source === 'wikimedia') {
    const doc = value.source_document;
    if (!isObject(doc) || doc.page !== wikimediaPage || doc.history !== wikimediaHistory || doc.license !== 'CC BY-SA 4.0' ||
        doc.license_url !== wikimediaLicense || typeof doc.retrieved_at !== 'string' ||
        !dateTimePattern.test(doc.retrieved_at) || !Number.isFinite(Date.parse(doc.retrieved_at))) return null;
    result.source_document = {page: doc.page, history: doc.history, license: doc.license, license_url: doc.license_url, retrieved_at: doc.retrieved_at};
  } else if (value.source_document !== undefined) return null;
  if (historical) {
    const doc = value.dataset_document;
    if (!isObject(doc) || doc.source !== civilSource || doc.license !== 'CC0 1.0' || doc.license_url !== civilLicense ||
        doc.artifact !== civilArtifact || doc.revision !== civilRevision || doc.sha256 !== civilChecksum ||
        doc.examined !== civilRows || doc.eligible !== eligible || typeof doc.retrieved_at !== 'string' ||
        !dateTimePattern.test(doc.retrieved_at) || !Number.isFinite(Date.parse(doc.retrieved_at))) return null;
    const screening = projectCivilScreening(doc.screening, excluded_records);
    if (!screening) return null;
    result.dataset_document = {source: doc.source, license: doc.license, license_url: doc.license_url,
      artifact: doc.artifact, revision: doc.revision, sha256: doc.sha256, examined: doc.examined,
      eligible: doc.eligible, retrieved_at: doc.retrieved_at, screening};
  } else if (value.dataset_document !== undefined) return null;
  if (analyze_discussion) {
    const checked = projectDiscussion(value.discussion_analysis, records);
    if (!checked) return null;
    result.discussion_analysis = checked;
  } else if (value.discussion_analysis !== undefined) return null;
  if (content === undefined) delete result.scope.content;
  if (analyze_discussion === undefined) delete result.scope.analyze_discussion;
  if (value.evidence_package !== undefined) {
    const evidence = projectEvidencePackage(value.evidence_package);
    if (!evidence || evidence.scope.source !== source || evidence.scope.mode !== mode || evidence.scope.query !== query ||
        evidence.scope.start_date !== start_date || evidence.scope.end_date !== end_date ||
        evidence.scope.analyzed_documents !== (result.discussion_analysis?.evidence_rows.length ?? 0) ||
        evidence.facts.find(fact => fact.metric === 'sample')?.values.selected !== records.length) return null;
    result.evidence_package = evidence;
  }
  return result;
}
