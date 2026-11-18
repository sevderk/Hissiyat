import {useFormatter, useLocale, useTranslations} from 'next-intl';
import type {OfficialTrendsResult} from '@/lib/trends-research';
import styles from './topic-research.module.css';

export function TrendsOfficialResult({data}: {data: OfficialTrendsResult}) {
  const t = useTranslations('TopicResearch.officialTrends');
  const locale = useLocale();
  const format = useFormatter();
  const date = (value: string) => format.dateTime(new Date(value + 'T00:00:00Z'), {dateStyle: 'medium', timeZone: 'UTC'});
  const geography = new Intl.DisplayNames(locale, {type: 'region'}).of(data.requested_geography) ?? data.requested_geography;
  const summary = data.summary;

  return (
    <section className={styles.results} aria-labelledby="official-trends-result">
      <header className={styles.resultHeader}>
        <div>
          <p className={styles.eyebrow}>{t(data.source === 'fictional_trends_research' ? 'fixture' : 'source')}</p>
          <h2 id="official-trends-result">{data.term}</h2>
          <p>{t('requested', {geography, start: data.start_month, end: data.end_month})}</p>
        </div>
        <span>{t('summaryOnly')}</span>
      </header>
      <div className={styles.coverage}>
        <p>{t('points', {count: data.point_count})}</p>
        {summary ? <>
          <p>{t('measurement')}</p>
          <p>{t('observedScope', {cadence: t(summary.cadence), start: date(summary.first_period), end: date(summary.last_period)})}</p>
          <p>{t('pointStates', {nonzero: summary.nonzero, zero: summary.ambiguous_zero,
            missing: summary.missing, suppressed: summary.suppressed})}</p>
          <p>{summary.peak_period ? t('peak', {day: date(summary.peak_period), count: summary.peak_ties}) : t('noPeak')}</p>
          <p>{t(summary.direction)}</p>
        </> : <>
          <p>{t('withheld')}</p>
          <p>{t('shape', {date: t(data.date_kind ?? 'unknown'), value: t(data.value_kind ?? 'unknown')})}</p>
          {data.metadata_fields.length > 0 && <p>{t('detectedFields', {fields: data.metadata_fields.join(', ')})}</p>}
        </>}
        <p>{t('limits')}</p>
      </div>
    </section>
  );
}
