import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {compareInterest, decodeTrendsCsv, importTrendsCsv, maxTrendsCsvBytes, readExploreLink, summarizeInterest} from '../src/lib/trends-csv.ts';
import {isTrendsPreview, trendPath} from '../src/lib/trends-research.ts';

const root = 'https://trends.google.com/trends/explore';
const range = '2025-01-05 2025-02-16';
const today = '2026-11-18';
const query = (q = 'career planning,career planning', geo = 'US,CA', date = range) =>
  `${root}?${new URLSearchParams({q, geo, date, hl: 'en-US'})}`;
const file = readFileSync(new URL('./fixtures/fictional-trends-comparison.csv', import.meta.url), 'utf8');
const scope = readExploreLink(query(), today);
const error = code => failure => failure?.code === code && failure.message === code;
const csv = (header, ...rows) => ['Category: All categories', '', header, ...rows].join('\n');

test('import retains the source link, filters, geography, actual cadence and shared scale', () => {
  const comparisonScope = readExploreLink(query('career planning,career planning', 'US,CA', `${range},${range}`), today);
  const result = importTrendsCsv('\uFEFF' + file.replaceAll('\n', '\r\n'), comparisonScope);
  assert.equal(result.url, comparisonScope.url);
  assert.equal(result.term, 'career planning');
  assert.deepEqual([result.start, result.end, result.interval], ['2025-01-05', '2025-02-16', 'weekly']);
  assert.equal(result.source, 'google_trends_website_csv');
  assert.equal(result.measurement, 'request_relative_0_to_100');
  assert.deepEqual(result.series.map(line => line.region), ['US', 'CA']);
  assert.deepEqual(result.series[0].points.slice(1, 4).map(point => [point.status, point.value]),
    [['observed', 0], ['missing', null], ['suppressed', null]]);
});

test('comparisons use jointly observed periods and keep fractional observations', () => {
  const result = importTrendsCsv(file, scope);
  assert.deepEqual(compareInterest(result), {leftHigher: 2, rightHigher: 1, equal: 1, aligned: 4});
  const summary = summarizeInterest(result.series[0].points);
  assert.equal(summary.first.value, 23.000001);
  assert.equal(summary.change, -3.000001);
  assert.equal(summary.observed, 5);
  assert.equal(summary.missing, 1);
  assert.equal(summary.suppressed, 1);
  assert.deepEqual(summary.peak, {date: '2025-02-02', value: 100, periods: 2});
  assert.deepEqual(summary.trough, {date: '2025-01-12', value: 0, periods: 1});
});

test('separate country files remain separate and a pair requires one set of aligned rows', () => {
  const first = readExploreLink(query('career planning', 'US'), today);
  const second = readExploreLink(query('career planning', 'CA'), today);
  const us = csv('Week,career planning: (United States)', '2025-01-05,100');
  const ca = csv('Week,career planning: (Canada)', '2025-01-05,100');
  assert.equal(compareInterest(importTrendsCsv(us, first)), null);
  assert.equal(compareInterest(importTrendsCsv(ca, second)), null);
  assert.throws(() => importTrendsCsv(us, scope), error('metadata'));
  assert.throws(() => importTrendsCsv(us + '\n' + ca, first), error('format'));
  assert.throws(() => importTrendsCsv(file.replace('(Canada)', '(Mexico)'), scope), error('metadata'));
  assert.throws(() => importTrendsCsv(file.replace('career planning:', 'job outlook:'), scope), error('metadata'));
});

test('links with credentials, other origins or ambiguous scopes fail with fixed codes', () => {
  for (const url of [query().replace('https://', 'https://user:fictional-secret@'),
    query().replace('trends.google.com', 'trends.google.com.example.invalid'), query() + '&key=fictional-secret',
    query() + '&geo=DE', query() + '#detail', query().replace('https://', 'http://')]) {
    assert.throws(() => readExploreLink(url, today), error('link'));
  }
  for (const url of [
    query('career planning,job outlook'), query(undefined, 'US,US'), query(undefined, 'US,ZZ'),
    query(undefined, 'US,US-CA'), query(undefined, 'US,'), query(undefined, 'US,CA', 'today 12-m'),
    query(undefined, 'US,CA', range + ',2025-01-06 2025-02-16'), query(undefined, 'US,CA', '2025-01-05 2025-01-20'),
    query(undefined, 'US,CA', '2025-02-30 2025-04-01'), query(undefined, 'US,CA', '2026-09-01 2026-11-18'),
    query('/m/fictional', 'US'), query() + '&gprop=youtube', query() + '&cat=12',
  ]) assert.throws(() => readExploreLink(url, today), error('scope'));
});

test('worldwide and Unicode terms require an explicit matching CSV header', () => {
  const world = readExploreLink(query('iş arama', ''), today);
  const result = importTrendsCsv(csv('Week,"iş arama: (Worldwide)"', '2025-01-05,100'), world);
  assert.equal(result.series[0].region, 'worldwide');
  assert.throws(() => importTrendsCsv(csv('Week,iş arama', '2025-01-05,100'), world), error('metadata'));
});

test('daily, monthly and annual periods use the calendar and preserve boundary buckets', () => {
  const settings = readExploreLink(query('career planning', 'TR', '2024-02-15 2025-03-15'), today);
  for (const [header, first, second, interval, expected] of [
    ['Day', '2024-02-29', '2024-03-01', 'daily', '2024-03-01'],
    ['Month', '2024-02', '2024-03', 'monthly', '2024-03-01'],
    ['Year', '2024', '2025', 'yearly', '2025-01-01'],
  ]) {
    const output = importTrendsCsv(csv(`${header},career planning: (Turkey)`, first + ',1', second + ',2'), settings);
    assert.equal(output.interval, interval);
    assert.equal(output.series[0].points[1].date, expected);
  }
});

test('rejects reordered, irregular and invalid periods rather than inventing coverage', () => {
  for (const date of ['2025-01-05', '2025-01-18', '2025-02-30', '2025-01-04']) {
    assert.throws(() => importTrendsCsv(file.replace('2025-01-12', date), scope), error('periods'));
  }
  assert.throws(() => importTrendsCsv(file.replace('2025-01-12', '2025-02-23'), scope), error('metadata'));
  assert.throws(() => importTrendsCsv(file.replace('Week,', 'Date,'), scope), error('structure'));
  assert.throws(() => importTrendsCsv(file.replace('All categories', 'Sensitive category'), scope), error('structure'));
});

test('censored or blank observations never become zero and gaps split both plot paths', () => {
  const data = importTrendsCsv(file, scope);
  const [left, right] = data.series.map(line => trendPath(line.points, index => index, value => value).trim());
  assert.equal(left, 'M0 23.000001 L1 0   M4 100 L5 100 L6 20');
  assert.equal(right, 'M0 25  M2 40  M4 60 L5 45 L6 20');
  const blank = importTrendsCsv(csv('Week,career planning: (United States),career planning: (Canada)',
    '2025-01-05,,<1', '2025-01-12,<1,'), scope);
  assert.deepEqual(compareInterest(blank), {leftHigher: 0, rightHigher: 0, equal: 0, aligned: 0});
  assert.equal(summarizeInterest(blank.series[0].points).peak, null);
  assert.equal(summarizeInterest(blank.series[0].points).change, null);
});

test('supports request-relative decimals without accepting numbers outside the scale', () => {
  for (const token of ['-1', '100.01', 'NaN', 'Infinity', '1e2', '0.0000001', 'N/A', '100 ', 'false', '=<PAYLOAD>']) {
    assert.throws(() => importTrendsCsv(file.replace('23.000001', token), scope), error('values'));
  }
  assert.throws(() => importTrendsCsv('a'.repeat(maxTrendsCsvBytes + 1), scope), error('size'));
});

test('CSV and the fictional API use distinct contracts and reject mismatched scales or raw fields', () => {
  const data = importTrendsCsv(file, scope);
  assert.equal(isTrendsPreview(data), false);
  const api = {source: 'fictional_fixture', term: 'career', geography: 'CA', granularity: 'daily',
    points: [{date: '2025-01-05', status: 'observed', value: 124.25}]};
  assert.equal(isTrendsPreview(api), true);
  assert.equal(isTrendsPreview({...api, key: 'fictional-confidential-content'}), false);
  assert.throws(() => importTrendsCsv(file.replace('23.000001', '124.25'), scope), error('values'));
});

test('original Turkish header, unquoted country column and ISO day rows work regardless of Explore link language', () => {
  const bytes = readFileSync(new URL('./fixtures/fictional-trends-turkish.csv', import.meta.url));
  const tr = decodeTrendsCsv(Uint8Array.from(bytes).buffer);
  const link = query('kurgusal araştırma', 'TR');
  for (const input of [link, link.replace('hl=en-US', 'hl=tr')]) {
    const result = importTrendsCsv(tr, readExploreLink(input, today));
    assert.equal(result.interval, 'daily');
    assert.equal(result.series[0].region, 'TR');
    assert.deepEqual(result.series[0].points.map(point => [point.status, point.value]),
      [['observed', 22], ['observed', 0], ['suppressed', null], ['missing', null], ['observed', 72]]);
  }
  assert.throws(() => importTrendsCsv(tr, readExploreLink(query('kurgusal araştırma', 'DE'), today)), error('metadata'));
  assert.throws(() => importTrendsCsv(tr.replace('kurgusal araştırma:', 'bambaşka terim:'), readExploreLink(link, today)), error('metadata'));
});

test('encoding, malformed rows, unsupported layouts and metadata disagreements have distinct error categories', () => {
  assert.throws(() => decodeTrendsCsv(new Uint8Array([0xc3, 0x28]).buffer), error('encoding'));
  assert.throws(() => importTrendsCsv(file.replace('23.000001,25', '"23.000001,25'), scope), error('format'));
  assert.throws(() => importTrendsCsv(file.replace('23.000001,25', '23.000001'), scope), error('format'));
  assert.throws(() => importTrendsCsv(file.replace('Week,', 'Gün,'), scope), error('structure'));
  assert.throws(() => importTrendsCsv(file.replace('(Canada)', '(Türkiye)'), scope), error('metadata'));
  assert.equal(importTrendsCsv(file.replace('Category: All categories', '"Category: All categories"'), scope).interval, 'weekly');
});

test('recognized Turkish period headers use the same calendar and keep the link geography', () => {
  const settings = readExploreLink(query('örnek konu', 'DE', '2024-02-15 2025-03-15'), today);
  for (const [header, first, second, interval] of [
    ['Hafta', '2024-02-11', '2024-02-18', 'weekly'],
    ['Ay', '2024-02', '2024-03', 'monthly'],
    ['Yıl', '2024', '2025', 'yearly'],
  ]) {
    const tr = ['Kategori: Tüm kategoriler', '', `${header},örnek konu: (Almanya)`, first + ',1', second + ',2'].join('\n');
    const result = importTrendsCsv(tr, settings);
    assert.equal(result.interval, interval);
    assert.equal(result.series[0].region, 'DE');
  }
});
