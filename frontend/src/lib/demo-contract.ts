export const cohorts = ['general', 'uncertainty-enriched'] as const;
export type Cohort = (typeof cohorts)[number];

export const categories = {
  topics: ['education', 'career_paths', 'job_market', 'reskilling'],
  emotions: ['hope', 'concern', 'frustration', 'relief'],
  needs: ['guidance', 'information', 'support', 'opportunities'],
  experiences: ['study_choice', 'job_search', 'career_change', 'skills_training']
} as const;

export type Group = keyof typeof categories;
type Category = (typeof categories)[Group][number];
type CategoryCount = {key: Category; count: number};

export type TextAnalysis = {
  cohort: Cohort;
  document_count: number;
  groups: Record<Group, CategoryCount[]>;
};

export type InterestPoint = {
  date: string;
  status: 'observed' | 'missing' | 'suppressed';
  value: number | null;
};

export type SearchInterest = {points: InterestPoint[]};

const groups = Object.keys(categories) as Group[];
const envelope = {
  demo: true,
  contract_version: '1.0',
  provenance: 'fixed_fictional_aggregates'
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function keys(value: Record<string, unknown>, expected: readonly string[]) {
  return Object.keys(value).length === expected.length && expected.every((key) => Object.hasOwn(value, key));
}

function count(value: unknown, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= max;
}

function literalArray(value: unknown, ...expected: (string | number)[]) {
  return Array.isArray(value) && value.length === expected.length &&
    expected.every((entry, index) => value[index] === entry);
}

function matches(value: Record<string, unknown>, expected: Record<string, unknown>) {
  return Object.entries(expected).every(([key, entry]) => value[key] === entry);
}

export function isCohort(value: unknown): value is Cohort {
  return value === 'general' || value === 'uncertainty-enriched';
}

export function isTextAnalysis(value: unknown, cohort: Cohort): value is TextAnalysis {
  const fixed = {
    ...envelope,
    source_category: 'human_experience',
    method: 'fictional_document_label_counts',
    multi_label: true,
    emotion_basis: 'explicit_expression',
    cohort
  };
  if (!record(value) || !keys(value, [...Object.keys(fixed), 'limitations', 'document_count', 'groups']) ||
      !matches(value, fixed) || !literalArray(value.limitations, 'fictional_only', 'cohorts_not_comparable_for_prevalence') ||
      !count(value.document_count, 100_000) || !record(value.groups) || !keys(value.groups, groups)) return false;
  const denominator = value.document_count;
  const categoryGroups = value.groups;
  return groups.every((group) => {
    const entries = categoryGroups[group];
    const allowed: readonly string[] = categories[group];
    if (!Array.isArray(entries) || entries.length > allowed.length || (!denominator && entries.length)) return false;
    const seen = new Set<string>();
    for (const entry of entries) {
      if (!record(entry) || !keys(entry, ['key', 'count']) || typeof entry.key !== 'string' ||
          !allowed.includes(entry.key) || seen.has(entry.key) || !count(entry.count, denominator)) return false;
      seen.add(entry.key);
    }
    return true;
  });
}

export function isSearchInterest(value: unknown): value is SearchInterest {
  const fixed = {
    ...envelope,
    source_category: 'search_interest',
    method: 'fictional_relative_index',
    query: 'orbital_greenhouse_apprenticeships',
    geography: 'fictional_harbor_district',
    granularity: 'weekly'
  };
  if (!record(value) || !keys(value, [...Object.keys(fixed), 'limitations', 'scale', 'points']) ||
      !matches(value, fixed) || !literalArray(value.limitations, 'fictional_only', 'index_not_volume') ||
      !literalArray(value.scale, 0, 100) || !Array.isArray(value.points) || value.points.length > 52) return false;
  let previous: number | undefined;
  for (const point of value.points) {
    if (!record(point) || !keys(point, ['date', 'status', 'value']) || typeof point.date !== 'string' ||
        !/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(point.date)) return false;
    const date = new Date(point.date + 'T00:00:00Z');
    const timestamp = date.getTime();
    if (!Number.isFinite(timestamp) || date.toISOString().slice(0, 10) !== point.date || date.getUTCDay() !== 1 ||
        (previous !== undefined && timestamp - previous !== 7 * 86_400_000)) return false;
    if (point.status === 'observed' ? !count(point.value, 100) :
      (point.status !== 'missing' && point.status !== 'suppressed') || point.value !== null) return false;
    previous = timestamp;
  }
  return true;
}
