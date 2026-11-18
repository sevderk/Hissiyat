import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const baseUrl = process.env.FRONTEND_BASE_URL ?? 'http://127.0.0.1:3000';
const expectResearchPreview = process.env.FRONTEND_EXPECT_RESEARCH_PREVIEW === '1';
const expectLocalAnalysis = process.env.FRONTEND_EXPECT_LOCAL_ANALYSIS === '1';
const expectMiniLM = process.env.FRONTEND_EXPECT_MINILM === '1';
const expectTrendsFixture = process.env.FRONTEND_EXPECT_TRENDS_FIXTURE === '1';
const expectTopicResearch = process.env.FRONTEND_EXPECT_TOPIC_RESEARCH === '1';
const expectLemmyFixture = process.env.FRONTEND_EXPECT_LEMMY_FIXTURE === '1';
const expectWikiFixture = process.env.FRONTEND_EXPECT_WIKI_FIXTURE === '1';
const locales = ['tr', 'en'];

function messageKeys(value, prefix = '') {
  return Object.entries(value).flatMap(([key, entry]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof entry === 'object' && entry !== null) return messageKeys(entry, path);
    assert.equal(typeof entry, 'string', `${path} must be a string`);
    assert.ok(entry.trim(), `${path} must not be empty`);
    return [path];
  }).sort();
}

const messages = await Promise.all(locales.map(async (locale) =>
  JSON.parse(await readFile(new URL(`../messages/${locale}.json`, import.meta.url), 'utf8'))
));
assert.deepEqual(messageKeys(messages[0]), messageKeys(messages[1]));

const root = await fetch(baseUrl, {
  redirect: 'manual',
  headers: {'Accept-Language': 'en'}
});
assert.ok([307, 308].includes(root.status), 'The root must redirect');
assert.equal(new URL(root.headers.get('location'), baseUrl).pathname, '/tr');
console.log('PASS / redirects to /tr, including an English browser preference');

for (const [index, locale] of locales.entries()) {
  const response = await fetch(`${baseUrl}/${locale}`);
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.ok(html.includes(`<html lang="${locale}"`), `${locale}: document language`);
  const {Dashboard: dashboard, LocalAnalysis: local, Research: research, TopicResearch: topic} = messages[index];
  assert.ok(html.includes(`<h1 id="topic-research-heading">${topic.title}</h1>`), `${locale}: translated research heading`);
  assert.ok(html.includes(dashboard.noticeTitle), `${locale}: translated demo notice`);
  assert.ok(html.includes(topic.intro), `${locale}: translated purpose`);
  assert.ok(html.includes(topic.unavailableStatus) && html.includes(topic.unsupportedGeography));
  assert.ok(html.includes(topic.lemmy) && html.includes(topic.lemmyHelp), `${locale}: Lemmy coverage`);
  assert.ok(html.includes(topic.wikimedia) && html.includes(topic.wikiHelp), `${locale}: Wikimedia pilot coverage`);
  assert.equal(html.includes(`>${topic.exampleTopic}</button>`), expectTopicResearch, `${locale}: research controls`);
  assert.ok(html.indexOf('id="topic-research"') < html.indexOf('id="synthetic-demo"'));
  assert.ok(html.includes(dashboard.human.title) && html.includes(dashboard.search.title), `${locale}: both domains`);
  assert.ok(html.includes(dashboard.states.loading), `${locale}: loading state before hydration`);
  assert.match(html, /href="\/tr"/);
  assert.match(html, /href="\/en"/);
  assert.ok(html.includes('aria-current="page"'));
  assert.ok(!html.includes('MISSING_MESSAGE'), `${locale}: no missing translations`);
  const syntheticStart = html.indexOf('id="synthetic-demo"');
  assert.ok(syntheticStart > -1, `${locale}: labeled synthetic section`);
  const trendsStart = html.indexOf('id="trends-research"');
  if (expectTrendsFixture) {
    assert.ok(trendsStart > -1 && trendsStart < syntheticStart);
    assert.ok(html.includes('href="#trends-research"'));
    assert.ok(html.slice(trendsStart, syntheticStart).includes(messages[index].TrendsResearch.title));
  } else {
    assert.equal(trendsStart, -1, `${locale}: research Trends preview stays off`);
  }
  const researchStart = html.indexOf('id="research-findings"');
  const localStart = html.indexOf('id="local-text-analysis"');
  if (expectLocalAnalysis) {
    assert.ok(localStart > -1 && localStart < (expectResearchPreview ? researchStart : syntheticStart));
    assert.match(html, /href="#local-text-analysis"/);
    const localSection = html.slice(localStart, html.indexOf('</section>', localStart));
    for (const label of [local.title, local.analyze, local.career, local.technology, local.method, ...Object.values(local.methods)]) {
      assert.ok(localSection.includes(label), `${locale}: analysis control label`);
    }
  } else {
    assert.equal(localStart, -1, `${locale}: local analysis stays off`);
    assert.ok(!html.includes(local.title), `${locale}: no analysis labels in the response`);
  }
  if (expectResearchPreview) {
    assert.ok(researchStart > -1 && researchStart < syntheticStart, `${locale}: separate research section`);
    assert.match(html, /href="#research-findings"/);
    const findings = html.slice(researchStart, syntheticStart);
    for (const message of [research.title, research.comparison, research.ari, research.observed, research.limits]) {
      assert.ok(findings.includes(message), `${locale}: research explanation`);
    }
    const decimal = new Intl.NumberFormat(locale, {minimumFractionDigits: 4, maximumFractionDigits: 4});
    for (const value of [0.3518, 0.1823, 0.8184, 0.5177, 0.8770, 0.4989]) {
      assert.ok(findings.includes(decimal.format(value)), `${locale}: formatted decimal ${value}`);
    }
    assert.match(findings, /<caption>/);
    assert.equal([...findings.matchAll(/scope="col"/g)].length, 3);
    assert.equal([...findings.matchAll(/scope="row"/g)].length, 3);
    assert.match(findings, /careernet-data\/releases\/tag\/v1\.1/);
    assert.match(findings, /creativecommons\.org\/licenses\/by\/4\.0\//);
    assert.doesNotMatch(findings, /kurgusal|fictional|review\.json|review\.key|AppData|LOCALAPPDATA/i);
    const synthetic = html.slice(syntheticStart, html.indexOf('</main>', syntheticStart));
    assert.ok(synthetic.includes(dashboard.notice));
    assert.ok(!synthetic.includes(decimal.format(0.3518)));
  } else {
    assert.equal(researchStart, -1, `${locale}: research section stays off`);
    assert.doesNotMatch(html, /0[,.]3518|0[,.]8770|href="#research-findings"/);
    for (const message of [research.title, research.observed, research.ari]) {
      assert.ok(!html.includes(message), `${locale}: no research findings or messages in the response`);
    }
  }
  const missing = await fetch(`${baseUrl}/${locale}/missing-page`);
  assert.equal(missing.status, 404);
  assert.ok((await missing.text()).includes(messages[index].NotFound.title));
  console.log(`PASS /${locale}: language, content, switch links and localized 404`);
}
for (const path of ['/api/research-findings', '/api/demo/research-findings', '/api/demo/annotations']) {
  const response = await fetch(baseUrl + path);
  assert.equal(response.status, 404, `No private research endpoint at ${path}`);
}
console.log('PASS research preview visibility and separation, with no research or annotation API');
console.log('PASS translation keys match and all messages are nonempty');

const trendsUrl = baseUrl + '/api/trends-preview';
assert.equal((await fetch(trendsUrl + '?term=apple')).status, 404);
assert.equal((await fetch(trendsUrl, {headers: {'Sec-Fetch-Site': 'cross-site'}})).status, 404);
const trendsResponse = await fetch(trendsUrl);
assert.equal(trendsResponse.headers.get('Cache-Control'), 'no-store');
assert.equal(trendsResponse.headers.get('Set-Cookie'), null);
if (expectTrendsFixture) {
  assert.equal(trendsResponse.status, 200);
  const data = await trendsResponse.json();
  assert.equal(data.source, 'fictional_fixture');
  assert.equal(data.granularity, 'monthly');
  assert.equal(data.geography, 'CA');
  assert.deepEqual(data.points.map(point => point.value), [124.25, 0, null, null, 60.125]);
  assert.deepEqual(data.points.map(point => point.status), ['observed', 'observed', 'missing', 'suppressed', 'observed']);
  console.log('PASS fictional Trends dates, original values and separate gap statuses');
} else {
  assert.equal(trendsResponse.status, 404);
}

const analysisUrl = baseUrl + '/api/local-text-analysis';
const headers = {'Content-Type': 'application/json', 'Origin': new URL(baseUrl).origin};
const topicResearchUrl = baseUrl + '/api/topic-research';
const submitResearch = (query, extraHeaders = {}) => fetch(topicResearchUrl, {
  method: 'POST', headers: {...headers, ...extraHeaders}, body: JSON.stringify(query),
});
assert.equal((await fetch(topicResearchUrl)).status, 404);
const topicScope = {mode: 'topic', query: 'bisiklet yolları', source: 'fictional', start_date: '2026-11-05', end_date: '2026-11-16', language: 'tr', geography: null};
if (expectTopicResearch) {
  assert.equal((await submitResearch(topicScope, {Origin: 'https://external.invalid'})).status, 403);
  assert.equal((await submitResearch(topicScope, {'Sec-Fetch-Site': 'cross-site'})).status, 403);
  assert.equal((await submitResearch({...topicScope, geography: 'TR'})).status, 400);
  assert.equal((await submitResearch({...topicScope, source: 'google_trends', language: null})).status, 422);
  const lemmyScope = {...topicScope, source: 'lemmy', query: 'fictional fixture only', language: null};
  assert.equal((await submitResearch({...lemmyScope, language: 'en'})).status, 400);
  if (expectLemmyFixture) {
    const response = await submitResearch(lemmyScope);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.equal(response.headers.get('set-cookie'), null);
    const body = await response.text();
    const result = JSON.parse(body);
    assert.deepEqual(result.scope, lemmyScope);
    assert.equal(result.capabilities.status, 'public_api');
    assert.deepEqual(result.capabilities.languages, []);
    assert.equal(result.retrieved, 1);
    assert.deepEqual(result.records.map(record => [record.source, record.country, record.reference, record.source_language_id]),
      [['lemmy', 'UNKNOWN', 'https://lemmy.world/post/2147483640', 37]]);
    assert.doesNotMatch(body, /fictional-confidential-content|thumbnail_url|\"text\"/);
    console.log('PASS fictional Lemmy fixture through both local APIs, source link and metadata only');
  }
  assert.deepEqual(await (await submitResearch(lemmyScope)).json(), {code: 'approval_required'});
  assert.deepEqual(await (await submitResearch({...lemmyScope, content: 'comments', analyze_discussion: true})).json(),
    {code: 'analysis_permission_unverified'});
  const wikiScope = {...topicScope, source: 'wikimedia', query: 'Talk:USB flash drive', language: null,
    content: 'comments', analyze_discussion: true, start_date: '2001-01-01'};
  if (expectWikiFixture) {
    const response = await submitResearch(wikiScope);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const body = await response.text();
    const wiki = JSON.parse(body);
    assert.equal(wiki.source_document.license, 'CC BY-SA 4.0');
    assert.equal(wiki.retrieved, 2);
    assert.deepEqual(wiki.discussion_analysis.evidence_rows, [0, 1]);
    assert.equal(wiki.discussion_analysis.expression_signals.submitted_texts, 2);
    assert.equal(wiki.discussion_analysis.topics_status, 'insufficient_texts');
    assert.doesNotMatch(body, /FictionalEditor|FictionalReply|I need information|othercontent/);
    console.log('PASS Wikimedia fixture through both local APIs, attribution, denominator and metadata only');
  }
  assert.deepEqual(await (await submitResearch(wikiScope)).json(), {code: 'approval_required'});
  assert.equal((await submitResearch({...wikiScope, query: 'Talk:Other'})).status, 400);
  for (const scope of [topicScope, {...topicScope, mode: 'event', query: 'river festival', language: 'en'}]) {
    const response = await submitResearch(scope);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
    assert.equal(response.headers.get('Set-Cookie'), null);
    const result = await response.json();
    assert.deepEqual(result.scope, scope);
    assert.equal(result.capabilities.status, 'synthetic');
    assert.equal(result.retrieved, 2);
    assert.deepEqual(result.records.map(record => record.country), ['UNKNOWN', 'UNKNOWN']);
    assert.ok(result.records.every(record => record.reference === null && record.text));
  }
  const empty = await (await submitResearch({...topicScope, query: 'unmatched fixture'})).json();
  assert.equal(empty.retrieved, 0);
  assert.deepEqual(empty.records, []);
  console.log('PASS research topic and event, empty results, source and geography controls, and no-store');
  const discussion = {...topicScope, query: 'community services', language: 'en', content: 'mixed', analyze_discussion: true};
  const discussionResponse = await submitResearch(discussion);
  assert.equal(discussionResponse.status, 200);
  const sample = await discussionResponse.json();
  assert.equal(sample.retrieved, 16);
  assert.equal(sample.records.filter(record => record.kind === 'comment').length, 10);
  assert.equal(sample.discussion_analysis.topics_status, expectMiniLM ? 'comparison' : 'nmf_only');
  assert.deepEqual(sample.discussion_analysis.evidence_rows, Array.from({length: 16}, (_, index) => index));
  assert.equal(sample.discussion_analysis.expression_signals.needs.information, 3);
  const small = await (await submitResearch({...discussion, content: 'posts'})).json();
  assert.equal(small.discussion_analysis.topics_status, 'insufficient_texts');
  assert.equal(small.discussion_analysis.topics, null);
  assert.equal(small.discussion_analysis.expression_signals.submitted_texts, 6);
  console.log('PASS mixed fictional discussion, evidence indices, model grouping, signals and small-sample gating');
} else {
  assert.equal((await submitResearch(topicScope)).status, 404);
  assert.equal((await submitResearch({...topicScope, source: 'civil_comments', query: 'work',
    start_date: '2015-01-01', end_date: '2017-12-31', language: 'en',
    content: 'comments', analyze_discussion: true})).status, 404);
  console.log('PASS topic research API is disabled');
}
assert.equal((await fetch(analysisUrl)).status, 404);
assert.equal((await fetch(analysisUrl, {method: 'OPTIONS'})).status, 404);
const status = async (body, extraHeaders) => (await fetch(analysisUrl, {
  method: 'POST', headers: {...headers, ...extraHeaders}, body
})).status;
if (expectLocalAnalysis) {
  assert.equal(await status('{}', {Origin: 'http://external.invalid'}), 403);
  assert.equal(await status('{}', {'Sec-Fetch-Site': 'cross-site'}), 403);
  assert.equal(await status('{"texts":["zzconfidentialmarker"]}'), 400);
  const large = new ReadableStream({start(controller) {
    controller.enqueue(new Uint8Array(33_000));
    controller.enqueue(new Uint8Array(33_000));
    controller.close();
  }});
  assert.equal((await fetch(analysisUrl, {method: 'POST', headers, body: large, duplex: 'half'})).status, 413);

  const examples = JSON.parse(await readFile(new URL('../src/lib/local-analysis-examples.json', import.meta.url), 'utf8'));
  async function run(texts, k, method, expected = 200) {
    const response = await fetch(analysisUrl, {method: 'POST', headers, body: JSON.stringify({texts, k, method, include_signals: true})});
    assert.equal(response.status, expected, `${method} k=${k}`);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.equal(response.headers.get('set-cookie'), null);
    return response.json();
  }
  for (const [name, texts] of Object.entries(examples)) {
    for (const k of [2, 3]) {
      const nmf = await run(texts, k, 'nmf');
      assert.deepEqual(Object.keys(nmf.methods), ['nmf']);
      assert.equal(nmf.agreement, null);
      let result = nmf;
      if (expectMiniLM) {
        const minilm = await run(texts, k, 'minilm');
        assert.deepEqual(Object.keys(minilm.methods), ['minilm']);
        assert.equal(minilm.agreement, null);
        result = await run(texts, k, 'both');
        assert.deepEqual(result, await run(texts, k, 'both'));
        assert.deepEqual(result.methods, {...nmf.methods, ...minilm.methods});
        assert.deepEqual(result.expression_signals, nmf.expression_signals);
        assert.deepEqual(result.expression_signals, minilm.expression_signals);
        assert.equal(result.agreement.common_assigned, texts.length);
        assert.ok(typeof result.agreement.ari === 'number' && Math.abs(result.agreement.ari) <= 1);
      }
      for (const method of Object.values(result.methods)) {
        assert.equal(method.groups.length, k);
        assert.equal(method.groups.reduce((total, {size}) => total + size, method.unassigned), texts.length);
      }
      assert.equal(result.expression_signals.submitted_texts, texts.length);
      console.log(`PASS local analysis ${name} k=${k}: ${JSON.stringify(result)}`);
    }
  }
  const challenge = JSON.parse(await readFile(new URL('../../backend/tests/fixtures/expression_signals.json', import.meta.url), 'utf8'));
  const texts = challenge.map(row => row.text);
  const labelsByGroup = {
    emotions: ['worry', 'excitement', 'frustration', 'confidence', 'curiosity'],
    needs: ['information', 'guidance', 'support'],
    experiences: ['reported']
  };
  const expected = {submitted_texts: texts.length, emotions: {}, needs: {}, experiences: {}};
  for (const [group, labels] of Object.entries(labelsByGroup)) {
    for (const label of labels) {
      expected[group][label] = challenge.filter(row => row.labels.includes(label)).length;
    }
  }
  const challengeResult = await run(texts, 2, 'nmf');
  assert.deepEqual(challengeResult.expression_signals, expected);
  const modified = await run(['I am not worried about the delay.', ...texts.slice(1)], 2, 'nmf');
  assert.deepEqual(modified.expression_signals, {...expected, emotions: {...expected.emotions, worry: 0}});
  console.log(`PASS fictional expression challenge and negation change: ${JSON.stringify(expected)}`);
  if (!expectMiniLM) assert.deepEqual(await run(examples.career, 2, 'minilm', 503), {code: 'model_unavailable'});
} else {
  assert.equal(await status('{}'), 404);
  assert.equal(await status('{"texts":["I am worried."],"k":2,"include_signals":true}'), 404);
  console.log('PASS local analysis API is disabled');
}
