import {hasLocale} from 'next-intl';
import {getTranslations, setRequestLocale} from 'next-intl/server';
import {notFound} from 'next/navigation';
import {AnalysisDashboard} from '@/components/analysis-dashboard';
import {routing} from '@/i18n/routing';

export default async function HomePage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations('Dashboard');

  return (
    <main id="main-content" tabIndex={-1} className="dashboard-shell">
      <div className="dashboard-hero">
        <h1>{t('title')}</h1>
        <p>{t('intro')}</p>
      </div>
      <aside className="demo-notice" aria-label={t('noticeTitle')}>
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="9" /><path d="M12 11v5m0-8v.01" strokeLinecap="round" />
        </svg>
        <p><strong>{t('noticeTitle')}</strong> {t('notice')}</p>
      </aside>
      <AnalysisDashboard />
    </main>
  );
}
