import {useLocale, useTranslations} from 'next-intl';
import data from '@/lib/civil-comparison-data.json';
import {comparisonPolicies, comparisonQuestions, projectCivilComparison, type PolicySummary} from '@/lib/civil-comparison';
import {evidenceLabels} from '@/lib/expression-evidence';
import type {LocalAnalysisResult} from '@/lib/local-analysis-contract';
import styles from './topic-research.module.css';
import {ResearchInterpretationAI} from './research-interpretation';

const comparison = projectCivilComparison(data);
const coverage = ['matched', 'length', 'eligible', 'selected', 'analyzed', 'selected_long_documents',
  'characters', 'segments', 'documents_with_expressions', 'evidence_spans'] as const;

function QualityRows({policies}: {policies: Record<'legacy' | 'updated', PolicySummary>}) {
  const t = useTranslations('TopicResearch.policyComparison');
  const locale = useLocale();
  const decimal = new Intl.NumberFormat(locale, {maximumFractionDigits: 4});
  const score = (value: number | null | undefined) => value == null ? '—' : decimal.format(value);
  function row(policy: 'legacy' | 'updated', k: number, topics: LocalAnalysisResult | null) {
    return <tr key={`${policy}-${k}`}><th scope="row">{t(policy)} · k={k}</th>
      {(['nmf', 'minilm'] as const).map(method => <td key={method}>
        {topics?.methods[method]?.groups.map(group => group.size).join(' / ') ?? '—'}
      </td>)}
      <td>{score(topics?.agreement?.ari)}</td>
      <td>{score(topics?.separation?.nmf)}</td><td>{score(topics?.separation?.minilm)}</td>
    </tr>;
  }
  return <div className={styles.comparisonScroll} tabIndex={0} role="region" aria-label={t('quality')}>
    <table className={styles.trendsTable}><caption>{t('quality')}</caption>
      <thead><tr>{(['policy', 'nmfSizes', 'minilmSizes', 'ari', 'nmfSilhouette', 'minilmSilhouette'] as const).map(key =>
        <th key={key} scope="col">{t(key)}</th>)}</tr></thead>
      <tbody>{comparisonPolicies.flatMap(policy => [row(policy, 2, policies[policy].topics), row(policy, 3, policies[policy].sensitivity.topics)])}</tbody>
    </table>
  </div>;
}

export function CivilComparison() {
  const t = useTranslations('TopicResearch.policyComparison');
  const labels = useTranslations('TopicResearch.documentEvidence');
  const locale = useLocale();
  const number = new Intl.NumberFormat(locale);
  if (!comparison) return null;
  return <section id="civil-policy-comparison" className={styles.panel} aria-labelledby="civil-comparison-heading">
    <h2 id="civil-comparison-heading">{t('title')}</h2>
    <p>{t('scope')}</p>
    <p className={styles.hint}>{t('policies')}</p>
    {comparisonQuestions.map(question => {
      const result = comparison.questions[question];
      const newer = result.updated;
      return <details key={question} open={question === 'wages'} className={styles.evidenceDetails} data-comparison-question={question}>
        <summary>{t(question)}</summary>
        <p className={styles.hint}>{t('query', {query: result.query})}</p>
        <table className={styles.trendsTable}><caption>{t('coverage')}</caption>
          <thead><tr><th scope="col">{t('measure')}</th>{comparisonPolicies.map(policy => <th scope="col" key={policy}>{t(policy)}</th>)}</tr></thead>
          <tbody>{coverage.map(metric => <tr key={metric}><th scope="row">{t(`metrics.${metric}`)}</th>
            {comparisonPolicies.map(policy => {
              const value = metric === 'length' ? result[policy].screening.length : result[policy][metric];
              return <td key={policy}>{value === null ? '—' : number.format(value)}</td>;
            })}</tr>)}</tbody>
        </table>
        <p>{t('selection', result.selection)}</p>
        <p>{t('paired', {documents: result.paired.documents, legacy_detected_documents: result.paired.legacy_detected_documents,
          updated_detected_documents: result.paired.updated_detected_documents})}</p>
        <p className={styles.hint}>{t('pairedCaution')}</p>
        <p>{t('evidence', {documents: newer.documents_with_expressions, denominator: newer.analyzed,
          spans: newer.evidence_spans ?? 0, late: newer.late_evidence_documents ?? 0})}</p>
        <p>{t('abstentions', {quoted: newer.abstentions?.quoted ?? 0, ambiguous: newer.abstentions?.ambiguous ?? 0,
          limited: newer.abstentions?.evidence_limit ?? 0})}</p>
        <details className={styles.evidenceDetails}>
          <summary>{t('categories')}</summary>
          <table className={styles.trendsTable}>
            <caption>{t('categoryDenominators', {legacy: result.legacy.analyzed, updated: newer.analyzed})}</caption>
            <thead><tr><th scope="col">{t('category')}</th>{comparisonPolicies.map(policy => <th scope="col" key={policy}>{t(policy)}</th>)}</tr></thead>
            <tbody>{evidenceLabels.map(label => <tr key={label}><th scope="row">{labels(`labels.${label}`)}</th>
              {comparisonPolicies.map(policy => <td key={policy}>{result[policy].counts[label] == null ? '—' : number.format(result[policy].counts[label]!)}</td>)}
            </tr>)}</tbody>
          </table>
          <p className={styles.hint}>{t('unsupported')}</p>
          <ul>{Object.entries(newer.rule_documents ?? {}).map(([rule, count]) => <li key={rule}>
            <code>{rule}</code> · {t('ruleCount', {count, denominator: newer.analyzed})}
          </li>)}</ul>
          <p>{t('pairedCategories', {count: result.paired.documents})}</p>
          <ul>{evidenceLabels.slice(0, 9).map(label => <li key={label}>
            {labels(`labels.${label}`)} · {t('changes', result.paired.categories[label])}
          </li>)}</ul>
        </details>
        <details className={styles.evidenceDetails}><summary>{t('quality')}</summary>
          <QualityRows policies={result} />
          <p className={styles.hint}>{t('qualityCaution')}</p>
          <p>{t('availability', {legacy: t(`statuses.${result.legacy.status}`), updated: t(`statuses.${newer.status}`)})}</p>
        </details>
        <ResearchInterpretationAI key={`${locale}-${question}`} id={`historical-ai-${question}`} input={{source: 'historical', question}} />
      </details>;
    })}
    <p className={styles.hint}>{t('limitations')}</p>
    <p className={styles.hint}>{t('normalization')}</p>
    <p><a href="https://huggingface.co/datasets/google/jigsaw_unintended_bias">{t('source')}</a>
      {' · '}<a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0 1.0</a>
      {' · '}<time dateTime={comparison.retrieved_at}>{comparison.retrieved_at.slice(0, 10)} UTC</time></p>
  </section>;
}
