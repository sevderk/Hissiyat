import {hasLocale, NextIntlClientProvider} from 'next-intl';
import {getMessages, getTranslations, setRequestLocale} from 'next-intl/server';
import {notFound} from 'next/navigation';
import {AnalysisDashboard} from '@/components/analysis-dashboard';
import {LocalAnalysis} from '@/components/local-analysis';
import {ResearchFindings} from '@/components/research-findings';
import {routing} from '@/i18n/routing';
import {isLocalAnalysisEnabled} from '@/lib/local-analysis-contract';
import {isResearchPreviewEnabled} from '@/lib/research-preview';

export default async function HomePage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations('Dashboard');
  const showResearch = isResearchPreviewEnabled(process.env.NODE_ENV, process.env.HISSIYAT_RESEARCH_PREVIEW);
  const researchTitle = showResearch ? (await getTranslations('Research'))('title') : null;
  const showLocalAnalysis = isLocalAnalysisEnabled(process.env.NODE_ENV, process.env.HISSIYAT_LOCAL_TEXT_ANALYSIS);
  const analysisMessages = showLocalAnalysis ? (await getMessages()).LocalAnalysis : null;

  return (
    <main id="main-content" tabIndex={-1} className="dashboard-shell">
      <div className="dashboard-hero">
        <h1>{t('title')}</h1>
        <p>{t('intro')}</p>
      </div>
      {(showResearch || analysisMessages) && (
        <nav className="dashboard-section-nav" aria-label={t('sectionNavigation')}>
          {analysisMessages && <a href="#local-text-analysis">{analysisMessages.title}</a>}
          {showResearch && <a href="#research-findings">{researchTitle}</a>}
          <a href="#synthetic-demo">{t('noticeTitle')}</a>
        </nav>
      )}
      {analysisMessages && (
        <NextIntlClientProvider messages={{LocalAnalysis: analysisMessages}}>
          <LocalAnalysis />
        </NextIntlClientProvider>
      )}
      {showResearch && <ResearchFindings />}
      <section id="synthetic-demo" className="analysis-section synthetic-section" aria-labelledby="synthetic-heading">
        <div className="analysis-heading">
          <h2 id="synthetic-heading">{t('noticeTitle')}</h2>
        </div>
        <p className="demo-notice">{t('notice')}</p>
        <AnalysisDashboard />
      </section>
    </main>
  );
}
