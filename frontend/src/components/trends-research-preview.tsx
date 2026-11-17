'use client';

import {useEffect, useState} from 'react';
import {useFormatter, useTranslations} from 'next-intl';
import {TrendPlot} from '@/components/trend-plot';
import {isTrendsPreview, type TrendsPreview} from '@/lib/trends-research';

function ResearchSeries({data}: {data: TrendsPreview}) {
  const t = useTranslations('TrendsResearch');
  const format = useFormatter();
  const date = (value: string, short = false) => format.dateTime(new Date(value + 'T00:00:00Z'),
    {month: 'short', day: 'numeric', year: short ? undefined : 'numeric', timeZone: 'UTC'});
  const number = (value: number) => format.number(value, {maximumSignificantDigits: 17});
  const values = data.points.flatMap(point => point.value === null ? [] : [point.value]);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const ticks = [...new Set([max, max / 2 + min / 2, min])];

  return (
    <div className="dashboard-card trend-card" data-testid="trends-research-series">
      <p className="source-label">{t(data.source === 'fictional_fixture' ? 'fictional' : 'source')}</p>
      <div className="trend-meta">
        <div><span>{t('term')}</span><strong lang="en">{data.term}</strong></div>
        <div><span>{t('geography')}</span><strong>{data.geography === 'worldwide' ? t('worldwide') : data.geography}</strong></div>
        <div><span>{t('period')}</span><strong>{t(data.granularity)}</strong></div>
        <div><span>{t('range')}</span><strong>{date(data.points[0].date)} – {date(data.points.at(-1)!.date)}</strong></div>
      </div>
      <figure className="trend-figure">
        <figcaption>{t(data.source === 'fictional_fixture' ? 'fixtureScale' : 'scale')}</figcaption>
        <TrendPlot points={data.points} ticks={ticks} chartLabel={t('chartLabel')}
          formatDate={value => date(value, true)} formatValue={number} />
        <ul className="trend-legend">
          <li><i className="legend-observed" aria-hidden="true" />{t('observed')}</li>
          <li><i className="legend-missing" aria-hidden="true" />{t('missing')}</li>
          <li><i className="legend-suppressed" aria-hidden="true" />{t('suppressed')}</li>
        </ul>
      </figure>
      <details className="method-note trend-values">
        <summary>{t('values')}</summary>
        <ul>
          {data.points.map(point => <li key={point.date}>
            <time dateTime={point.date}>{date(point.date)}</time>
            <span>{point.value === null ? t(point.status === 'missing' ? 'missing' : 'suppressed') : number(point.value)}</span>
          </li>)}
        </ul>
      </details>
    </div>
  );
}

export function TrendsResearchPreview() {
  const t = useTranslations('TrendsResearch');
  const [data, setData] = useState<TrendsPreview | null>();

  useEffect(() => {
    const abort = new AbortController();
    async function load() {
      try {
        const response = await fetch('/api/trends-preview', {cache: 'no-store', credentials: 'omit', signal: abort.signal});
        const payload: unknown = response.ok ? await response.json() : null;
        if (!abort.signal.aborted) setData(isTrendsPreview(payload) ? payload : null);
      } catch {
        if (!abort.signal.aborted) setData(null);
      }
    }
    void load();
    return () => abort.abort();
  }, []);

  return (
    <section id="trends-research" className="analysis-section search-section" aria-labelledby="trends-research-heading">
      <div className="analysis-heading"><h2 id="trends-research-heading">{t('title')}</h2></div>
      {data ? <ResearchSeries data={data} /> : <p className="dashboard-state" role="status">{t(data === undefined ? 'loading' : 'withheld')}</p>}
      <div className="method-note"><p>{t('limits')}</p><p>{t('alignment')}</p></div>
    </section>
  );
}
