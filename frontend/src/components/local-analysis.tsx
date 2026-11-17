'use client';

import {useFormatter, useTranslations} from 'next-intl';
import {type FormEvent, useState} from 'react';
import examples from '@/lib/local-analysis-examples.json';
import {analysisLimits, analysisMethods, type AnalysisMethod, expressionCategories, isLocalAnalysisResult, type LocalAnalysisResult,
  makeAnalysisBody, parseTextarea, resultTextCount} from '@/lib/local-analysis-contract';

type Example = keyof typeof examples;
type ErrorKey = 'textCount' | 'tooLarge' | 'invalidInput' | 'insufficientVariation' | 'busy' | 'unavailable' | 'modelUnavailable';

const requestErrors: Partial<Record<number, ErrorKey>> = {
  400: 'invalidInput', 413: 'tooLarge', 422: 'insufficientVariation', 429: 'busy'
};

function ExpressionSignals({signals}: {signals: NonNullable<LocalAnalysisResult['expression_signals']>}) {
  const t = useTranslations('LocalAnalysis.signals');
  const format = useFormatter();
  const counts = {...signals.emotions, ...signals.needs, ...signals.experiences};

  return (
    <section className="local-analysis-results" aria-labelledby="expression-signals-heading">
      <h3 id="expression-signals-heading">{t('title')}</h3>
      <p className="dashboard-muted">{t('denominator', {count: signals.submitted_texts})}</p>
      <p className="dashboard-muted">{t('interpretation')}</p>
      <div className="expression-groups">
        {(['emotions', 'needs', 'experiences'] as const).map(group => (
          <section key={group} aria-label={t(`groups.${group}`)}>
            <h4>{t(`groups.${group}`)}</h4>
            <dl className="distribution-list">
              {expressionCategories[group].map(label => (
                <div key={label} className="bar-label"><dt>{t(`labels.${label}`)}</dt><dd>{format.number(counts[label])}</dd></div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </section>
  );
}

export function LocalAnalysis() {
  const t = useTranslations('LocalAnalysis');
  const format = useFormatter();
  const [text, setText] = useState('');
  const [example, setExample] = useState<Example | ''>('');
  const [k, setK] = useState<2 | 3>(2);
  const [method, setMethod] = useState<AnalysisMethod>('nmf');
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<LocalAnalysisResult | null>(null);
  const [error, setError] = useState<ErrorKey | null>(null);
  const count = parseTextarea(text).length;

  function updateText(value: string, collection: Example | '' = '') {
    setText(value);
    setExample(collection);
    setError(null);
    setResult(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError(null);
    setResult(null);
    const texts = parseTextarea(text);
    const submission = makeAnalysisBody(texts, k, method);
    if (submission.error) {
      setError(submission.error);
      return;
    }
    setPending(true);
    try {
      const response = await fetch('/api/local-text-analysis', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: submission.body,
        cache: 'no-store', credentials: 'omit', signal: AbortSignal.timeout(67000)
      });
      if (!response.ok) {
        if (response.status === 503 && (await response.json()).code === 'model_unavailable') {
          setError('modelUnavailable');
          return;
        }
        setError(requestErrors[response.status] ?? 'unavailable');
        return;
      }
      const payload: unknown = await response.json();
      if (isLocalAnalysisResult(payload, texts.length, k, method) && payload.expression_signals) setResult(payload);
      else setError('unavailable');
    } catch {
      setError('unavailable');
    } finally {
      setPending(false);
    }
  }

  return (
    <section id="local-text-analysis" className="analysis-section" aria-labelledby="local-analysis-heading">
      <div className="analysis-heading">
        <div>
          <p className="source-label">{t('local')}</p>
          <h2 id="local-analysis-heading">{t('title')}</h2>
          <p className="section-description">{t('intro')}</p>
        </div>
      </div>
      <div className="dashboard-card local-analysis-panel">
        <form onSubmit={submit} aria-busy={pending} autoComplete="off">
          <fieldset disabled={pending}>
            <div className="local-analysis-options">
              <label>
                {t('examples')}
                <select value={example} onChange={event => {
                  const value = event.target.value as Example | '';
                  updateText(value ? examples[value].join('\n') : '', value);
                }}>
                  <option value="">{t('own')}</option>
                  <option value="career">{t('career')}</option>
                  <option value="technology">{t('technology')}</option>
                </select>
              </label>
              <label>
                {t('method')}
                <select value={method} onChange={event => {
                  setMethod(event.target.value as AnalysisMethod);
                  setResult(null);
                  setError(null);
                }}>
                  {[...analysisMethods, 'both' as const].map(value => <option key={value} value={value}>{t(`methods.${value}`)}</option>)}
                </select>
              </label>
              <label>
                {t('clusters')}
                <select value={k} onChange={event => {
                  setK(event.target.value === '3' ? 3 : 2);
                  setResult(null);
                  setError(null);
                }}>
                  <option value={2}>{format.number(2)}</option>
                  <option value={3}>{format.number(3)}</option>
                </select>
              </label>
            </div>
            <label className="local-analysis-input" htmlFor="local-analysis-text">{t('texts')}</label>
            <p id="local-analysis-input-help" className="dashboard-muted">
              {t('inputHelp', {min: analysisLimits.minTexts, max: analysisLimits.maxTexts, chars: analysisLimits.maxChars})}
            </p>
            <textarea id="local-analysis-text" aria-describedby="local-analysis-input-help" rows={7} value={text}
              onChange={event => updateText(event.target.value)} lang="en"
              maxLength={analysisLimits.maxBytes} autoComplete="off" autoCorrect="off" autoCapitalize="none" spellCheck={false} />
            <div className="local-analysis-actions">
              <button type="submit">{t('analyze')}</button>
              <button type="button" disabled={!text && !error && !result} onClick={() => updateText('')}>{t('clear')}</button>
              <span className="dashboard-muted">{t('textTotal', {count})}</span>
            </div>
          </fieldset>
        </form>
        {pending && <p className="dashboard-muted" role="status">{t('loading')}</p>}
        {error && <p className="local-analysis-error" role="alert">{t(`errors.${error}`)}</p>}
        {result && (
          <section className="local-analysis-results" aria-labelledby="local-analysis-results-heading">
            <h3 id="local-analysis-results-heading">{t('resultTitle')}</h3>
            {result.agreement !== null && (
              <div className="local-analysis-agreement">
                <h4>{t('agreementTitle')}</h4>
                <p role="status">{result.agreement.ari === null ? t('agreementUnavailable') : t('agreementValue', {
                  ari: format.number(result.agreement.ari, {minimumFractionDigits: 4, maximumFractionDigits: 4}),
                  count: result.agreement.common_assigned
                })}</p>
                <p>{t('agreementHelp')}</p>
              </div>
            )}
            <div className={result.agreement !== null ? 'local-method-comparison' : undefined}>
              {analysisMethods.map(name => {
                const computed = result.methods[name];
                if (!computed) return null;
                const processed = resultTextCount(computed);
                return (
                  <section key={name} className="local-method-result" aria-label={t(`methods.${name}`)}>
                    <h4>{t(`methods.${name}`)}</h4>
                    <p className="dashboard-muted" role="status">{t('resultSummary', {count: processed, k})}</p>
                    <p className="dashboard-muted">{t(name === 'nmf' ? 'nmfHelp' : 'minilmHelp')}</p>
                    <ul className="distribution-list">
                      {computed.groups.map(({size, keywords}, index) => (
                        <li key={index}>
                          <div className="bar-label"><span>{t('group', {number: index + 1})}</span><span>{format.number(size)}</span></div>
                          <div className="bar-track" aria-hidden="true"><div className="bar-fill" style={{width: `${size / processed * 100}%`}} /></div>
                          <p className="dashboard-muted">{keywords.length ? (
                            <>{t('keywords')} <span lang="en">{format.list(keywords, {type: 'unit'})}</span></>
                          ) : t('noKeywords')}</p>
                        </li>
                      ))}
                    </ul>
                    {computed.unassigned > 0 && <p className="dashboard-muted">{t('unassigned', {count: computed.unassigned})}</p>}
                    {computed.iteration_limit && <p className="dashboard-muted">{t('iterationLimit')}</p>}
                  </section>
                );
              })}
            </div>
          </section>
        )}
        {result?.expression_signals && <ExpressionSignals signals={result.expression_signals} />}
      </div>
      <p className="method-note">{t('limits')}</p>
    </section>
  );
}
