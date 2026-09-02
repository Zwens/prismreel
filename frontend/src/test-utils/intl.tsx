import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import type { Locale } from '@/store/settingsStore';
import { getMessages } from '@/lib/i18n';

/**
 * render() for components that call useTranslations.
 *
 * Without a NextIntlClientProvider in the tree next-intl throws
 * "Failed to call `useTranslations` because the context from
 * `NextIntlClientProvider` was not found" and the whole spec file dies.
 *
 * Mirrors the wiring in src/components/Providers.tsx and feeds it the real
 * messages/zh.json rather than a stub, so specs keep asserting on the copy
 * the app actually ships -- a renamed or deleted message key then shows up
 * as a failing assertion instead of silently passing against a fake.
 */
export function renderWithIntl(ui: ReactElement, locale: Locale = 'zh') {
    return render(
        <NextIntlClientProvider
            locale={locale}
            messages={getMessages(locale)}
            timeZone="Asia/Shanghai"
        >
            {ui}
        </NextIntlClientProvider>
    );
}
