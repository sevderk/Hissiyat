'use client';

import {useState} from 'react';
import {useFormatter, useLocale, useTranslations} from 'next-intl';
import {TrendPlot} from '@/components/trend-plot';
import {compareInterest, summarizeInterest, type TrendsExport} from '@/lib/trends-csv';
import type {TrendPoint} from '@/lib/trends-research';
import styles from './topic-research.module.css';

export function TrendsCsvResults({data, sha256}: {data: TrendsExport; sha256: string}) {
  const t = useTranslations('TopicResearch.importedTrends');
  const format = useFormatter();
  const locale = useLocale();
  const [active, setActive] = useState(0);
  const points = data.series[0].points;
  const date = (value: string, short = false) => format.dateTime(new Date(value + 'T00:00:00Z'),
    {month: 'short', day: 'numeric', ...(short ? {} : {year: 'numeric'}), timeZone: 'UTC'});
  const number = (value: number) => format.number(value, {maximumFractionDigits: 6});
  const regionFormatter = new Intl.DisplayNames(locale, {type: 'region'});
  const region = (value: string) => value === 'worldwide' ? t('worldwide') : regionFormatter.of(value) ?? value;
  const displayValue = ({value, status}: TrendPoint) => value === null
    ? t(status === 'suppressed' ? 'suppressed' : 'missing') : number(value);
  const comparison = compareInterest(data);
  const tableStart = Math.max(0, Math.min(active - 3, points.length - 7));

  return (
    <section className={styles.results} aria-labelledby="trends-import-result">
      <header className={styles.resultHeader}>
        <div>
          <p className={styles.eyebrow}>{t('measurement')}</p>
          <h2 id="trends-import-result">{data.term}</h2>
          <p>{t('source')}</p>
        </div>
        <span>{t(data.interval)}</span>
      </header>
      <div className={styles.coverage}>
        <p>{t('requestedRange', {start: date(data.start), end: date(data.end)})}</p>
        <p>{t('actualRange', {start: date(points[0].date), end: date(points.at(-1)!.date), count: points.length})}</p>
        <p>{t(comparison ? 'sharedScale' : 'singleScale')}</p>
      </div>
      <section className={styles.panel} aria-labelledby="trends-import-chart">
        <h3 id="trends-import-chart">{t('chart')}</h3>
        <figure className="trend-figure">
          <figcaption>{t('measurement')}</figcaption>
          <TrendPlot points={points} comparison={data.series[1]?.points} activeIndex={active} ticks={[100, 50, 0]}
            chartLabel={t('chartLabel', {regions: data.series.map(({region: code}) => region(code)).join(' / ')})}
            formatDate={value => date(value, true)} formatValue={number} />
          <ul className="trend-legend">
            {data.series.map(({region: code}, index) => <li key={code}>
              <i className={index ? 'legend-comparison' : 'legend-observed'} aria-hidden="true" />
              {region(code)}
            </li>)}
            <li><i className="legend-missing" aria-hidden="true" />{t('missing')}</li>
            <li><i className="legend-suppressed" aria-hidden="true" />{t('suppressed')}</li>
          </ul>
        </figure>
        {points.length > 1 && <label className={styles.field}>{t('selectPeriod')}
          <input type="range" min={0} max={points.length - 1} step={1} value={active}
            aria-valuetext={date(points[active].date)} onChange={event => setActive(event.target.valueAsNumber)} />
        </label>}
        <p role="status">{date(points[active].date)} · {data.series.map(line =>
          `${region(line.region)} ${displayValue(line.points[active])}`).join(' · ')}</p>
        <table className={styles.trendsTable}>
          <caption>{t('table')}</caption>
          <thead><tr><th scope="col">{t('period')}</th>{data.series.map(line =>
            <th key={line.region} scope="col">{region(line.region)}</th>)}</tr></thead>
          <tbody>{points.slice(tableStart, tableStart + 7).map((point, offset) => (
            <tr key={point.date} data-selected={offset + tableStart === active || undefined}>
              <th scope="row"><time dateTime={point.date}>{date(point.date)}</time></th>
              {data.series.map(line => <td key={line.region}>{displayValue(line.points[tableStart + offset])}</td>)}
            </tr>
          ))}</tbody>
        </table>
      </section>
      <section className={`${styles.panel} ${styles.interpretation}`} aria-labelledby="trends-interpretation">
        <h3 id="trends-interpretation">{t('interpretation')}</h3>
        {data.series.map(line => {
          const summary = summarizeInterest(line.points);
          return (
            <div key={line.region}>
              <h4>{region(line.region)}</h4>
              <p>{t('coverage', {observed: summary.observed, total: points.length,
                missing: summary.missing, suppressed: summary.suppressed})}</p>
              {summary.peak && summary.trough ? <>
                <p>{t('extremes', {peak: number(summary.peak.value), peakDate: date(summary.peak.date), peaks: summary.peak.periods,
                  trough: number(summary.trough.value), troughDate: date(summary.trough.date), troughs: summary.trough.periods})}</p>
                {summary.first && summary.last && summary.change !== null && <p>{t(
                  summary.change > 0 ? 'increase' : summary.change < 0 ? 'decrease' : 'unchanged',
                  {from: number(summary.first.value), fromDate: date(summary.first.date), to: number(summary.last.value),
                    toDate: date(summary.last.date), delta: number(Math.abs(summary.change))}
                )}</p>}
              </> : <p>{t('noObserved')}</p>}
            </div>
          );
        })}
        {comparison && <p>{comparison.aligned ? t('compare', {...comparison, first: region(data.series[0].region),
          second: region(data.series[1].region), total: points.length}) : t('noComparison')}</p>}
        <p>{t('limits')}</p>
        <p>{t('separate')}</p>
        <details>
          <summary>{t('provenance')}</summary>
          <p>{t('provenanceNote')}</p>
          <p className={styles.trendsHash}>SHA-256 <code>{sha256}</code></p>
          <p><a href={data.url} target="_blank" rel="noopener noreferrer">{t('original')}</a></p>
        </details>
      </section>
    </section>
  );
}
