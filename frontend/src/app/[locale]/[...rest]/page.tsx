import {hasLocale} from 'next-intl';
import {setRequestLocale} from 'next-intl/server';
import {notFound} from 'next/navigation';
import {routing} from '@/i18n/routing';

export default async function MissingPage({params}: {params: Promise<{locale: string}>}) {
  const {locale} = await params;
  if (hasLocale(routing.locales, locale)) setRequestLocale(locale);
  notFound();
}
