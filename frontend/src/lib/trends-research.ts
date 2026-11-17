export const cadences = ['daily', 'weekly', 'monthly', 'yearly'] as const;
export type TrendPoint = {date: string; status: 'observed' | 'missing' | 'suppressed'; value: number | null};
export type TrendsPreview = {
  source: 'google_trends_research' | 'fictional_fixture'; term: 'career'; geography: string;
  granularity: typeof cadences[number]; points: TrendPoint[];
};

export function isTrendsPreviewEnabled(environment: string | undefined, setting: string | undefined) {
  return environment === 'development' && setting === '1';
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
