import assert from 'node:assert/strict';
import test from 'node:test';
import {evidenceLabels, projectExpressionEvidence, projectProcessing} from '../src/lib/expression-evidence.ts';
import {analysisLimits, makeAnalysisBody} from '../src/lib/local-analysis-contract.ts';

const original = 'Fictional 🏛 account. I cannot access the website.';
const start = [...original].indexOf('I');
const sentence = 'I cannot access the website.';
const match = {row: 0, start, end: start + [...sentence].length, rule: 'stated_problem_v1', label: 'problem', text: sentence};
const report = {method: 'explicit_english_spans_v2', documents: 1, counts: Object.fromEntries(
  evidenceLabels.map(label => [label, label === 'problem' ? 1 : 0])), abstentions: {quoted: 1}, evidence: [match]};
const metadata = [{source: 'fictional', text: original}];

test('evidence checks Unicode codepoint offsets against the original complete document', () => {
  assert.deepEqual(projectExpressionEvidence(report, [0], metadata), report);
  for (const change of [{start: start - 1}, {end: match.end + 1}, {row: 1}, {text: 'invented supporting evidence'},
    {rule: 'self_emotion_v2'}, {label: 'curiosity'}]) {
    assert.equal(projectExpressionEvidence({...report, evidence: [{...match, ...change}]}, [0], metadata), null);
  }
  assert.equal(projectExpressionEvidence({...report, counts: {...report.counts, problem: 0}}, [0], metadata), null);
  assert.equal(projectExpressionEvidence({...report, evidence: [match, match]}, [0], metadata), null);
});

test('restricted source text never crosses the response projection', () => {
  const hidden = {...match};
  delete hidden.text;
  const restricted = [{source: 'civil_comments'}];
  assert.deepEqual(projectExpressionEvidence({...report, evidence: [hidden]}, [0], restricted)?.evidence, [hidden]);
  assert.equal(projectExpressionEvidence(report, [0], restricted), null);
});

test('processing counts documents and segments independently with exhaustive exclusions', () => {
  const processing = {documents: 1, segments: 5, characters: 1350,
    excluded: {language_or_markup: 1, document_limit: 0, duplicate: 0, collection_limit: 0, segment_limit: 0}};
  assert.deepEqual(projectProcessing(processing, 1, 2), processing);
  assert.equal(projectProcessing({...processing, segments: 0}, 1, 2), null);
  assert.equal(projectProcessing({...processing, characters: 100001}, 1, 2), null);
  assert.equal(projectProcessing(processing, 1, 3), null);
});

test('long inputs preserve full documents while respecting a separate collection budget', () => {
  const long = 'The original fictional document retains its context. '.repeat(20);
  const texts = Array.from({length: 12}, (_, index) => long + index);
  const submission = makeAnalysisBody(texts, 2, 'nmf');
  assert.deepEqual(JSON.parse(submission.body).texts, texts);
  assert.equal(makeAnalysisBody([long.repeat(10), ...texts], 2, 'nmf').error, 'tooLarge');
  assert.equal(makeAnalysisBody(Array(20).fill('x'.repeat(6000)), 2, 'nmf').error, 'tooLarge');
  assert.equal(analysisLimits.maxChars, 8000);
});
