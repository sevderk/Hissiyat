import {getFormatter, getTranslations} from 'next-intl/server';
import {researchPreview} from '@/lib/research-preview';

const measures = ['betweenMethods', 'nmfStability', 'miniLmStability'] as const;

export async function ResearchFindings() {
  const [t, format] = await Promise.all([getTranslations('Research'), getFormatter()]);
  const decimal = (value: number) => format.number(value, {minimumFractionDigits: 4, maximumFractionDigits: 4});

  return (
    <section id="research-findings" className="analysis-section research-section" aria-labelledby="research-heading">
      <div className="analysis-heading">
        <div>
          <p className="source-label">{t('preview')}</p>
          <h2 id="research-heading">{t('title')}</h2>
          <p className="section-description">{t('sample', {questions: researchPreview.reviewedQuestions})}</p>
        </div>
      </div>
      <div className="dashboard-card research-comparison">
        <table>
          <caption>{t('comparison')}</caption>
          <thead>
            <tr>
              <th scope="col">{t('measure')}</th>
              {researchPreview.comparisons.map(({k}) => (
                <th key={k} scope="col">{t('clusterCount', {k})}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {measures.map((measure) => (
              <tr key={measure}>
                <th scope="row">{t(measure)}</th>
                {researchPreview.comparisons.map((comparison) => (
                  <td key={comparison.k}>
                    <span className="research-value">{decimal(comparison[measure])}</span>
                    <div className="bar-track" aria-hidden="true">
                      <div className={'bar-fill ' + measure} style={{width: comparison[measure] * 100 + '%'}} />
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="research-scale">{t('scale')}</p>
      </div>
      <div className="research-notes">
        <div>
          <h3>{t('readingTitle')}</h3>
          <p>{t('ari')}</p>
          <p>{t('stability', {
            repetitions: researchPreview.stabilityRepetitions,
            share: format.number(researchPreview.stabilitySampleShare, {style: 'percent'})
          })}</p>
          <p>{t('observed')}</p>
        </div>
        <div>
          <h3>{t('reviewTitle')}</h3>
          <p>{t('review', {questions: researchPreview.overlapQuestions})}</p>
          <p>{t('limits')}</p>
        </div>
      </div>
      <footer className="research-source">
        <p>{t.rich('source', {
          release: (chunks) => <a href={researchPreview.source.release}>{chunks}</a>,
          license: (chunks) => <a href={researchPreview.source.license}>{chunks}</a>
        })}</p>
        <p>{t('attribution')}</p>
      </footer>
    </section>
  );
}
