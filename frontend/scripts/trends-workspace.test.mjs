import assert from 'node:assert/strict';
import test from 'node:test';
import {projectOfficialTrends} from '../src/lib/trends-research.ts';

const shape = Object.freeze({
  source: 'google_trends_research', mode: 'topic', term: 'career', requested_geography: 'TR',
  start_month: '2026-09', end_month: '2026-10', point_count: 5, date_kind: 'string',
  value_kind: 'decimal', metadata_fields: ['geo', 'granularity', 'valueStatus'], measurement: null, summary: null,
});
const summary = Object.freeze({
  geography: 'TR', cadence: 'weekly', first_period: '2026-09-07', last_period: '2026-10-05',
  nonzero: 2, ambiguous_zero: 1, missing: 1, suppressed: 1, peak_period: '2026-10-05', peak_ties: 1, direction: 'increased',
});
const fixture = {...shape, source: 'fictional_trends_research', mode: 'event',
  measurement: 'consistently_scaled_search_interest', summary};

test('official response structure and authorized summary are separate contracts', () => {
  assert.deepEqual(projectOfficialTrends(shape), shape);
  assert.deepEqual(projectOfficialTrends(fixture), fixture);
  assert.equal(projectOfficialTrends({...shape, summary}), null);
  assert.equal(projectOfficialTrends({...shape, measurement: fixture.measurement}), null);
});

test('projection excludes credentials, raw periods and unrecognized metadata', () => {
  for (const bad of [
    {...shape, key: 'fictional-secret'}, {...shape, points: []},
    {...shape, metadata_fields: ['arbitrary_key']}, {...shape, metadata_fields: ['geo', 'geo']},
    {...fixture, summary: {...summary, points: []}},
    {...fixture, summary: {...summary, geography: 'US'}},
    {...fixture, summary: {...summary, missing: 2}},
    {...fixture, summary: {...summary, peak_period: '2026-10-06'}},
    {...fixture, summary: {...summary, first_period: '2026-08-31'}},
  ]) assert.equal(projectOfficialTrends(bad), null);
});
