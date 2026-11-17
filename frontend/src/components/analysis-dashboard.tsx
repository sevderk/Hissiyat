'use client';

import {useEffect, useState} from 'react';
import {useFormatter, useTranslations} from 'next-intl';
import {TrendPlot} from '@/components/trend-plot';
import {categories, cohorts, isSearchInterest, isTextAnalysis} from '@/lib/demo-contract';
import type {Cohort, Group, InterestPoint, SearchInterest, TextAnalysis} from '@/lib/demo-contract';

type LoadState<T> =
  | {status: 'loading'}
  | {status: 'unavailable' | 'invalid'}
  | {status: 'ready'; data: T};

function useDemo<T>(url: string, validate: (data: unknown) => data is T) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{url: string; attempt: number; state: LoadState<T>}>();

  useEffect(() => {
    const controller = new AbortController();
    const publish = (state: LoadState<T>) => {
      if (!controller.signal.aborted) setResult({url, attempt, state});
    };
    async function load() {
      try {
        const response = await fetch(url, {signal: controller.signal, cache: 'no-store'});
        if (!response.ok) {
          publish({status: response.status === 502 ? 'invalid' : 'unavailable'});
          return;
        }
        try {
          const data: unknown = await response.json();
          publish(validate(data) ? {status: 'ready', data} : {status: 'invalid'});
        } catch {
          publish({status: 'invalid'});
        }
      } catch {
        publish({status: 'unavailable'});
      }
    }
    void load();
    return () => controller.abort();
  }, [url, attempt, validate]);

  const state: LoadState<T> = result?.url === url && result.attempt === attempt ? result.state : {status: 'loading'};
  return {state, retry: () => setAttempt((previous) => previous + 1)};
}

function StatusPanel({status, retry}: {status: 'loading' | 'unavailable' | 'invalid' | 'empty'; retry?: () => void}) {
  const t = useTranslations('Dashboard');
  const failed = status === 'invalid' || status === 'unavailable';
  return (
    <div className="dashboard-state">
      <p role={failed ? 'alert' : 'status'}>{t(`states.${status}`)}</p>
      {failed && retry && <button type="button" onClick={retry}>{t('states.retry')}</button>}
    </div>
  );
}

function Distribution({group, data}: {group: Group; data: TextAnalysis}) {
  const t = useTranslations('Dashboard');
  const format = useFormatter();
  const entries = data.groups[group];
  return (
    <article className={'dashboard-card distribution ' + group} aria-labelledby={'distribution-' + group}>
      <h4 id={'distribution-' + group}>{t(`groups.${group}`)}</h4>
      {entries.length ? (
        <ul className="distribution-list">
          {entries.map(({key, count}) => {
            const share = count / data.document_count;
            const ratio = format.number(share, {style: 'percent', maximumFractionDigits: 1});
            return (
              <li key={key}>
                <div className="bar-label">
                  <span>{t(`categories.${key}`)}</span>
                  <span className="sr-only">{t('categoryValue', {count, total: data.document_count, ratio})}</span>
                  <span aria-hidden="true">
                    {format.number(count)} <small>{ratio}</small>
                  </span>
                </div>
                <div className="bar-track" aria-hidden="true">
                  <div className="bar-fill" style={{width: (share * 100) + '%'}} />
                </div>
              </li>
            );
          })}
        </ul>
      ) : <p className="dashboard-muted">{t('states.noCategories')}</p>}
    </article>
  );
}

const textValidators = {
  general: (data: unknown): data is TextAnalysis => isTextAnalysis(data, 'general'),
  'uncertainty-enriched': (data: unknown): data is TextAnalysis => isTextAnalysis(data, 'uncertainty-enriched')
};

function HumanExperience() {
  const t = useTranslations('Dashboard');
  const format = useFormatter();
  const [cohort, setCohort] = useState<Cohort>('general');
  const {state, retry} = useDemo('/api/demo/text-analysis?cohort=' + cohort, textValidators[cohort]);
  const data = state.status === 'ready' ? state.data : null;
  return (
    <section className="analysis-section human-section" aria-labelledby="human-heading">
      <div className="analysis-heading">
        <div>
          <p className="source-label">{t('human.source')}</p>
          <h3 id="human-heading">{t('human.title')}</h3>
          <p className="section-description">{t('human.description')}</p>
        </div>
        <fieldset className="cohort-picker">
          <legend>{t('human.cohort')}</legend>
          <div className="cohort-options">
            {cohorts.map((option) => (
              <label key={option}>
                <input type="radio" name="cohort" value={option} checked={cohort === option}
                  onChange={() => setCohort(option)} />
                <span>{t(`cohorts.${option}`)}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>
      <div aria-busy={state.status === 'loading'} data-testid="text-results">
        {state.status !== 'ready' && <StatusPanel status={state.status} retry={retry} />}
        {data && (
          <>
            <div className="cohort-summary" role="status">
              <div className="document-metric">
                <strong data-testid="document-count">{format.number(data.document_count)}</strong>
                <span>{t('human.documents')}</span>
              </div>
              <div className="cohort-note">
                <strong>{t(`cohorts.${cohort}`)}</strong>
                <p data-testid="cohort-caveat">{t(`caveats.${cohort}`)}</p>
              </div>
            </div>
            {data.document_count > 0 ? (
              <div className="distribution-grid">
                {(Object.keys(categories) as Group[]).map((group) => <Distribution key={group} group={group} data={data} />)}
              </div>
            ) : <StatusPanel status="empty" />}
          </>
        )}
      </div>
      <details className="method-note">
        <summary>{t('methodology')}</summary>
        <p>{t('human.method')}</p>
        <p>{t('human.limit')}</p>
      </details>
    </section>
  );
}

function InterestChart({points}: {points: InterestPoint[]}) {
  const t = useTranslations('Dashboard');
  const format = useFormatter();
  const date = (value: string, short = false) => format.dateTime(new Date(value + 'T00:00:00Z'),
    {month: 'short', day: 'numeric', year: short ? undefined : 'numeric', timeZone: 'UTC'});
  const observed = points.filter((point) => point.status === 'observed').length;
  return (
    <div className="dashboard-card trend-card" data-testid="trend-data">
      <div className="trend-meta">
        <div><span>{t('search.queryLabel')}</span><h4>{t('search.query')}</h4></div>
        <div><span>{t('search.geographyLabel')}</span><strong>{t('search.geography')}</strong></div>
        <div><span>{t('search.periodLabel')}</span><strong>{t('search.weekly')}</strong></div>
        <div><span>{t('search.rangeLabel')}</span><strong>{date(points[0].date)} – {date(points[points.length - 1].date)}</strong></div>
      </div>
      {observed ? (
        <figure className="trend-figure">
          <figcaption>
            <span>{t('search.scale')}</span>
            <span>{t('search.coverage', {observed, weeks: points.length})}</span>
          </figcaption>
          <TrendPlot points={points} ticks={[100, 75, 50, 25, 0]} chartLabel={t('search.chartLabel')}
            formatDate={value => date(value, true)} formatValue={format.number} />
          <ul className="trend-legend">
            <li><i className="legend-observed" aria-hidden="true" />{t('search.observed')}</li>
            <li><i className="legend-missing" aria-hidden="true" />{t('search.missing')}</li>
            <li><i className="legend-suppressed" aria-hidden="true" />{t('search.suppressed')}</li>
          </ul>
        </figure>
      ) : <StatusPanel status="empty" />}
      <details className="method-note trend-values">
        <summary>{t('search.values')}</summary>
        <ul>
          {points.map((point) => <li key={point.date}>
            <time dateTime={point.date}>{date(point.date)}</time>
            <span>{point.value === null ? t(`search.${point.status}`) : format.number(point.value)}</span>
          </li>)}
        </ul>
      </details>
    </div>
  );
}

function SearchInterestSection() {
  const t = useTranslations('Dashboard');
  const {state, retry} = useDemo<SearchInterest>('/api/demo/search-interest', isSearchInterest);
  return (
    <section className="analysis-section search-section" aria-labelledby="search-heading">
      <div className="analysis-heading">
        <div>
          <p className="source-label">{t('search.source')}</p>
          <h3 id="search-heading">{t('search.title')}</h3>
          <p className="section-description">{t('search.description')}</p>
        </div>
      </div>
      <div aria-busy={state.status === 'loading'} data-testid="search-results">
        {state.status !== 'ready' ? <StatusPanel status={state.status} retry={retry} /> :
          state.data.points.length ? <InterestChart points={state.data.points} /> : <StatusPanel status="empty" />}
      </div>
      <details className="method-note">
        <summary>{t('methodology')}</summary>
        <p>{t('search.method')}</p>
        <p>{t('search.limit')}</p>
      </details>
    </section>
  );
}

export function AnalysisDashboard() {
  return <><HumanExperience /><SearchInterestSection /></>;
}
