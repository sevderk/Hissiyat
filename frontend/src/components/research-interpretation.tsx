import {useEffect, useRef, useState} from 'react';
import {useLocale, useTranslations} from 'next-intl';
import {projectAIInterpretation, type AIInterpretation, type EvidenceFact, type EvidencePackage} from '@/lib/research-interpretation';
import {evidenceLabels} from '@/lib/expression-evidence';
import styles from './topic-research.module.css';

const errorCodes = ['model_unavailable', 'model_timeout', 'unsupported_claim', 'invalid_model_output', 'evidence_expired', 'busy', 'invalid_input'] as const;
type ErrorCode = typeof errorCodes[number];

function FactObservation({fact}: {fact: EvidenceFact}) {
  const t = useTranslations('TopicResearch.ai');
  const labels = useTranslations('TopicResearch.documentEvidence');
  const locale = useLocale();
  const format = new Intl.NumberFormat(locale, {maximumFractionDigits: 4});
  const display = (key: string) => fact.values[key] == null ? t('unknown') : typeof fact.values[key] === 'number'
    ? format.format(fact.values[key]) : String(fact.values[key]);
  switch (fact.metric) {
    case 'sample': return <p>{t('facts.sample', {retrieved: display('retrieved'), selected: display('selected'), analyzed: display('analyzed')})}</p>;
    case 'source_scope': return <p>{t('facts.source_scope', {limit: display('max_items'), examined: display('examined'), eligible: display('eligible')})}</p>;
    case 'coverage': return <p>{t('facts.coverage', {first: display('first'), last: display('last'), days: display('active_days')})}</p>;
    case 'expression': {
      const label = evidenceLabels.find(value => value === fact.values.label);
      return <p>{t('facts.expression', {label: label ? labels(`labels.${label}`) : t('unknown'),
        count: display('matched'), denominator: fact.denominator ?? t('unknown')})}</p>;
    }
    case 'no_expression_matches': return <p>{t('facts.no_expression_matches', {count: fact.denominator ?? t('unknown')})}</p>;
    case 'topic_partition': return <p>{t('facts.topic_partition', {method: fact.method === 'nmf' ? 'TF-IDF + NMF' : 'MiniLM + K-means',
      sizes: ['group_1', 'group_2', 'group_3'].filter(key => key in fact.values).map(display).join(' / '),
      count: fact.denominator ?? t('unknown'), assigned: display('assigned'), unassigned: display('unassigned'), silhouette: display('silhouette')})}
      {' '}{t('terms', {terms: ['terms_1', 'terms_2', 'terms_3'].map(key => fact.values[key]).filter(Boolean).join(' · ') || t('unknown')})}</p>;
    case 'agreement': return <p>{t('facts.agreement', {score: display('ari'), count: fact.denominator ?? t('unknown')})}</p>;
    case 'geography': return <p>{t('facts.geography', {geography: fact.values.geography === 'UNKNOWN' ? t('unknown') : display('geography')})}</p>;
    case 'search_summary': return <p>{t('facts.search_summary', {first: display('first_period'), last: display('last_period'),
      nonzero: display('nonzero'), zero: display('ambiguous_zero'), missing: display('missing'), suppressed: display('suppressed'),
      direction: t(`directions.${fact.values.direction as 'increased' | 'decreased' | 'unchanged' | 'insufficient'}`)})}</p>;
    default: {
      const metric = fact.metric as 'temporal_comparison' | 'expression_unavailable' | 'topic_validity' | 'topics_unavailable' |
        'expression_validity' | 'analysis_unavailable' | 'search_unverified' | 'search_limits' | 'context' | 'generalization';
      return <p>{t(`facts.${metric}`)}</p>;
    }
  }
}

export function ResearchInterpretationAI({evidence}: {evidence?: EvidencePackage}) {
  const t = useTranslations('TopicResearch.ai');
  const locale = useLocale() as 'tr' | 'en';
  const [report, setReport] = useState<AIInterpretation | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ErrorCode | null>(null);
  const abort = useRef<AbortController | null>(null);
  const catalogue = useRef<HTMLDetailsElement | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  const anchor = (id: string) => `ai-evidence-${evidence?.package_id}-${id}`;
  const cite = (id: string) => <a href={`#${anchor(id)}`} onClick={() => { if (catalogue.current) catalogue.current.open = true; }}>{id}</a>;
  async function generate() {
    if (!evidence || pending) return;
    setError(null); setReport(null); setPending(true);
    abort.current = new AbortController();
    try {
      const response = await fetch('/api/research-interpretation', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({package_id: evidence.package_id, language: locale}), cache: 'no-store', redirect: 'error',
        signal: AbortSignal.any([abort.current.signal, AbortSignal.timeout(165000)])});
      const data: unknown = await response.json();
      if (!response.ok) {
        const code = typeof data === 'object' && data !== null && 'code' in data && errorCodes.find(code => code === data.code);
        setError(code || 'model_unavailable');
      } else {
        const checked = projectAIInterpretation(data, evidence, locale);
        if (checked) setReport(checked);
        else setError('invalid_model_output');
      }
    } catch { if (!abort.current.signal.aborted) setError('model_unavailable'); }
    finally { setPending(false); }
  }
  return <section id="ai-research-interpretation" className={`${styles.panel} ${styles.aiPanel}`} aria-labelledby="ai-interpretation-heading">
    <h2 id="ai-interpretation-heading">{t('title')}</h2>
    <p>{t('intro')}</p>
    {evidence ? <>
      <p className={styles.hint}>{evidence.fictional ? t('fictional') : t('sourceGrounded')}</p>
      <p>{t('scope', {query: evidence.scope.query, first: evidence.scope.start_date, last: evidence.scope.end_date,
        geography: evidence.scope.geography === 'UNKNOWN' ? t('unknown') : evidence.scope.geography})}</p>
      <button type="button" className={styles.aiGenerate} onClick={generate} disabled={pending}>{pending ? t('loading') : t('generate')}</button>
      {pending && <p role="status">{t('waiting')}</p>}
      {error && <p role="alert">{t(`errors.${error}`)}</p>}
      {report && <div data-testid="ai-generated-result">
        <p className={styles.hint}>{t('generatedBy')} · {report.model}</p>
        <p>{t(report.result.status === 'insufficient' ? 'insufficient' : 'exploratory')}</p>
        <h3>{t('overview')}</h3><p lang={locale}>{report.result.overview.text} {cite(report.result.overview.evidence_id)}</p>
        <h3>{t('findings')}</h3>
        <ul>{report.result.findings.map(item => <li key={item.evidence_id}>
          <p lang={locale}>{item.interpretation} {cite(item.evidence_id)}</p>
          <span className={styles.hint}>{t(`kinds.${item.kind}`)}</span>
        </li>)}</ul>
        <h3>{t('uncertainties')}</h3>
        {report.result.uncertainties.map(item => <p key={item.evidence_id} lang={locale}>{item.text} {cite(item.evidence_id)}</p>)}
        <h3>{t('questions')}</h3>
        {report.result.questions.map(item => <p key={item.evidence_id} lang={locale}>{item.text} {cite(item.evidence_id)}</p>)}
      </div>}
      <details ref={catalogue} open={Boolean(report)} className={styles.evidenceDetails}>
        <summary>{t('evidence')}</summary>
        <p className={styles.hint}>{t('observations')}</p>
        <ol className={styles.explorer}>{evidence.facts.map(fact => <li key={fact.id} id={anchor(fact.id)}>
          <strong>{fact.id} · {t(`kinds.${fact.kind}`)}</strong>
          <FactObservation fact={fact} />
          <p className={styles.hint}>{t('method')} · <code>{fact.method}</code></p>
        </li>)}</ol>
        {evidence.source_reference && <a href={evidence.source_reference} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{t('source')}</a>}
      </details>
    </> : <p className={styles.hint}>{t('needsEvidence')}</p>}
    <p className={styles.hint}>{t('verification')}</p>
  </section>;
}
