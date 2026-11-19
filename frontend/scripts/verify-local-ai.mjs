// Opt-in real local-model acceptance. All research inputs are fictional.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {existsSync, mkdtempSync, readFileSync, realpathSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, relative} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const baseUrl = process.env.FRONTEND_BASE_URL ?? 'http://127.0.0.1:3084';
const productionUrl = process.env.FRONTEND_PRODUCTION_URL;
for (const url of [baseUrl, productionUrl].filter(Boolean)) {
  const parsed = new URL(url);
  assert.equal(parsed.hostname, '127.0.0.1');
  assert.equal(parsed.protocol, 'http:');
}
const executable = join(process.env.ProgramFiles, 'Google/Chrome/Application/chrome.exe');
assert.ok(existsSync(executable));
const tempRoot = realpathSync(tmpdir());
const profile = mkdtempSync(join(tempRoot, 'hissiyat-local-ai-'));
const child = spawn(executable, ['--headless=new', '--disable-background-networking', '--disable-component-update',
  '--disable-extensions', '--disable-sync', '--no-first-run', '--no-default-browser-check', '--disable-crash-reporter',
  '--no-proxy-server', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--user-data-dir=' + profile, 'about:blank'],
{windowsHide: true, stdio: 'ignore'});
let websocket;
async function waitFor(probe, label, timeout = 20000) {
  const stop = Date.now() + timeout;
  do { const result = await probe(); if (result) return result; await delay(200); } while (Date.now() < stop);
  throw new Error('Timed out waiting for ' + label);
}
try {
  const port = await waitFor(() => {
    try { return Number(readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0]); }
    catch { return 0; }
  }, 'Chrome');
  const targets = await fetch('http://127.0.0.1:' + port + '/json/list').then(reply => reply.json());
  websocket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((accept, reject) => {websocket.onopen = accept; websocket.onerror = reject;});
  let serial = 0;
  const pending = new Map(), requests = [], responses = [];
  websocket.onmessage = ({data}) => {
    const message = JSON.parse(data);
    if (message.method === 'Network.requestWillBeSent') requests.push(message.params.request.url);
    if (message.method === 'Network.responseReceived') responses.push(message.params);
    const operation = pending.get(message.id);
    if (operation) {
      pending.delete(message.id);
      if (message.error) operation.reject(new Error(message.error.message));
      else operation.accept(message.result);
    }
  };
  const call = (method, params = {}) => new Promise((accept, reject) => {
    const id = ++serial; pending.set(id, {accept, reject});
    websocket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', {expression, returnByValue: true});
    if (result.exceptionDetails) throw new Error('Browser evaluation failed');
    return result.result.value;
  };
  await call('Network.enable'); await call('Page.enable');
  for (const [language, query, expected, status] of [['tr', 'community services', 16, 'exploratory'], ['en', 'printing', 2, 'insufficient']]) {
    const messages = JSON.parse(readFileSync('messages/' + language + '.json', 'utf8')).TopicResearch;
    await call('Emulation.setDeviceMetricsOverride', {width: language === 'tr' ? 430 : 1365, height: 900, deviceScaleFactor: 1, mobile: false});
    await call('Page.navigate', {url: baseUrl + '/' + language});
    await waitFor(() => evaluate('(()=>{const button=Array.from(document.querySelectorAll("#topic-research button")).find(el=>el.textContent===' +
      JSON.stringify(messages.discussionExample) + ');return button && Object.keys(button).some(key=>key.startsWith("__reactProps$") && typeof button[key].onClick==="function");})()'), 'hydrated controls');
    await evaluate('Array.from(document.querySelectorAll("#topic-research button")).find(el=>el.textContent===' + JSON.stringify(messages.discussionExample) + ').click()');
    await waitFor(() => evaluate('document.querySelector("#topic-research input[type=text]").value==="community services"'), 'fictional scope');
    if (query === 'printing') {
      await evaluate('(()=>{const el=document.querySelector("#topic-research input[type=text]");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(el,"printing");el.dispatchEvent(new Event("input",{bubbles:true}));})()');
      await evaluate('document.querySelector("input[name=research-mode][value=event]").click()');
    }
    await evaluate('document.querySelector("#topic-research button[type=submit]").click()');
    await waitFor(() => evaluate('!!document.querySelector("#ai-research-interpretation button")'), 'computed evidence');
    const research = responses.filter(entry => new URL(entry.response.url).pathname === '/api/topic-research').at(-1);
    assert.equal(research.response.status, 200);
    const body = await call('Network.getResponseBody', {requestId: research.requestId});
    const evidence = JSON.parse(body.body).evidence_package;
    assert.equal(evidence.scope.analyzed_documents, expected);
    assert.equal(evidence.fictional, true);
    assert.equal(evidence.status, status);
    const started = Date.now();
    await evaluate('document.querySelector("#ai-research-interpretation button").click()');
    await waitFor(() => evaluate('!!document.querySelector("[data-testid=ai-generated-result]") || !!document.querySelector("#ai-research-interpretation [role=alert]")'), 'real local model result', 180000);
    const error = await evaluate('document.querySelector("#ai-research-interpretation [role=alert]")?.textContent');
    assert.ok(!error, error);
    const inference = responses.filter(entry => new URL(entry.response.url).pathname === '/api/research-interpretation').at(-1);
    assert.equal(inference.response.status, 200);
    const generated = JSON.parse((await call('Network.getResponseBody', {requestId: inference.requestId})).body);
    assert.equal(generated.model, 'hissiyat-qwen3-1.7b');
    assert.equal(generated.package_id, evidence.package_id);
    assert.equal(generated.result.language, language);
    assert.equal(generated.result.status, status);
    assert.equal(generated.result.scope.analyzed_documents, expected);
    assert.ok(generated.result.findings.every(finding => evidence.facts.some(fact => fact.id === finding.evidence_id && fact.kind === finding.kind)));
    assert.ok(await evaluate('Array.from(document.querySelectorAll("[data-testid=ai-generated-result] a")).every(link=>!!document.getElementById(link.hash.slice(1)))'));
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
    assert.ok(!await evaluate('document.body.textContent.includes("MISSING_MESSAGE")'));
    console.log('PASS ' + JSON.stringify({language, mode: generated.result.scope.mode, documents: expected, status,
      realModel: generated.model, seconds: Math.round((Date.now() - started) / 1000), overview: generated.result.overview.text}));
  }
  if (productionUrl) {
    const reply = await fetch(productionUrl + '/api/research-interpretation', {method: 'POST',
      headers: {'Content-Type': 'application/json', Origin: productionUrl}, body: JSON.stringify({package_id: 'a'.repeat(32), language: 'en'})});
    assert.equal(reply.status, 404);
    await call('Page.navigate', {url: productionUrl + '/tr'});
    await waitFor(() => evaluate('!!document.querySelector("#topic-research fieldset")'), 'production controls');
    assert.equal(await evaluate('document.querySelector("#topic-research fieldset").disabled'), true);
    assert.equal(await evaluate('document.querySelector("#ai-research-interpretation")===null'), true);
    console.log('PASS production inference and UI gates');
  }
  assert.ok(requests.every(url => !/^https?:/.test(url) || url.startsWith('http://127.0.0.1:')));
  console.log('PASS browser requests stayed on loopback');
  await call('Browser.close').catch(() => {});
} finally {
  websocket?.close();
  if (child.exitCode === null) child.kill();
  await delay(2400);
  const checked = realpathSync(profile);
  assert.match(relative(tempRoot, checked), /^hissiyat-local-ai-[A-Za-z0-9]+$/);
  rmSync(checked, {recursive: true, force: true, maxRetries: 12, retryDelay: 150});
}
