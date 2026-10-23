import type {Metadata} from 'next';
import {hasLocale, NextIntlClientProvider} from 'next-intl';
import {getTranslations, setRequestLocale} from 'next-intl/server';
import {notFound} from 'next/navigation';
import {LanguageSwitcher} from '@/components/language-switcher';
import {Link} from '@/i18n/navigation';
import {routing} from '@/i18n/routing';
import '../globals.css';

type Props = {
  children: React.ReactNode;
  params: Promise<{locale: string}>;
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({locale}));
}

export async function generateMetadata({params}: Omit<Props, 'children'>): Promise<Metadata> {
  const {locale} = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  const t = await getTranslations({locale, namespace: 'Metadata'});
  return {title: t('title'), description: t('description')};
}

export default async function LocaleLayout({children, params}: Props) {
  const {locale} = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations('Navigation');

  return (
    <html lang={locale}>
      <body className="min-h-screen antialiased">
        <NextIntlClientProvider>
          <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-10 focus:rounded-lg focus:bg-white focus:p-4">
            {t('skipToContent')}
          </a>
          <header className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-6 py-6 sm:px-10">
            <Link href="/" aria-label={t('home')} className="text-xl font-semibold tracking-tight text-teal-950">
              {t('projectName')}
            </Link>
            <LanguageSwitcher />
          </header>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
