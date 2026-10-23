import {hasLocale} from 'next-intl';
import {getTranslations, setRequestLocale} from 'next-intl/server';
import {notFound} from 'next/navigation';
import {routing} from '@/i18n/routing';

export default async function HomePage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations('Home');

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-5xl px-6 pt-12 pb-16 sm:px-10 sm:pt-24">
      <p className="text-sm font-semibold tracking-wide text-teal-800">{t('eyebrow')}</p>
      <h1 className="mt-5 text-5xl font-semibold tracking-tight text-teal-950 sm:text-7xl">{t('title')}</h1>
      <p className="mt-7 max-w-3xl text-lg leading-8 text-stone-700 sm:text-xl sm:leading-9">{t('description')}</p>

      <section aria-labelledby="development-status" className="mt-12 rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
        <h2 id="development-status" className="flex items-center gap-3 text-base font-semibold text-stone-900">
          <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full bg-amber-600" />
          {t('status')}
        </h2>
        <p className="mt-3 max-w-2xl leading-7 text-stone-600">{t('statusDescription')}</p>
      </section>

      <section aria-labelledby="research-approach" className="mt-10 max-w-3xl">
        <h2 id="research-approach" className="text-sm font-semibold text-teal-900">{t('principle')}</h2>
        <p className="mt-3 text-sm leading-7 text-stone-600">{t('principleDescription')}</p>
      </section>
    </main>
  );
}
