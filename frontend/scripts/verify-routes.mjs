import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const baseUrl = process.env.FRONTEND_BASE_URL ?? 'http://127.0.0.1:3000';
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
  assert.ok(html.includes(messages[index].Home.status), `${locale}: translated status`);
  assert.ok(html.includes(messages[index].Home.description), `${locale}: translated purpose`);
  assert.match(html, /href="\/tr"/);
  assert.match(html, /href="\/en"/);
  assert.ok(html.includes('aria-current="page"'));
  assert.ok(!html.includes('MISSING_MESSAGE'), `${locale}: no missing translations`);
  const missing = await fetch(`${baseUrl}/${locale}/missing-page`);
  assert.equal(missing.status, 404);
  assert.ok((await missing.text()).includes(messages[index].NotFound.title));
  console.log(`PASS /${locale}: language, content, switch links and localized 404`);
}
console.log('PASS translation keys match and all messages are nonempty');
