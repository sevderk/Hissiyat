import {importTrendsCsv, decodeTrendsCsv, readExploreLink, summarizeInterest, maxTrendsCsvBytes} from './trends-csv.ts';

export type ImportedEvidenceInput =
  | {source: 'historical'; question: 'wages' | 'job_opportunities'}
  | {source: 'csv'; file: File; url: string; region: string; mode: 'topic' | 'event'};

// This runs in the local Next server. Browser-supplied statistics are never used.
export function csvAggregateInput(input: unknown, hash: (bytes: Uint8Array) => string) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('invalid_evidence');
  const v = input as Record<string, unknown>;
  if (Object.keys(v).sort().join() !== 'csv_base64,mode,region,source,url' || v.source !== 'csv' ||
      typeof v.csv_base64 !== 'string' || !v.csv_base64 || v.csv_base64.length > Math.ceil(maxTrendsCsvBytes / 3) * 4 ||
      typeof v.url !== 'string' || typeof v.region !== 'string' || !['TR', 'US', 'GB', 'worldwide'].includes(v.region) ||
      v.mode !== 'topic' && v.mode !== 'event') throw new Error('invalid_evidence');
  const raw = Uint8Array.from(atob(v.csv_base64), character => character.charCodeAt(0));
  if (btoa(Array.from(raw, character => String.fromCharCode(character)).join('')) !== v.csv_base64 || raw.length > maxTrendsCsvBytes) throw new Error('invalid_evidence');
  const scope = readExploreLink(v.url);
  const data = importTrendsCsv(decodeTrendsCsv(raw.buffer), scope);
  const line = data.series.find(line => line.region === v.region);
  if (!line) throw new Error('invalid_evidence');
  const summary = summarizeInterest(line.points);
  const extreme = (value: {date: string; value: number} | undefined) => value ? {...value, periods: 1} : null;
  return {source: 'csv', url: data.url, region: v.region, mode: v.mode, sha256: hash(raw), interval: data.interval,
    observations: line.points.length, observed: summary.observed, missing: summary.missing, suppressed: summary.suppressed,
    ambiguous_zero: line.points.filter(point => point.value === 0).length,
    first_period: line.points[0].date, last_period: line.points.at(-1)!.date,
    peak: summary.peak, trough: summary.trough, first: extreme(summary.first), last: extreme(summary.last), change: summary.change};
}
