import {useTranslations} from 'next-intl';
import {evidenceLabels} from '@/lib/expression-evidence';
import type {ResearchResult} from '@/lib/topic-research';
import styles from './topic-research.module.css';

export function DiscussionEvidence({analysis}: {analysis: NonNullable<ResearchResult['discussion_analysis']>}) {
  const t = useTranslations('TopicResearch.documentEvidence');
  const {processing, expression_evidence: findings} = analysis;
  if (!processing || !findings) return null;
  const skipped = Object.values(processing.excluded).reduce((sum, count) => sum + count, 0);
  const abstained = Object.values(findings.abstentions).reduce((sum, count) => sum + count, 0);
  const observed = evidenceLabels.filter(label => findings.counts[label] > 0);
  return (
    <section className={styles.panel} aria-labelledby="discussion-evidence-heading">
      <h3 id="discussion-evidence-heading">{t('heading')}</h3>
      <p>{t('processing', {documents: processing.documents, segments: processing.segments, characters: processing.characters, skipped})}</p>
      <p className={styles.hint}>{t('method')}</p>
      <p className={styles.hint}>{t('limits')}</p>
      <dl className={styles.signalCounts}>
        {observed.map(label => <div key={label}><dt>{t(`labels.${label}`)}</dt>
          <dd>{t('count', {count: findings.counts[label], denominator: findings.documents})}</dd></div>)}
      </dl>
      {findings.evidence.length ? <details className={styles.evidenceDetails}>
        <summary>{t('showEvidence', {count: findings.evidence.length})}</summary>
        <ol className={styles.explorer}>
          {findings.evidence.map((item, index) => <li key={`${item.row}-${item.start}-${item.rule}-${item.label}-${index}`}>
            <a href={`#research-document-${item.row}`}>{t('document', {number: item.row + 1})}</a>
            <p>{t('span', {start: item.start, end: item.end})} · {t(`labels.${item.label}`)}</p>
            <p className={styles.hint}>{t(`rules.${item.rule}`)} · <code>{item.rule}</code></p>
            {item.text ? <blockquote className={styles.evidenceQuote} lang="en">{item.text}</blockquote>
              : <p className={styles.hint}>{t('sourceWithheld')}</p>}
          </li>)}
        </ol>
      </details> : <p>{t('none')}</p>}
      <p className={styles.hint}>{t('abstentions', {count: abstained})}</p>
    </section>
  );
}
