import assert from 'node:assert/strict';
import {test} from 'node:test';
import {isSearchInterest, isTextAnalysis} from '../src/lib/demo-contract.ts';

const envelope = {demo: true, contract_version: '1.0', provenance: 'fixed_fictional_aggregates'};
const text = {
  ...envelope,
  cohort: 'general',
  source_category: 'human_experience',
  method: 'fictional_document_label_counts',
  limitations: ['fictional_only', 'cohorts_not_comparable_for_prevalence'],
  document_count: 4,
  multi_label: true,
  emotion_basis: 'explicit_expression',
  groups: {
    topics: [{key: 'education', count: 4}, {key: 'reskilling', count: 2}],
    emotions: [{key: 'hope', count: 1}],
    needs: [],
    experiences: []
  }
};
const search = {
  ...envelope,
  source_category: 'search_interest',
  method: 'fictional_relative_index',
  limitations: ['fictional_only', 'index_not_volume'],
  query: 'orbital_greenhouse_apprenticeships',
  geography: 'fictional_harbor_district',
  granularity: 'weekly',
  scale: [0, 100],
  points: [
    {date: '2025-01-06', status: 'observed', value: 0},
    {date: '2025-01-13', status: 'missing', value: null},
    {date: '2025-01-20', status: 'suppressed', value: null}
  ]
};

test('text accepts overlapping categories and validates the selected denominator', () => {
  assert.equal(isTextAnalysis(text, 'general'), true);
  assert.equal(isTextAnalysis(text, 'uncertainty-enriched'), false);
  assert.equal(isTextAnalysis({...text, document_count: 3}, 'general'), false);
  assert.equal(isTextAnalysis({...text, document_count: 0}, 'general'), false);
});

test('text rejects malformed or extra data and accepts a well-formed empty cohort', () => {
  for (const value of [
    {...text, demo: false},
    {...text, private_records: []},
    {...text, groups: {...text.groups, topics: [{key: 'hope', count: 1}]}},
    {...text, groups: {...text.groups, topics: [text.groups.topics[0], text.groups.topics[0]]}},
    {...text, groups: {...text.groups, topics: [{key: 'education', count: 1, private_text: 'fixture'}]}}
  ]) assert.equal(isTextAnalysis(value, 'general'), false);
  const groups = {topics: [], emotions: [], needs: [], experiences: []};
  assert.equal(isTextAnalysis({...text, document_count: 0, groups}, 'general'), true);
});

test('search distinguishes observed zero from missing and suppressed and accepts empty series', () => {
  assert.equal(isSearchInterest(search), true);
  assert.equal(isSearchInterest({...search, points: []}), true);
  assert.equal(isSearchInterest({...search, points: [{...search.points[1], value: 0}]}), false);
  assert.equal(isSearchInterest({...search, points: [{...search.points[2], value: 0}]}), false);
  assert.equal(isSearchInterest({...search, points: [{...search.points[0], value: null}]}), false);
});

test('search rejects a mismatched scale, calendar, or source contract', () => {
  for (const value of [
    {...search, scale: [0, 10]},
    {...search, points: [search.points[0], search.points[2]]},
    {...search, points: [...search.points].reverse()},
    {...search, points: [{...search.points[0], date: '2025-02-31'}]},
    {...search, points: [{...search.points[0], date: '2025-01-07'}]},
    {...search, points: [{...search.points[0], value: 101}]},
    {...search, query: 'unexpected'},
    {...search, cohort: 'general'}
  ]) assert.equal(isSearchInterest(value), false);
});
