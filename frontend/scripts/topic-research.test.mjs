import assert from 'node:assert/strict';
import test from 'node:test';
import {isResearchEnabled, projectResearchResult, researchErrorFor, researchUpstreamStatus, topicEvidence} from '../src/lib/topic-research.ts';

const marker = 'fictional confidential marker';
const valid = {
  scope: {mode: 'event', query: 'river festival', source: 'bluesky', start_date: '2026-11-05', end_date: '2026-11-16', language: 'en', geography: null},
  capabilities: {status: 'public_api', languages: ['en', 'tr'], geography: false, max_items: 25},
  retrieved: 1, outside_dates: 0, invalid_records: 0, duplicates: 0, excluded_records: 0,
  records: [{source: 'bluesky', published_at: '2026-11-10T12:00:00+00:00', languages: [], country: 'UNKNOWN',
    geography_attribution: 'unknown', kind: 'post', thread_reference: null,
    reference: 'https://bsky.app/profile/did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/post/abcdefg'}],
};

test('public response projects only scoped metadata and reconstructs the allowlisted response', () => {
  const input = {...valid, body: marker, records: [{...valid.records[0], text: marker, author: {displayName: marker}}]};
  assert.deepEqual(projectResearchResult(input), valid);
  assert.ok(!JSON.stringify(projectResearchResult(input)).includes(marker));
});

test('unexpected links, location attribution, counts and dates are rejected', () => {
  for (const fields of [{country: 'TR'}, {reference: 'javascript:alert(1)'},
    {reference: 'https://bsky.app/profile/did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/post/..'},
    {published_at: '2026-11-20T12:00:00+00:00'}, {languages: ['<script>']}]) {
    assert.equal(projectResearchResult({...valid, records: [{...valid.records[0], ...fields}]}), null);
  }
  assert.equal(projectResearchResult({...valid, retrieved: 2}), null);
});

test('only fixed errors survive and preview needs explicit development configuration', () => {
  assert.equal(researchErrorFor(429, {code: 'rate_limited', body: marker}), 'rate_limited');
  assert.equal(researchErrorFor(429, {code: marker}), 'unavailable');
  assert.equal(researchErrorFor(404, {code: 'rate_limited'}), 'unavailable');
  assert.equal(researchErrorFor(502, {code: 'provider_auth_required'}), 'provider_auth_required');
  assert.equal(researchUpstreamStatus('provider_auth_required', {upstream_status: 401, body: marker}), 401);
  assert.equal(researchUpstreamStatus('provider_denied', {upstream_status: 403}), 403);
  assert.equal(researchUpstreamStatus('provider_denied', {upstream_status: 401}), null);
  assert.equal(researchUpstreamStatus('provider_denied', {upstream_status: '403'}), null);
  assert.equal(researchUpstreamStatus('approval_required', {upstream_status: 403}), null);
  assert.equal(isResearchEnabled('production', '1'), false);
  assert.equal(isResearchEnabled('development', undefined), false);
  assert.equal(isResearchEnabled('development', '1'), true);
});

test('Lemmy preserves only local permalinks and native language metadata, including for restricted counts', () => {
  const reference = 'https://lemmy.world/post/2147483640';
  const row = {...valid.records[0], source: 'lemmy', reference, source_language_id: 37};
  const input = {...valid, scope: {...valid.scope, source: 'lemmy', language: null},
    capabilities: {...valid.capabilities, languages: []}, retrieved: 2, excluded_records: 1,
    records: [{...row, text: marker, thumbnail_url: 'https://example.invalid/image'}]};
  assert.deepEqual(projectResearchResult(input), {...input, records: [row]});
  for (const change of [{source_language_id: true}, {languages: ['tr']}, {reference: 'https://lemmy.world:443/post/2147483640'},
    {reference: 'https://lemmy.world.example.invalid/post/2147483640'}, {reference: `${reference}?next=example.invalid`}]) {
    assert.equal(projectResearchResult({...input, records: [{...row, ...change}]}), null);
  }
  assert.equal(projectResearchResult({...input, scope: {...input.scope, language: 'en'}}), null);
});

test('comment responses require an approved same-origin reference and parent thread', () => {
  const row = {...valid.records[0], source: 'lemmy', kind: 'comment', reference: 'https://lemmy.world/comment/2147483630',
    thread_reference: 'https://lemmy.world/post/2147483640', source_language_id: null};
  const input = {...valid, scope: {...valid.scope, source: 'lemmy', content: 'comments', language: null},
    capabilities: {...valid.capabilities, languages: []}, records: [{...row, text: marker}]};
  assert.deepEqual(projectResearchResult(input), {...input, records: [row]});
  assert.equal(projectResearchResult({...input, records: [{...row, thread_reference: 'https://example.invalid/post/1'}]}), null);
  assert.equal(projectResearchResult({...input, scope: {...input.scope, content: 'posts'}}), null);
  assert.equal(projectResearchResult({...input, discussion_analysis: {}}), null);
});

test('fictional analysis preserves cohort indices and drops model-only fields', () => {
  const row = {...valid.records[0], source: 'fictional', reference: null, languages: ['en'], text: 'invented text'};
  const scope = {...valid.scope, source: 'fictional', content: 'mixed', analyze_discussion: true};
  const signals = {submitted_texts: 1, emotions: {worry: 1, excitement: 0, frustration: 0, confidence: 0, curiosity: 0},
    needs: {information: 0, guidance: 0, support: 0}, experiences: {reported: 0}};
  const analysis = {evidence_rows: [0], topics_status: 'insufficient_texts', topics: null, expression_signals: signals};
  const input = {...valid, scope, capabilities: {...valid.capabilities, status: 'synthetic'}, records: [row],
    discussion_analysis: {...analysis, private_values: marker}};
  assert.deepEqual(projectResearchResult(input)?.discussion_analysis, analysis);
  assert.equal(projectResearchResult({...input, discussion_analysis: {...analysis, evidence_rows: [0, 0]}}), null);
  assert.equal(projectResearchResult({...input, discussion_analysis: {...analysis, evidence_rows: [1]}}), null);
  assert.equal(projectResearchResult({...input, discussion_analysis: {...analysis, topics_status: 'comparison'}}), null);
});

test('Wikimedia evidence is page-attributed and forwards aggregate data without raw comment fields', () => {
  const page = 'https://en.wikipedia.org/wiki/Talk:USB_flash_drive';
  const date = '2026-11-10T12:00:00+00:00';
  const row = {...valid.records[0], source: 'wikimedia', kind: 'comment', reference: page,
    thread_reference: null, languages: ['en'], published_at: date};
  const document = {page, history: 'https://en.wikipedia.org/w/index.php?title=Talk:USB_flash_drive&action=history',
    license: 'CC BY-SA 4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0/', retrieved_at: date};
  const scope = {...valid.scope, mode: 'topic', source: 'wikimedia', query: 'Talk:USB flash drive', content: 'comments', language: null};
  const input = {...valid, scope, capabilities: {...valid.capabilities, languages: []}, source_document: document,
    records: [{...row, text: marker, author: marker, identifier: marker}]};
  const result = projectResearchResult(input);
  assert.deepEqual(result?.source_document, document);
  assert.deepEqual(result?.records, [row]);
  assert.equal(projectResearchResult({...input, source_document: {...document, history: 'https://example.invalid'}}), null);
  assert.equal(projectResearchResult({...input, records: [{...row, reference: `${page}#FictionalEditor`}]}), null);
});

test('historical results separate archive, match, eligibility and analysis denominators', () => {
  const row = {source: 'civil_comments', reference: null, published_at: '2016-06-01T00:12:23.123456+00:00',
    languages: ['en'], country: 'UNKNOWN', geography_attribution: 'unknown', kind: 'comment',
    thread_reference: null, article_id: '45', publication_id: null};
  const signals = {submitted_texts: 1, emotions: {worry: 0, excitement: 0, frustration: 0, confidence: 0, curiosity: 0},
    needs: {information: 0, guidance: 0, support: 0}, experiences: {reported: 0}};
  const analysis = {evidence_rows: [25], topics_status: 'insufficient_texts', topics: null, expression_signals: signals};
  const records = Array.from({length: 26}, (_, index) => ({...row, article_id: String(index + 1)}));
  const document = {source: 'https://huggingface.co/datasets/google/jigsaw_unintended_bias', license: 'CC0 1.0',
    license_url: 'https://creativecommons.org/publicdomain/zero/1.0/', artifact: 'test_public_expanded.csv.gz',
    revision: '9beb047ad342ac2c3ac209d2d74e0b7c833fe294',
    sha256: 'a5a8fba390af3f17639b1bcef9b1c1b38373d3e45728f7eb814bfe5f3ea1c3d2', examined: 97320,
    eligible: 70, retrieved_at: '2026-11-18T12:00:00+00:00',
    screening: {length: 1, privacy_or_markup: 0, language: 0, moderation: 0, safety_labels: 1}};
  const input = {scope: {...valid.scope, source: 'civil_comments', query: 'work', content: 'comments',
    start_date: '2015-01-01', end_date: '2017-12-31', analyze_discussion: true},
  capabilities: {status: 'historical', languages: ['en'], geography: false, max_items: 100},
  retrieved: 75, outside_dates: 1, invalid_records: 1, duplicates: 1, excluded_records: 2,
  dataset_document: {...document, raw: marker}, discussion_analysis: analysis,
  records: records.map(record => ({...record, text: marker, author: marker}))};
  const result = projectResearchResult(input);
  assert.deepEqual(result?.records, records);
  assert.deepEqual(result?.dataset_document, document);
  assert.deepEqual(result?.discussion_analysis, analysis);
  for (const change of [
    {dataset_document: {...document, eligible: 75}},
    {dataset_document: {...document, sha256: marker}},
    {dataset_document: {...document, screening: {...document.screening, length: 2}}},
    {capabilities: {...input.capabilities, status: 'synthetic'}},
    {records: [{...row, reference: 'https://example.invalid'}]},
    {records: [{...row, country: 'US'}]},
    {records: [row, row, row, row, row]},
  ]) assert.equal(projectResearchResult({...input, ...change}), null);
});

test('diagnostics distinguish uneven groups, low chance-adjusted overlap and unavailable terms', () => {
  const group = (size, keywords = ['work']) => ({size, keywords});
  const topics = {methods: {nmf: {groups: [group(93), group(7, [])], unassigned: 0, iteration_limit: false},
    minilm: {groups: [group(62), group(38)], unassigned: 0, iteration_limit: false}},
  agreement: {ari: -0.0267, common_assigned: 100}};
  assert.deepEqual(topicEvidence(topics), {uneven: ['nmf'], weakAgreement: true, limitedTerms: true, iterationLimit: false});
  topics.agreement.ari = null;
  topics.methods.nmf.groups = [group(90), group(10)];
  topics.methods.minilm.iteration_limit = true;
  assert.deepEqual(topicEvidence(topics), {uneven: [], weakAgreement: false, limitedTerms: false, iterationLimit: true});
});
