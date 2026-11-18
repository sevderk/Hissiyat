import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {projectCivilComparison} from '../src/lib/civil-comparison.ts';

const input = JSON.parse(await readFile(new URL('../src/lib/civil-comparison-data.json', import.meta.url), 'utf8'));

test('curated aggregate comparison preserves paired denominators and unsupported legacy measures', () => {
  const report = projectCivilComparison(input);
  assert.ok(report);
  for (const question of Object.values(report.questions)) {
    assert.equal(question.selection.shared + question.selection.legacy_only, question.legacy.selected);
    assert.equal(question.selection.shared + question.selection.updated_only, question.updated.selected);
    assert.equal(question.legacy.counts.problem, null);
    assert.equal(question.legacy.evidence_spans, null);
    assert.equal(typeof question.updated.counts.problem, 'number');
    assert.ok(question.paired.documents <= question.selection.shared);
    assert.ok(question.updated.segments >= question.updated.analyzed);
  }
});

test('comparison rejects wrong provenance, scope, counters and unsupported legacy claims', () => {
  const mutations = [
    value => { value.dataset.sha256 = 'fictional invalid digest'; },
    value => { value.study_window[0] = '2014-01-01'; },
    value => { value.geography = 'TR'; },
    value => { value.questions.wages.query = 'a different query'; },
    value => { value.questions.wages.updated.analyzed = 101; },
    value => { value.questions.wages.selection.shared += 1; },
    value => { value.questions.wages.paired.documents = 101; },
    value => { value.questions.wages.paired.categories.worry.gained = 1; },
    value => { value.questions.wages.legacy.counts.problem = 0; },
    value => { value.questions.wages.updated.abstentions = {unexpected: 1}; },
    value => { value.questions.wages.updated.topics.separation.nmf = 2; },
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(input);
    mutate(changed);
    assert.equal(projectCivilComparison(changed), null);
  }
});

test('comparison projection drops fictional raw fields and publishes aggregate fields only', () => {
  const changed = structuredClone(input);
  const marker = 'FICTIONAL_PRIVATE_TEST_PAYLOAD';
  changed.raw = marker;
  changed.questions.wages.updated.text = marker;
  changed.questions.wages.paired.categories.worry.author = marker;
  changed.questions.wages.updated.rule_documents.raw_text = marker;
  const report = projectCivilComparison(changed);
  assert.ok(report);
  assert.ok(!JSON.stringify(report).includes(marker));
});
