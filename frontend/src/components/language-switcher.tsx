'use client';

import {useLocale, useTranslations} from 'next-intl';
import {Link, usePathname} from '@/i18n/navigation';
import {routing} from '@/i18n/routing';

export function LanguageSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const t = useTranslations('Navigation');

  return (
    <nav aria-label={t('languageLabel')} className="flex gap-1 rounded-full border border-stone-300 bg-white p-1">
      {routing.locales.map((targetLocale) => (
        <Link
          key={targetLocale}
          href={pathname}
          locale={targetLocale}
          lang={targetLocale}
          aria-current={locale === targetLocale ? 'page' : undefined}
          className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
            locale === targetLocale
              ? 'bg-teal-900 text-white'
              : 'text-stone-700 hover:bg-stone-100'
          }`}
        >
          {t(targetLocale === 'tr' ? 'turkish' : 'english')}
        </Link>
      ))}
    </nav>
  );
}
