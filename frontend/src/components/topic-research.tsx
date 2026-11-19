'use client';

import {useLocale, useTranslations} from 'next-intl';
import {type FormEvent, useState} from 'react';
import {TrendsCsvResults} from '@/components/trends-csv-results';
import {TrendsOfficialResult} from '@/components/trends-official-result';
import {DiscussionEvidence} from '@/components/discussion-evidence';
import {CivilComparison} from '@/components/civil-comparison';
import {ResearchInterpretationAI} from '@/components/research-interpretation';
import {expressionCategories} from '@/lib/local-analysis-contract';
import {decodeTrendsCsv, importTrendsCsv, maxTrendsCsvBytes, readExploreLink, TrendsCsvError, type TrendsExport} from '@/lib/trends-csv';
import {projectOfficialTrends, trendsCountries, type OfficialTrendsResult, type TrendsCountry} from '@/lib/trends-research';
import {civilDates, civilDistribution, civilScreeningReasons, projectResearchResult, researchErrorFor, researchSources, researchUpstreamStatus,
  topicEvidence, wikimediaTitle, type ResearchError,
  type ResearchResult, type ResearchScope, type ResearchSource} from '@/lib/topic-research';
import styles from './topic-research.module.css';

function methodTitle(method: string) {
  return method === 'nmf' ? 'TF-IDF + NMF' : 'MiniLM + K-means';
}

function recentScope(): ResearchScope {
  const today = new Date();
  return {
    mode: 'topic', query: '', source: 'fictional', language: null, geography: null,
    start_date: new Date(today.getTime() - 13 * 86400000).toISOString().slice(0, 10),
    end_date: today.toISOString().slice(0, 10),
  };
}

function previousMonth(monthsAgo: number) {
  const today = new Date();
  return new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - monthsAgo, 1)).toISOString().slice(0, 7);
}

export function TopicResearch({enabled}: {enabled: boolean}) {
  const t = useTranslations('TopicResearch');
  const locale = useLocale();
  const [scope, setScope] = useState(recentScope);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState<{code: ResearchError; upstream?: number | null} | null>(null);
  const [pending, setPending] = useState(false);
  const [exploreLink, setExploreLink] = useState('');
  const [trendsFile, setTrendsFile] = useState<File | null>(null);
  const [sameChart, setSameChart] = useState(false);
  const [trendsError, setTrendsError] = useState<TrendsCsvError['code'] | null>(null);
  const [trendsResult, setTrendsResult] = useState<{data: TrendsExport; sha256: string} | null>(null);
  const [officialResult, setOfficialResult] = useState<OfficialTrendsResult | null>(null);
  const importingTrends = scope.source === 'google_trends_csv';
  const queryingTrends = scope.source === 'google_trends';
  const isTrends = importingTrends || queryingTrends;

  function chooseExample(mode: ResearchScope['mode']) {
    setScope({mode, source: 'fictional', query: t(mode === 'topic' ? 'exampleTopicQuery' : 'exampleEventQuery'),
      start_date: '2026-11-05', end_date: '2026-11-16', language: locale === 'tr' ? 'tr' : 'en', geography: null});
    setError(null);
    setResult(null);
  }

  function chooseDiscussion() {
    setScope({mode: 'topic', source: 'fictional', query: 'community services', start_date: '2026-11-05',
      end_date: '2026-11-16', language: 'en', geography: null, content: 'mixed', analyze_discussion: true});
    setError(null);
    setResult(null);
  }

  function chooseLongDiscussion() {
    setScope({mode: 'topic', source: 'fictional', query: 'public service research', start_date: '2026-11-05',
      end_date: '2026-11-16', language: 'en', geography: null, content: 'mixed', analyze_discussion: true});
    setError(null);
    setResult(null);
  }

  function chooseSource(source: ResearchSource) {
    if (source === 'wikimedia') {
      setScope({...recentScope(), source, query: wikimediaTitle, start_date: '2001-01-01',
        language: null, content: 'comments', analyze_discussion: true});
    } else if (source === 'civil_comments') {
      setScope({...scope, source, query: scope.source === 'wikimedia' ? '' : scope.query,
        start_date: civilDates.first, end_date: civilDates.last, language: 'en', geography: null, content: 'comments', analyze_discussion: true});
    } else if (source === 'google_trends') {
      setScope({...scope, source, query: scope.source === 'wikimedia' ? '' : scope.query, geography: 'TR',
        start_date: previousMonth(2) + '-01', end_date: previousMonth(1) + '-01',
        language: null, content: undefined, analyze_discussion: undefined});
    } else if (source === 'google_trends_csv') {
      setScope({...scope, source, geography: null, language: null, content: undefined, analyze_discussion: undefined});
    } else {
      setScope({...scope, ...(['wikimedia', 'civil_comments'].includes(scope.source) || isTrends ? recentScope() : {}), source,
        geography: null, language: source === 'lemmy' ? null : scope.language, content: undefined, analyze_discussion: undefined});
    }
    setError(null);
    setTrendsError(null);
    if (source !== 'google_trends' && source !== 'google_trends_csv' && !isTrends) setResult(null);
  }

  function applyExploreLink(link: string) {
    setExploreLink(link);
    setSameChart(false);
    try {
      const input = readExploreLink(link);
      setScope(current => ({...current, query: input.term, start_date: input.start, end_date: input.end}));
      setTrendsError(null);
    } catch {
      // Validate on submit so typing or pasting a partial link does not announce errors.
    }
  }

  async function importInterest() {
    setTrendsResult(null);
    setTrendsError(null);
    try {
      if (window.location.hostname !== '127.0.0.1') throw new TrendsCsvError('link');
      const input = readExploreLink(exploreLink);
      if (input.term !== scope.query || input.start !== scope.start_date || input.end !== scope.end_date) {
        throw new TrendsCsvError('scope');
      }
      if (!trendsFile || !/\.csv$/i.test(trendsFile.name)) throw new TrendsCsvError('file');
      if (trendsFile.size > maxTrendsCsvBytes) throw new TrendsCsvError('size');
      const buffer = await trendsFile.arrayBuffer().catch(() => { throw new TrendsCsvError('file'); });
      const data = importTrendsCsv(decodeTrendsCsv(buffer), input);
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', buffer));
      const sha256 = Array.from(digest, value => value.toString(16).padStart(2, '0')).join('');
      setTrendsResult({data, sha256});
    } catch (failure) {
      setTrendsError(failure instanceof TrendsCsvError ? failure.code : 'parser');
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled || pending) return;
    setPending(true);
    setError(null);
    try {
      if (importingTrends) {
        await importInterest();
        return;
      }
      if (queryingTrends) setOfficialResult(null);
      else setResult(null);
      const response = await fetch('/api/topic-research', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(scope),
        cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(scope.source === 'civil_comments' || queryingTrends ? 95000 : 20000),
      });
      const data: unknown = await response.json();
      if (!response.ok) {
        const code = researchErrorFor(response.status, data);
        setError({code, upstream: researchUpstreamStatus(code, data)});
      }
      else if (queryingTrends) {
        const checked = projectOfficialTrends(data);
        if (checked && checked.mode === scope.mode && checked.term === scope.query.normalize('NFC').trim().replace(/\s+/g, ' ') &&
            checked.requested_geography === scope.geography && checked.start_month === scope.start_date.slice(0, 7) &&
            checked.end_month === scope.end_date.slice(0, 7)) setOfficialResult(checked);
        else setError({code: 'unavailable'});
      } else {
        const checked = projectResearchResult(data);
        if (checked) setResult(checked);
        else setError({code: 'unavailable'});
      }
    } catch {
      setError({code: 'unavailable'});
    } finally {
      setPending(false);
    }
  }

  const historical = scope.source === 'civil_comments';

  return (
    <section id="topic-research" className={styles.workspace} aria-labelledby="topic-research-heading">
      <header className={styles.hero}>
        <p className={styles.eyebrow}>{t('workspace')}</p>
        <h1 id="topic-research-heading">{t('title')}</h1>
        <p>{t('intro')}</p>
      </header>
      <div className={styles.grid}>
        <form onSubmit={submit} className={styles.panel} autoComplete="off">
          <fieldset className={styles.fields} disabled={!enabled || pending || undefined}>
            <legend>{t('modeLegend')}</legend>
            <div className={styles.mode}>
              {(['topic', 'event'] as const).map(mode => (
                <label key={mode}>
                  <input name="research-mode" type="radio" value={mode} checked={scope.mode === mode} disabled={scope.source === 'wikimedia' && mode === 'event'}
                    onChange={() => setScope({...scope, mode})} />
                  {t(mode)}
                </label>
              ))}
            </div>
            <label className={styles.field}>{t('query')}
              <input required type="text" minLength={2} maxLength={120} value={scope.query} autoComplete="off" readOnly={scope.source === 'wikimedia'}
                placeholder={t(scope.mode === 'topic' ? 'topicPlaceholder' : 'eventPlaceholder')}
                onChange={event => setScope({...scope, query: event.target.value})} />
            </label>
            <p className={styles.hint}>{t(queryingTrends ? 'officialTrends.termHelp' : importingTrends ? 'importedTrends.linkScopeHelp' : scope.source === 'wikimedia' ? 'wikiScopeHelp' : scope.source === 'lemmy'
              ? 'lemmyQueryHelp' : historical ? 'civilScopeHelp' : scope.mode === 'topic' ? 'topicHelp' : 'eventHelp')}</p>
            <div className={styles.pair}>
              <label className={styles.field}>{t(queryingTrends ? 'officialTrends.start' : 'start')}
                <input key={queryingTrends ? 'start-month' : 'start-date'} type={queryingTrends ? 'month' : 'date'} required
                  min={queryingTrends ? '2000-01' : historical ? civilDates.first : '2000-01-01'}
                  max={queryingTrends ? previousMonth(1) : historical ? civilDates.last : undefined}
                  value={queryingTrends ? scope.start_date.slice(0, 7) : scope.start_date}
                  onChange={event => setScope({...scope, start_date: queryingTrends && event.target.value ? event.target.value + '-01' : event.target.value})} />
              </label>
              <label className={styles.field}>{t(queryingTrends ? 'officialTrends.end' : 'end')}
                <input key={queryingTrends ? 'end-month' : 'end-date'} type={queryingTrends ? 'month' : 'date'} required
                  min={queryingTrends ? scope.start_date.slice(0, 7) || '2000-01' : scope.start_date || (historical ? civilDates.first : '2000-01-01')}
                  max={queryingTrends ? previousMonth(1) : historical ? civilDates.last : undefined}
                  value={queryingTrends ? scope.end_date.slice(0, 7) : scope.end_date}
                  onChange={event => setScope({...scope, end_date: queryingTrends && event.target.value ? event.target.value + '-01' : event.target.value})} />
              </label>
            </div>
            <p className={styles.hint}>{t(queryingTrends ? 'officialTrends.dateHelp' : importingTrends ? 'importedTrends.dateHelp' :
              scope.source === 'wikimedia' ? 'wikiDates' : historical ? 'civilDates' : 'dateHelp')}</p>
            <div className={styles.pair}>
              <label className={styles.field}>{t('sourceLabel')}
                <select value={scope.source} onChange={event => chooseSource(event.target.value as ResearchSource)}>
                  {researchSources.map(source => <option key={source} value={source}>{t(source)}</option>)}
                </select>
              </label>
              {queryingTrends && <label className={styles.field}>{t('officialTrends.geography')}
                <select value={scope.geography ?? 'TR'} onChange={event => setScope({...scope, geography: event.target.value as TrendsCountry})}>
                  {trendsCountries.map(country => <option key={country} value={country}>
                    {new Intl.DisplayNames(locale, {type: 'region'}).of(country)}
                  </option>)}
                </select>
              </label>}
              {!isTrends && <label className={styles.field}>{t('language')}
                <select value={scope.language ?? ''} disabled={scope.source === 'lemmy' || scope.source === 'wikimedia' || historical}
                  onChange={event => setScope({...scope, language: (event.target.value || null) as ResearchScope['language']})}>
                  <option value="">{t('allLanguages')}</option>
                  <option value="en">{t('english')}</option>
                  <option value="tr">{t('turkish')}</option>
                </select>
              </label>}
            </div>
            {importingTrends && <>
              <label className={styles.field}>{t('importedTrends.link')}
                <input type="url" required value={exploreLink} maxLength={2048}
                  onChange={event => applyExploreLink(event.target.value)} />
              </label>
              <label className={styles.field}>{t('importedTrends.file')}
                <input type="file" accept=".csv,text/csv" required onChange={event => {
                  setTrendsFile(event.target.files?.[0] ?? null);
                  setSameChart(false);
                }} />
              </label>
              <p className={styles.hint}>{t('importedTrends.help')}</p>
              <label className={styles.analysisChoice}>
                <input type="checkbox" required checked={sameChart} onChange={event => setSameChart(event.target.checked)} />
                {' '}{t('importedTrends.sameChart')}
              </label>
            </>}
            {scope.source === 'lemmy' && <label className={styles.field}>{t('contentLabel')}
              <select value={scope.content ?? 'posts'} onChange={event => setScope({...scope,
                content: event.target.value === 'comments' ? 'comments' : undefined})}>
                <option value="posts">{t('posts')}</option>
                <option value="comments">{t('comments')}</option>
              </select>
            </label>}
            {scope.source === 'fictional' && <label className={styles.analysisChoice}>
              <input type="checkbox" checked={Boolean(scope.analyze_discussion)} onChange={event =>
                setScope({...scope, analyze_discussion: event.target.checked ? true : undefined})} /> {t('analyzeDiscussion')}
            </label>}
          </fieldset>
          <div className={styles.actions}>
            <button className={styles.submit} type="submit" disabled={!enabled || pending}>
              {t(importingTrends ? (pending ? 'importedTrends.reading' : 'importedTrends.submit') : pending ? 'searching' : 'submit')}
              {' '}<span aria-hidden="true">→</span>
            </button>
            {enabled && <div className={styles.examples}>
              <button type="button" disabled={pending} onClick={() => chooseExample('topic')}>{t('exampleTopic')}</button>
              <button type="button" disabled={pending} onClick={() => chooseExample('event')}>{t('exampleEvent')}</button>
              <button type="button" disabled={pending} onClick={chooseDiscussion}>{t('discussionExample')}</button>
              <button type="button" disabled={pending} onClick={chooseLongDiscussion}>{t('documentEvidence.example')}</button>
            </div>}
          </div>
          {!enabled && <p className={styles.hint}>{t('localOnly')}</p>}
        </form>
        <aside className={styles.panel} aria-labelledby="topic-source-heading">
          <h2 id="topic-source-heading">{t('sources')}</h2>
          <div className={styles.source}>
            <div><h3>{t('civil_comments')}</h3><span>{t('civilStatus')}</span></div>
            <p>{t('civilHelp')}</p>
          </div>
          <div className={styles.source}>
            <div><h3>{t('wikimedia')}</h3><span className={styles.live}>{t('wikiStatus')}</span></div>
            <p>{t('wikiHelp')}</p>
          </div>
          <div className={styles.source}>
            <div><h3>Lemmy.World</h3><span className={styles.live}>{t('liveStatus')}</span></div>
            <p>{t('lemmyHelp')}</p>
          </div>
          <div className={styles.source}>
            <div><h3>Bluesky</h3><span>{t('blueskyStatus')}</span></div>
            <p>{t('blueskyHelp')}</p>
          </div>
          <div className={styles.source}>
            <div><h3>Google Trends</h3><span>{t('importedTrends.localCsv')}</span></div>
            <p>{t('trendsHelp')}</p>
          </div>
          <div className={styles.source}>
            <div><h3>{t('fictional')}</h3><span>{t('fictionalStatus')}</span></div>
            <p>{t('fictionalHelp')}</p>
          </div>
          <p className={styles.geography}>{t('unsupportedGeography')}</p>
        </aside>
      </div>
      <div aria-live="polite" role="status">
        {pending && <p className={styles.feedback}>{t(importingTrends ? 'importedTrends.reading' : 'searching')}</p>}
        {error && <p className={styles.feedback}>{t(`errors.${error.code}`)} {error.upstream && t('upstreamStatus', {status: error.upstream})}</p>}
        {importingTrends && trendsError && <p className={styles.feedback}>{t(`importedTrends.errors.${trendsError}`)}</p>}
        {result && <p className={styles.visuallyHidden}>{t('resultAnnouncement', {count: result.records.length})}</p>}
      </div>
      {officialResult && <TrendsOfficialResult data={officialResult} />}
      {trendsResult && <TrendsCsvResults key={trendsResult.sha256} {...trendsResult} />}
      {result && <ResearchResults result={result} />}
      {enabled && <ResearchInterpretationAI key={`${locale}-${(isTrends ? officialResult : result)?.evidence_package?.package_id ?? 'empty'}`}
        evidence={importingTrends ? undefined : (queryingTrends ? officialResult : result)?.evidence_package} />}
      {enabled && <CivilComparison />}
    </section>
  );
}

function ResearchResults({result}: {result: ResearchResult}) {
  const t = useTranslations('TopicResearch');
  const locale = useLocale();
  const {scope, records, discussion_analysis: analysis, dataset_document: dataset} = result;
  const number = new Intl.NumberFormat(locale);
  const day = new Intl.DateTimeFormat(locale, {timeZone: 'UTC', dateStyle: 'medium'});
  const dateTime = new Intl.DateTimeFormat(locale, {timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short'});
  const month = new Intl.DateTimeFormat(locale, {timeZone: 'UTC', month: 'short', year: 'numeric'});
  const timeline = new Map<string, {post: number; comment: number}>();
  for (const record of records) {
    const key = record.published_at.slice(0, dataset ? 7 : 10);
    const counts = timeline.get(key) ?? {post: 0, comment: 0};
    counts[record.kind] += 1;
    timeline.set(key, counts);
  }
  const largestPeriod = Math.max(1, ...[...timeline.values()].map(count => count.post + count.comment));
  const commentCount = records.filter(record => record.kind === 'comment').length;
  const analysisComments = analysis?.evidence_rows.filter(index => records[index].kind === 'comment').length ?? 0;
  const signals = analysis?.expression_signals;
  const signalCounts = signals ? {...signals.emotions, ...signals.needs, ...signals.experiences} : null;
  const formatDay = (value: string) => day.format(new Date(value));
  const phrases = scope.query.split('|').map(part => part.trim());
  const archiveRecords = records.filter(record => record.source === 'civil_comments');
  const distinct = (field: 'article_id' | 'publication_id') =>
    new Set(archiveRecords.map(record => record[field]).filter(value => value !== null)).size;
  return (
    <section className={styles.results} aria-labelledby="topic-results-heading">
      <header className={styles.resultHeader}>
        <div>
          <p className={styles.eyebrow}>{t('overview')} · {t(scope.mode)}</p>
          <h2 id="topic-results-heading">{scope.query}</h2>
          <p>{t(scope.source)} · {formatDay(scope.start_date)} – {formatDay(scope.end_date)} UTC · {t(scope.language === 'en' ? 'english' : scope.language === 'tr' ? 'turkish' : 'allLanguages')}</p>
        </div>
        <span>{t(dataset ? 'civilSample' : scope.source === 'fictional' ? 'fictionalStatus' : 'publicSample')}</span>
      </header>
      <dl className={styles.metrics}>
        {dataset && <div><dt>{t('civilExamined')}</dt><dd>{number.format(dataset.examined)}</dd></div>}
        <div><dt>{t(dataset ? 'civilMatched' : scope.source === 'wikimedia' ? 'screened' : 'retrieved')}</dt><dd>{number.format(result.retrieved)}</dd></div>
        <div><dt>{t('accepted')}</dt><dd>{number.format(dataset?.eligible ?? records.length)}</dd></div>
        {dataset ? <div><dt>{t('civilSelected')}</dt><dd>{number.format(commentCount)}</dd></div> : <>
          <div><dt>{t('posts')}</dt><dd>{number.format(records.length - commentCount)}</dd></div>
          <div><dt>{t('comments')}</dt><dd>{number.format(commentCount)}</dd></div>
        </>}
        <div><dt>{t('unknownGeography')}</dt><dd>{number.format(records.length)}</dd></div>
      </dl>
      <div className={styles.coverage}>
        <h3>{t('coverage')}</h3>
        <p>{t(dataset ? 'civilCoverage' : scope.source === 'wikimedia' ? 'wikiCoverage' : scope.source === 'fictional' ? 'fictionalCoverage' : scope.source === 'lemmy'
          ? scope.content === 'comments' ? 'lemmyCommentsCoverage' : 'lemmyCoverage' : 'blueskyCoverage')}</p>
        {dataset && <>
          <p>{t(phrases.length === 1 ? 'civilLiteral' : 'civilAnyPhrase', {phrases: phrases.join(' · ')})}</p>
          <p>{t('civilDistinct', {articles: distinct('article_id'), publications: distinct('publication_id'), count: records.length})}</p>
        </>}
        {scope.source !== 'fictional' && <p>{t(dataset ? 'civilSafety' : scope.source === 'wikimedia' ? 'wikiSafety' : scope.source === 'lemmy' ? 'lemmySafety' : 'blueskySafety')}</p>}
        {result.retrieved !== (dataset?.eligible ?? records.length) && <p>{t(dataset ? 'civilExcluded' : 'excluded',
          {dates: result.outside_dates, invalid: result.invalid_records, duplicates: result.duplicates, restricted: result.excluded_records})}</p>}
        {dataset && result.excluded_records > 0 && <p>{t('civilScreening', Object.fromEntries(
          civilScreeningReasons.map(reason => [reason, number.format(dataset.screening[reason])])
        ))}</p>}
        {records.length > 0 && <p>{t('observedDates', {first: formatDay(records[0].published_at), last: formatDay(records[records.length - 1].published_at)})}</p>}
        <p>{t(dataset ? records.length === 0 ? 'civilEmpty' : 'civilLimitations' : records.length === 0 ? 'empty' : 'limitations')}</p>
      </div>
      <ResearchInterpretation result={result} />
      {analysis && <DiscussionEvidence analysis={analysis} />}
      <div className={styles.grid}>
        <section className={styles.panel} aria-labelledby="discussion-topics-heading">
          <h3 id="discussion-topics-heading">{t('topicExploration')}</h3>
          {!analysis ? <p className={styles.hint}>{t(scope.source === 'fictional' ? 'analysisOptional' : 'analysisWithheld')}</p> : <>
            <p className={styles.hint}>{t('analysisBasis', {total: analysis.evidence_rows.length,
              posts: analysis.evidence_rows.length - analysisComments, comments: analysisComments})}</p>
            <p className={styles.hint}>{t(`topicStatuses.${analysis.topics_status}`)}</p>
            {analysis.topics && <div className={styles.methodGroups}>
              {Object.entries(analysis.topics.methods).map(([method, grouping]) => <div key={method}>
                <h4>{methodTitle(method)}</h4>
                <ol>
                  {grouping.groups.map((group, index) => <li key={index}>
                    {t('topicGroupCount', {index: index + 1, count: group.size})}
                    {group.keywords.length > 0 && <p className={styles.hint}>{group.keywords.join(', ')}</p>}
                  </li>)}
                </ol>
                {grouping.unassigned > 0 && <p className={styles.hint}>{t('unassigned', {count: grouping.unassigned})}</p>}
                {grouping.iteration_limit && <p className={styles.hint}>{t('iterationLimit')}</p>}
              </div>)}
            </div>}
          </>}
        </section>
        <section className={styles.panel} aria-labelledby="discussion-signals-heading">
          <h3 id="discussion-signals-heading">{t('expressionHeading')}</h3>
          {!analysis ? <p className={styles.hint}>{t(scope.source === 'fictional' ? 'analysisOptional' : 'analysisWithheld')}</p> : <>
            <p className={styles.hint}>{t('expressionMethod')}</p>
            {analysis.evidence_rows.length > 0 && signalCounts ? <dl className={styles.signalCounts}>
              {Object.values(expressionCategories).flat().map(signal => <div key={signal}>
                  <dt>{t(`signals.${signal}`)}</dt><dd>{number.format(signalCounts[signal])}</dd>
                </div>)}
            </dl> : <p className={styles.hint}>{t('noAnalysisText')}</p>}
          </>}
        </section>
      </div>
      {records.length > 0 && <div className={styles.grid}>
        <section className={styles.panel} aria-labelledby="topic-timeline-heading">
          <h3 id="topic-timeline-heading">{t('timeline')}</h3>
          <p className={styles.hint}>{t(dataset ? 'civilTimeline' : 'timelineHelp')}</p>
          <ol className={styles.timeline}>
            {[...timeline].map(([date, count]) => <li key={date}>
              <time dateTime={date}>{dataset ? month.format(new Date(`${date}-01`)) : formatDay(date)}</time>
              <span className={styles.track} aria-hidden="true"><span style={{width: `${(count.post + count.comment) / largestPeriod * 100}%`}} /></span>
              <span aria-label={t('dayCounts', {posts: count.post, comments: count.comment})}>{number.format(count.post + count.comment)}</span>
            </li>)}
          </ol>
        </section>
        <section className={styles.panel} aria-labelledby="topic-explorer-heading">
          <h3 id="topic-explorer-heading">{t('explorer')}</h3>
          {scope.source !== 'fictional' && <p className={styles.hint}>{t(dataset ? 'civilContext' : 'linkOnly')}</p>}
          <ol className={styles.explorer}>
            {records.map((record, index) => <li id={`research-document-${index}`} key={`${record.reference ?? record.published_at}-${index}`}>
              <p><time dateTime={record.published_at}>{dateTime.format(new Date(record.published_at))} UTC</time>
                <span> · {t(record.kind === 'post' ? 'post' : 'comment')} · {record.source === 'lemmy' && record.source_language_id !== null
                  ? t('lemmyLanguageId', {id: record.source_language_id})
                  : record.languages.length ? record.languages.join(', ') : t('unknownLanguage')}</span></p>
              {record.source === 'civil_comments'
                ? <p>{t('civilIdentifiers', {article: record.article_id ?? t('unknownIdentifier'),
                  publication: record.publication_id ?? t('unknownIdentifier')})}</p>
                : record.source !== 'fictional'
                ? <div className={styles.recordLinks}>
                  <a href={record.reference} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{record.source === 'wikimedia' ? t('wikiSourcePage') : t('recordLink', {index: index + 1})} ↗</a>
                  {record.thread_reference && <a href={record.thread_reference} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{t('threadLink')} ↗</a>}
                </div>
                : <details><summary>{t('documentEvidence.document', {number: index + 1})}</summary>
                  <p className={styles.exampleText}>{record.text}</p></details>}
              {analysis?.evidence_rows.includes(index) && <span className={styles.hint}>{t('inAnalysis')}</span>}
            </li>)}
          </ol>
        </section>
      </div>}
      <section className={styles.future} aria-labelledby="topic-future-heading">
        <h3 id="topic-future-heading">{t('methodology')}</h3>
        <p>{t(dataset ? 'civilMethodology' : scope.source === 'wikimedia' ? 'wikiMethodology' : analysis ? 'methodologyFictional' : 'futureHelp')}</p>
      </section>
    </section>
  );
}

function ResearchInterpretation({result}: {result: ResearchResult}) {
  const t = useTranslations('TopicResearch');
  const locale = useLocale();
  const analysis = result.discussion_analysis;
  const doc = result.source_document;
  const dataset = result.dataset_document;
  const count = analysis?.evidence_rows.length ?? 0;
  const date = new Intl.DateTimeFormat(locale, {dateStyle: 'medium', timeZone: 'UTC'});
  const number = new Intl.NumberFormat(locale);
  const formatDay = (value: string) => date.format(new Date(value));
  const list = new Intl.ListFormat(locale, {style: 'long', type: 'conjunction'});
  const source = doc ? result.scope.query : t(result.scope.source);
  const signals = analysis?.expression_signals;
  const counts = signals ? {...signals.emotions, ...signals.needs, ...signals.experiences} : null;
  const found = counts ? Object.values(expressionCategories).flat().filter(name => counts[name] > 0)
    .map(name => t('claimSignal', {signal: t(`signals.${name}`), count: counts[name]})) : [];
  const topics = analysis?.topics;
  const diagnostics = topics ? topicEvidence(topics) : null;
  const agreement = topics?.agreement;
  return (
    <section className={`${styles.panel} ${styles.interpretation}`} aria-labelledby="interpretation-heading">
      <h3 id="interpretation-heading">{t('interpretation')}</h3>
      <p className={styles.hint}>{t('interpretationType')}</p>
      <h4>{t('observedEvidence')}</h4>
      <p>{dataset ? t('civilClaim', {matched: result.retrieved, examined: dataset.examined,
        eligible: dataset.eligible, selected: result.records.length}) :
        t('claimScope', {source, first: formatDay(result.scope.start_date), last: formatDay(result.scope.end_date),
          eligible: result.records.length, checked: result.retrieved})}</p>
      {analysis && <>
        <h4>{t('exploratoryEvidence')}</h4>
        <p>{t('claimDenominator', {count})}</p>
        {topics && diagnostics ? <>
          <p>{t('fixedTopics')}</p>
          {Object.entries(topics.methods).map(([method, value]) => (
            <p key={method}>{t('claimTopics', {method: methodTitle(method),
              sizes: list.format(value.groups.map(group => number.format(group.size))), unassigned: value.unassigned, count})}</p>
          ))}
          {diagnostics.uneven.length > 0 &&
            <p>{t('unevenTopics', {methods: list.format(diagnostics.uneven.map(methodTitle))})}</p>}
          {agreement?.ari != null
            ? <p>{t('agreementEvidence', {score: new Intl.NumberFormat(locale, {maximumFractionDigits: 4}).format(agreement.ari),
              count: agreement.common_assigned})} {diagnostics.weakAgreement && t('weakAgreementEvidence')}</p>
            : <p>{t('noAgreementEvidence')}</p>}
          {diagnostics.limitedTerms && <p>{t('limitedTopicTerms')}</p>}
          {topics.separation && Object.entries(topics.separation).map(([method, score]) =>
            <p key={method}>{score === null ? t('documentEvidence.separationUnavailable', {method: methodTitle(method)}) :
              t('documentEvidence.separation', {method: methodTitle(method), score: number.format(score),
                count: topics.methods[method as 'nmf' | 'minilm']!.groups.reduce((sum, group) => sum + group.size, 0)})}</p>)}
          {diagnostics.weakSeparation.length > 0 && <p>{t('documentEvidence.weakSeparation',
            {methods: list.format(diagnostics.weakSeparation.map(methodTitle))})}</p>}
          {diagnostics.iterationLimit && <p>{t('iterationLimit')}</p>}
        </> : <p>{t(`topicStatuses.${analysis.topics_status}`)}</p>}
        <h4>{t('expressionEvidence')}</h4>
        <p>{count > 0 ? found.length ? t('claimSignals', {summary: list.format(found), count}) : t('claimNoSignals', {count})
          : t('noAnalysisText')}</p>
        <p>{t('expressionBoundary')}</p>
      </>}
      {dataset && <>
        <h4>{t('evidenceLimits')}</h4>
        <p>{t('civilContextLimit')}</p>
      </>}
      {!dataset && <p>{t('claimTime')}</p>}
      {dataset && <p className={styles.recordLinks}>
        <a href={dataset.source} target="_blank" rel="noopener noreferrer">{t('civil_comments')}</a>
        <a href={civilDistribution} target="_blank" rel="noopener noreferrer">{dataset.artifact}</a>
        <a href={dataset.license_url} target="_blank" rel="noopener noreferrer">{dataset.license}</a>
      </p>}
      {doc && <p className={styles.recordLinks}>
        <a href={doc.page} target="_blank" rel="noopener noreferrer">{t('wikiSourcePage')}</a>
        <a href={doc.history} target="_blank" rel="noopener noreferrer">{t('wikiHistory')}</a>
        <a href={doc.license_url} target="_blank" rel="noopener noreferrer">{doc.license}</a>
      </p>}
      {result.records.length > 0 && <p><a href="#topic-explorer-heading">{t('interpretationEvidence')}</a></p>}
    </section>
  );
}
