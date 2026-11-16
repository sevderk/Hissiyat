import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const baseUrl = process.env.FRONTEND_BASE_URL ?? 'http://127.0.0.1:3000';
const expectResearchPreview = process.env.FRONTEND_EXPECT_RESEARCH_PREVIEW === '1';
const expectLocalAnalysis = process.env.FRONTEND_EXPECT_LOCAL_ANALYSIS === '1';
const expectMiniLM = process.env.FRONTEND_EXPECT_MINILM === '1';
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
  const {Dashboard: dashboard, LocalAnalysis: local, Research: research} = messages[index];
  assert.ok(html.includes(`<h1>${dashboard.title}</h1>`), `${locale}: translated dashboard heading`);
  assert.ok(html.includes(dashboard.noticeTitle), `${locale}: translated demo notice`);
  assert.ok(html.includes(dashboard.intro), `${locale}: translated purpose`);
  assert.ok(html.includes(dashboard.human.title) && html.includes(dashboard.search.title), `${locale}: both domains`);
  assert.ok(html.includes(dashboard.states.loading), `${locale}: loading state before hydration`);
  assert.match(html, /href="\/tr"/);
  assert.match(html, /href="\/en"/);
  assert.ok(html.includes('aria-current="page"'));
  assert.ok(!html.includes('MISSING_MESSAGE'), `${locale}: no missing translations`);
  const syntheticStart = html.indexOf('id="synthetic-demo"');
  assert.ok(syntheticStart > -1, `${locale}: labeled synthetic section`);
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

const analysisUrl = baseUrl + '/api/local-text-analysis';
const headers = {'Content-Type': 'application/json', 'Origin': new URL(baseUrl).origin};
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
    const response = await fetch(analysisUrl, {method: 'POST', headers, body: JSON.stringify({texts, k, method})});
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
        assert.equal(result.agreement.common_assigned, texts.length);
        assert.ok(typeof result.agreement.ari === 'number' && Math.abs(result.agreement.ari) <= 1);
      }
      for (const method of Object.values(result.methods)) {
        assert.equal(method.groups.length, k);
        assert.equal(method.groups.reduce((total, {size}) => total + size, method.unassigned), texts.length);
      }
      console.log(`PASS local analysis ${name} k=${k}: ${JSON.stringify(result)}`);
    }
  }
  if (!expectMiniLM) assert.deepEqual(await run(examples.career, 2, 'minilm', 503), {code: 'model_unavailable'});
} else {
  assert.equal(await status('{}'), 404);
  console.log('PASS local analysis API is disabled');
}
