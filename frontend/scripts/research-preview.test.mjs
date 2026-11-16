import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {isResearchPreviewEnabled, researchPreview} from '../src/lib/research-preview.ts';

test('the preview contains exactly the curated research aggregates and attribution', () => {
  assert.deepEqual(researchPreview, {
    reviewedQuestions: 80,
    overlapQuestions: 12,
    stabilityRepetitions: 5,
    stabilitySampleShare: 0.8,
    comparisons: [
      {k: 2, betweenMethods: 0.3518, nmfStability: 0.8184, miniLmStability: 0.8770},
      {k: 3, betweenMethods: 0.1823, nmfStability: 0.5177, miniLmStability: 0.4989}
    ],
    source: {
      release: 'https://github.com/RenaissancePhilanthropy/careernet-data/releases/tag/v1.1',
      license: 'https://creativecommons.org/licenses/by/4.0/'
    }
  });
});

test('research numbers require an explicit development-only opt-in', () => {
  assert.equal(isResearchPreviewEnabled('development', '1'), true);
  for (const environment of ['production', 'test', undefined]) {
    assert.equal(isResearchPreviewEnabled(environment, '1'), false);
  }
  for (const setting of [undefined, '0', 'true']) {
    assert.equal(isResearchPreviewEnabled('development', setting), false);
  }
});

test('the research section is a server component with static inputs and no demo dependency', async () => {
  const code = await readFile(new URL('../src/components/research-findings.tsx', import.meta.url), 'utf8');
  assert.deepEqual([...code.matchAll(/^import .* from '([^']+)';$/gm)].map((match) => match[1]),
    ['next-intl/server', '@/lib/research-preview']);
  assert.doesNotMatch(code, /use client|\bfetch\s*\(|\/api\/|[A-Z]:[\\/]|LOCALAPPDATA|review\.json|review\.key/i);
});

for (const locale of ['tr', 'en']) {
  test(`${locale} explains chance-adjusted agreement, observed stability and review limitations`, async () => {
    const messages = JSON.parse(await readFile(new URL(`../messages/${locale}.json`, import.meta.url), 'utf8'));
    const {Research: research, Dashboard: dashboard} = messages;
    assert.equal(research.title, locale === 'tr' ? 'Araştırma Bulguları' : 'Research Findings');
    assert.match(research.ari, locale === 'tr' ? /şansla.*Sınıflandırma doğruluğu/ : /chance.*Classification accuracy/);
    assert.match(research.observed, /k = 2/);
    assert.match(research.observed, locale === 'tr' ? /Temaların geçerliliği/ : /Thematic validity/);
    assert.match(research.review, locale === 'tr' ? /bağımsız.*Uyum kategoriye göre/ : /independently.*Agreement varied/);
    assert.match(research.limits, locale === 'tr' ? /seçilmiş İngilizce/ : /selected English-language/);
    assert.match(dashboard.notice, locale === 'tr' ? /kurgusal/ : /fictional/);
  });
}
