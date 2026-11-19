import {projectEvidencePackage, type EvidencePackage} from './research-interpretation.ts';

export const cadences = ['daily', 'weekly', 'monthly', 'yearly'] as const;
export type TrendPoint = {date: string; status: 'observed' | 'missing' | 'suppressed'; value: number | null};
export type TrendsPreview = {
  source: 'google_trends_research' | 'fictional_fixture'; term: 'career'; geography: string;
  granularity: typeof cadences[number]; points: TrendPoint[];
};
export const trendsCountries = ['TR', 'US', 'GB'] as const;
export type TrendsCountry = typeof trendsCountries[number];
const metadataNames = ['geo', 'region', 'regionCode', 'geography', 'granularity', 'aggregation', 'status', 'valueStatus',
  'isMissing', 'isSuppressed', 'hasData', 'metadata', 'scale', 'unit'] as const;
type MetadataName = typeof metadataNames[number];
type OfficialTrendsSummary = {
  geography: TrendsCountry; cadence: typeof cadences[number]; first_period: string; last_period: string;
  nonzero: number; ambiguous_zero: number; missing: number; suppressed: number;
  peak_period: string | null; peak_ties: number; direction: 'increased' | 'decreased' | 'unchanged' | 'insufficient';
};
export type OfficialTrendsResult = {
  evidence_package?: EvidencePackage;
  source: 'google_trends_research' | 'fictional_trends_research'; mode: 'topic' | 'event'; term: string;
  requested_geography: TrendsCountry; start_month: string; end_month: string; point_count: number;
  date_kind: 'string' | null; value_kind: 'integer' | 'decimal' | null; metadata_fields: MetadataName[];
  measurement: 'consistently_scaled_search_interest' | null; summary: OfficialTrendsSummary | null;
};

function count(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max;
}

function validPeriod(value: unknown): value is string {
  if (typeof value !== 'string' || !/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + 'T00:00:00Z');
  return Number.isFinite(+date) && date.toISOString().slice(0, 10) === value;
}

function isSummary(value: unknown, scope: Pick<OfficialTrendsResult, 'requested_geography' | 'start_month' | 'end_month' | 'point_count'>): value is OfficialTrendsSummary {
  if (!hasFields(value, ['geography', 'cadence', 'first_period', 'last_period', 'nonzero', 'ambiguous_zero', 'missing',
    'suppressed', 'peak_period', 'peak_ties', 'direction'])) return false;
  const {first_period, last_period, nonzero, ambiguous_zero, missing, suppressed, peak_period, peak_ties, direction} = value;
  return value.geography === scope.requested_geography && cadences.some(cadence => cadence === value.cadence) &&
    validPeriod(first_period) && validPeriod(last_period) && first_period <= last_period &&
    first_period.slice(0, 7) >= scope.start_month && last_period.slice(0, 7) <= scope.end_month &&
    count(nonzero, scope.point_count) && count(ambiguous_zero, scope.point_count) &&
    count(missing, scope.point_count) && count(suppressed, scope.point_count) &&
    nonzero + ambiguous_zero + missing + suppressed === scope.point_count &&
    count(peak_ties, nonzero) && (nonzero === 0 ? peak_ties === 0 && peak_period === null :
      peak_ties > 0 && validPeriod(peak_period) && first_period <= peak_period && peak_period <= last_period) &&
    (nonzero < 2 ? direction === 'insufficient' : direction === 'increased' || direction === 'decreased' || direction === 'unchanged');
}

export function projectOfficialTrends(value: unknown): OfficialTrendsResult | null {
  let evidence: EvidencePackage | undefined;
  if (typeof value === 'object' && value !== null && 'evidence_package' in value) {
    const {evidence_package, ...rest} = value;
    const checked = projectEvidencePackage(evidence_package);
    const projected = projectOfficialTrends(rest);
    if (!checked || !projected || checked.scope.source !== 'google_trends' || checked.scope.query !== projected.term ||
        checked.scope.mode !== projected.mode || checked.scope.start_date !== projected.start_month ||
        checked.scope.end_date !== projected.end_month || checked.scope.geography !== (projected.summary?.geography ?? 'UNKNOWN')) return null;
    evidence = checked;
    return {...projected, evidence_package: evidence};
  }
  if (!hasFields(value, ['source', 'mode', 'term', 'requested_geography', 'start_month', 'end_month', 'point_count',
    'date_kind', 'value_kind', 'metadata_fields', 'measurement', 'summary'])) return null;
  const {source, mode, term, requested_geography, start_month, end_month, point_count,
    date_kind, value_kind, metadata_fields, measurement, summary} = value;
  if ((source !== 'google_trends_research' && source !== 'fictional_trends_research') || (mode !== 'event' && mode !== 'topic') ||
      typeof term !== 'string' || term.length < 2 || term.length > 120 ||
      (requested_geography !== 'TR' && requested_geography !== 'US' && requested_geography !== 'GB') ||
      typeof start_month !== 'string' || !validPeriod(start_month + '-01') ||
      typeof end_month !== 'string' || !validPeriod(end_month + '-01') || start_month > end_month ||
      !count(point_count, 2000) || point_count === 0 ||
      (date_kind !== 'string' && date_kind !== null) || (value_kind !== 'integer' && value_kind !== 'decimal' && value_kind !== null) ||
      !Array.isArray(metadata_fields) || metadata_fields.length > metadataNames.length ||
      new Set(metadata_fields).size !== metadata_fields.length ||
      !metadata_fields.every(field => metadataNames.some(known => known === field))) return null;
  if (measurement !== null && measurement !== 'consistently_scaled_search_interest') return null;
  if (summary === null ? measurement !== null : measurement === null ||
      !isSummary(summary, {requested_geography, start_month, end_month, point_count})) return null;
  return {source, mode, term, requested_geography, start_month, end_month, point_count,
    date_kind, value_kind, metadata_fields, measurement, summary: summary as OfficialTrendsSummary | null};
}

export function isTrendsPreviewEnabled(environment: string | undefined, setting: string | undefined) {
  return environment === 'development' && setting === '1';
}

export function trendPath(points: TrendPoint[], x: (index: number) => number, y: (value: number) => number) {
  return points.map(({value}, index) => value === null ? '' :
    (index > 0 && points[index - 1].value !== null ? 'L' : 'M') + x(index) + ' ' + y(value)).join(' ');
}

function hasFields(value: unknown, fields: string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) &&
    Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));
}

export function isTrendsPreview(value: unknown): value is TrendsPreview {
  if (!hasFields(value, ['source', 'term', 'geography', 'granularity', 'points']) ||
      (value.source !== 'google_trends_research' && value.source !== 'fictional_fixture') || value.term !== 'career' ||
      typeof value.geography !== 'string' || !/^(worldwide|[A-Z]{2}(-[A-Z0-9]{1,3})?)$/.test(value.geography) ||
      !cadences.some(cadence => cadence === value.granularity) || !Array.isArray(value.points) ||
      value.points.length < 1 || value.points.length > 2000) return false;
  let previous = '';
  for (const point of value.points) {
    if (!hasFields(point, ['date', 'status', 'value']) || typeof point.date !== 'string' ||
        !/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(point.date) || point.date <= previous) return false;
    const date = new Date(point.date + 'T00:00:00Z');
    if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== point.date) return false;
    if (point.status === 'observed' ? typeof point.value !== 'number' || !Number.isFinite(point.value) :
      (point.status !== 'missing' && point.status !== 'suppressed') || point.value !== null) return false;
    previous = point.date;
  }
  return true;
}
