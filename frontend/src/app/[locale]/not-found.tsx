import {getTranslations} from 'next-intl/server';
import {Link} from '@/i18n/navigation';

export default async function NotFoundPage() {
  const t = await getTranslations('NotFound');
  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-5xl px-6 py-16 sm:px-10">
      <h1 className="text-3xl font-semibold text-teal-950">{t('title')}</h1>
      <p className="mt-4 text-stone-700">{t('description')}</p>
      <Link href="/" className="mt-8 inline-block rounded-lg bg-teal-900 px-5 py-3 text-white">{t('home')}</Link>
    </main>
  );
}
