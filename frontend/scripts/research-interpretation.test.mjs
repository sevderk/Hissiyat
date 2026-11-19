import assert from 'node:assert/strict';
import test from 'node:test';
import {projectAIInterpretation, projectEvidencePackage} from '../src/lib/research-interpretation.ts';

// Every value below belongs to an explicitly fictional protocol fixture.
const scope = {source: 'fictional', family: 'discussion', mode: 'event', query: 'fictional library',
  start_date: '2026-11-05', end_date: '2026-11-16', date_unit: 'day', geography: 'UNKNOWN',
  requested_geography: null, language_filter: 'en', content: 'mixed', analyzed_documents: 16};
const input = {package_id: 'a'.repeat(32), version: 'research_evidence_v1', created_at: '2026-11-19T10:00:00+00:00',
  scope, fictional: true, status: 'exploratory', source_reference: null, facts: [
    {id: 'E01', metric: 'sample', unit: 'documents', kind: 'observed', values: {retrieved: 16, selected: 16, analyzed: 16}, denominator: 16, method: 'source_metadata'},
    {id: 'E02', metric: 'context', unit: 'metadata', kind: 'insufficient', values: {}, denominator: null, method: 'demographics_and_article_context_unavailable'},
  ]};
const output = {package_id: input.package_id, model: 'hissiyat-qwen3-1.7b', prompt_version: 'research_interpretation_v1',
  verification: 'scope_ids_framing_and_numeric_text_checks', result: {language: 'en', scope, status: 'exploratory',
    overview: {evidence_id: 'E01', text: 'This fictional sample supports an exploratory description.'},
    findings: [{evidence_id: 'E01', kind: 'observed', interpretation: 'The evidence is bounded by the retained sample.'}],
    uncertainties: [{evidence_id: 'E02', text: 'Article context is unavailable.'}],
    questions: [{evidence_id: 'E02', text: 'What further context would help?'}]}};

test('evidence projection preserves source scope and excludes unknown private fields', () => {
  assert.deepEqual(projectEvidencePackage({...input, raw_text: 'FICTIONAL_PRIVATE'}), input);
  for (const mutate of [
    value => {value.scope.geography = 'TR';},
    value => {value.facts[0].values.analyzed = 99;},
    value => {value.facts[0].denominator = 99;},
    value => {value.facts[0].values.raw_text = 'FICTIONAL_PRIVATE';},
    value => {value.source_reference = 'https://example.invalid/private';},
    value => {value.facts.push(value.facts[0]);},
    value => {value.scope.end_date = '2026-02-30';},
    value => {value.fictional = false;},
  ]) {
    const changed = structuredClone(input); mutate(changed);
    assert.equal(projectEvidencePackage(changed), null);
  }
});

test('AI projection binds the report to its actual package, language and evidence framing', () => {
  const evidence = projectEvidencePackage(input);
  assert.deepEqual(projectAIInterpretation(output, evidence, 'en'), output);
  for (const mutate of [
    value => {value.package_id = 'b'.repeat(32);},
    value => {value.result.scope.analyzed_documents = 999;},
    value => {value.result.scope.start_date = '2025-01-01';},
    value => {value.result.scope.geography = 'TR';},
    value => {value.result.findings[0].evidence_id = 'E99';},
    value => {value.result.findings[0].kind = 'exploratory';},
    value => {value.result.language = 'tr';},
    value => {value.result.questions[0].evidence_id = 'E98';},
  ]) {
    const changed = structuredClone(output); mutate(changed);
    assert.equal(projectAIInterpretation(changed, evidence, 'en'), null);
  }
});

test('model headers, raw responses and arbitrary fields never enter the projected report', () => {
  const changed = structuredClone(output);
  const marker = 'FICTIONAL_PRIVATE';
  changed.headers = marker;
  changed.result.raw = marker;
  changed.result.findings[0].raw = marker;
  assert.ok(!JSON.stringify(projectAIInterpretation(changed, projectEvidencePackage(input), 'en')).includes(marker));
});
