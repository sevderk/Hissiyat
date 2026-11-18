import {type TrendPoint, cadences} from './trends-research.ts';

export const maxTrendsCsvBytes = 256 * 1024;
type Cadence = typeof cadences[number];
type ExportScope = {term: string; start: string; end: string; regions: string[]; url: string};
export type TrendsExport = ExportScope & {
  source: 'google_trends_website_csv';
  measurement: 'request_relative_0_to_100';
  interval: Cadence;
  series: {region: string; points: TrendPoint[]}[];
};

export class TrendsCsvError extends Error {
  readonly code: 'link' | 'scope' | 'file' | 'encoding' | 'format' | 'structure' | 'metadata' |
    'periods' | 'values' | 'size' | 'parser';

  constructor(code: TrendsCsvError['code']) {
    super(code);
    this.code = code;
  }
}

const DAY = 86400000;
const layouts = [
  {category: 'Category: All categories', periods: {Day: 'daily', Week: 'weekly', Month: 'monthly', Year: 'yearly'},
    names: new Intl.DisplayNames('en-US', {type: 'region', fallback: 'none'}), worldwide: 'Worldwide'},
  {category: 'Kategori: Tüm kategoriler', periods: {Gün: 'daily', Hafta: 'weekly', Ay: 'monthly', Yıl: 'yearly'},
    names: new Intl.DisplayNames('tr', {type: 'region', fallback: 'none'}), worldwide: 'Dünya geneli'},
] as const satisfies {category: string; periods: Record<string, Cadence>; names: Intl.DisplayNames; worldwide: string}[];
const countryNames = new Intl.DisplayNames('en-US', {type: 'region', fallback: 'none'});
const notCountry = new Set(['AC', 'CP', 'DG', 'EA', 'EU', 'EZ', 'IC', 'QO', 'TA', 'UN', 'XA', 'XB', 'XK', 'ZZ']);
const allowedParams = new Set(['date', 'geo', 'q', 'hl', 'cat', 'gprop']);

function canonicalDate(value: string): string | null {
  if (!/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(value + 'T00:00:00Z');
  return Number.isFinite(+parsed) && parsed.toISOString().slice(0, 10) === value ? value : null;
}

function validCountry(code: string) {
  return /^[A-Z]{2}$/.test(code) && !notCountry.has(code) &&
    new Intl.Locale('und-' + code).region === code && countryNames.of(code) !== undefined;
}

export function readExploreLink(input: string, today = new Date().toISOString().slice(0, 10)): ExportScope {
  let url: URL;
  try {
    if (input.length > 2048) throw new Error();
    url = new URL(input);
  } catch {
    throw new TrendsCsvError('link');
  }
  if (url.origin !== 'https://trends.google.com' || url.pathname !== '/trends/explore' ||
      url.username || url.password || url.hash ||
      [...url.searchParams.keys()].some(key => !allowedParams.has(key) || url.searchParams.getAll(key).length !== 1)) {
    throw new TrendsCsvError('link');
  }
  const params = url.searchParams;
  if ((params.get('cat') ?? '0') !== '0' || (params.get('gprop') ?? '') !== '' ||
      !/^[a-z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}$/.test(params.get('hl') ?? 'en')) throw new TrendsCsvError('scope');

  const terms = (params.get('q') ?? '').split(',');
  const term = terms[0];
  if (terms.length > 2 || terms.some(other => other !== term) ||
      term.trim() !== term || term.length < 2 || term.length > 120 ||
      !/^[\p{L}\p{M}\p{N}][\p{L}\p{M}\p{N}'’ -]+$/u.test(term)) throw new TrendsCsvError('scope');

  const regions = (params.get('geo') ?? '').split(',').map(code => code || 'worldwide');
  if (regions.length !== terms.length || new Set(regions).size !== regions.length ||
      regions.some(code => !validCountry(code) && !(regions.length === 1 && code === 'worldwide'))) throw new TrendsCsvError('scope');

  const dates = (params.get('date') ?? '').split(',');
  const [start, end, ...extra] = dates[0].split(' ');
  if ((dates.length !== 1 && dates.length !== terms.length) || dates.some(range => range !== dates[0]) ||
      extra.length || !canonicalDate(start) || !canonicalDate(end) || start < '2004-01-01' || end >= today ||
      Date.parse(end) - Date.parse(start) < 29 * DAY) throw new TrendsCsvError('scope');
  return {term, start, end, regions, url: url.href};
}

function readRow(line: string): string[] {
  const row = [];
  let remaining = line;
  while (true) {
    const cell = /^(?:"((?:[^"]|"")*)"|([^",]*))(,|$)/.exec(remaining);
    if (!cell) throw new TrendsCsvError('format');
    row.push(cell[1]?.replaceAll('""', '"') ?? cell[2]);
    if (!cell[3]) return row;
    if (row.length === 3) throw new TrendsCsvError('format');
    remaining = remaining.slice(cell[0].length);
  }
}

function periodStart(value: string, interval: Cadence) {
  const expanded = interval === 'monthly' && /^\d{4}-\d{2}$/.test(value) ? value + '-01' :
    interval === 'yearly' && /^\d{4}$/.test(value) ? value + '-01-01' : value;
  if (!canonicalDate(expanded) || (interval === 'monthly' && !expanded.endsWith('-01')) ||
      (interval === 'yearly' && !expanded.endsWith('-01-01'))) throw new TrendsCsvError('periods');
  return expanded;
}

function nextPeriod(value: string, interval: Cadence) {
  const next = new Date(value + 'T00:00:00Z');
  if (interval === 'monthly') next.setUTCMonth(next.getUTCMonth() + 1);
  else if (interval === 'yearly') next.setUTCFullYear(next.getUTCFullYear() + 1);
  else next.setUTCDate(next.getUTCDate() + (interval === 'weekly' ? 7 : 1));
  return next.toISOString().slice(0, 10);
}

function point(date: string, raw: string): TrendPoint {
  if (raw === '') return {date, value: null, status: 'missing'};
  if (raw === '<1') return {date, value: null, status: 'suppressed'};
  if (!/^(?:0|[1-9]\d{0,2})(?:\.\d{1,6})?$/.test(raw) || Number(raw) > 100) throw new TrendsCsvError('values');
  return {date, value: Number(raw), status: 'observed'};
}

function columnMatches(column: string, term: string, region: string, layout: typeof layouts[number]) {
  const area = region === 'worldwide' ? layout.worldwide : layout.names.of(region);
  const label = column.normalize('NFC');
  const query = term.normalize('NFC');
  return label === `${query}: (${area})` ||
    (layout === layouts[0] && region === 'TR' && label === `${query}: (Turkey)`);
}

export function decodeTrendsCsv(bytes: ArrayBuffer): string {
  try {
    return new TextDecoder('utf-8', {fatal: true}).decode(bytes);
  } catch {
    throw new TrendsCsvError('encoding');
  }
}

export function importTrendsCsv(csv: string, scope: ExportScope): TrendsExport {
  if (csv.length > maxTrendsCsvBytes || new TextEncoder().encode(csv).length > maxTrendsCsvBytes) throw new TrendsCsvError('size');
  if (/[\0\u202a-\u202e\u2066-\u2069]/.test(csv)) throw new TrendsCsvError('format');
  const lines = csv.replace(/^\uFEFF/, '').replace(/(?:\r?\n)+$/, '').split(/\r?\n/);
  const category = readRow(lines[0].normalize('NFC'));
  const layout = layouts.find(item => category.length === 1 && item.category === category[0]);
  if (!layout) throw new TrendsCsvError('structure');
  const headerIndex = lines.findIndex((line, index) => index > 0 && line !== '');
  if (headerIndex === -1) throw new TrendsCsvError('structure');
  const [dateColumn, ...columns] = readRow(lines[headerIndex].normalize('NFC'));
  const periods: Record<string, Cadence> = layout.periods;
  if (!Object.hasOwn(periods, dateColumn) || !columns.length) throw new TrendsCsvError('structure');
  const interval = periods[dateColumn];
  if (columns.length !== scope.regions.length || columns.some((column, index) =>
    !columnMatches(column, scope.term, scope.regions[index], layout))) throw new TrendsCsvError('metadata');

  const rows = lines.slice(headerIndex + 1);
  if (rows.length === 0) throw new TrendsCsvError('structure');
  if (rows.length > 2000) throw new TrendsCsvError('size');
  const series = scope.regions.map(region => ({region, points: [] as TrendPoint[]}));
  let previous = '';
  for (const row of rows) {
    const [dateText, ...values] = readRow(row);
    if (values.length !== columns.length) throw new TrendsCsvError('format');
    const date = periodStart(dateText, interval);
    if (date > scope.end || nextPeriod(date, interval) <= scope.start) throw new TrendsCsvError('metadata');
    if (previous && nextPeriod(previous, interval) !== date) throw new TrendsCsvError('periods');
    values.forEach((value, index) => series[index].points.push(point(date, value)));
    previous = date;
  }
  return {...scope, source: 'google_trends_website_csv', measurement: 'request_relative_0_to_100', interval, series};
}

export function summarizeInterest(points: TrendPoint[]) {
  const observed = points.flatMap(({date, value}) => value === null ? [] : [{date, value}]);
  const extreme = (value: number) => {
    const ties = observed.filter(point => point.value === value);
    return ties[0] ? {...ties[0], periods: ties.length} : null;
  };
  const first = observed[0];
  const last = observed.at(-1);
  return {
    observed: observed.length, missing: points.filter(point => point.status === 'missing').length,
    suppressed: points.filter(point => point.status === 'suppressed').length,
    peak: extreme(Math.max(...observed.map(point => point.value))),
    trough: extreme(Math.min(...observed.map(point => point.value))), first, last,
    change: first && last && first !== last ? Math.round((last.value - first.value) * 1e6) / 1e6 : null,
  };
}

export function compareInterest(data: TrendsExport) {
  const [left, right] = data.series;
  if (!right) return null;
  const comparison = {leftHigher: 0, rightHigher: 0, equal: 0, aligned: 0};
  left.points.forEach((point, index) => {
    const other = right.points[index];
    if (point.value === null || other.value === null) return;
    comparison.aligned++;
    if (point.value > other.value) comparison.leftHigher++;
    else if (point.value < other.value) comparison.rightHigher++;
    else comparison.equal++;
  });
  return comparison;
}
