import type { Locale } from '@/store/settingsStore';
import zh from '../../messages/zh.json';
import zhHant from '../../messages/zh-Hant.json';
import en from '../../messages/en.json';

export const SUPPORTED_LOCALES: Locale[] = ['zh', 'zh-Hant', 'en'];

const messages: Record<Locale, typeof zh> = { zh, 'zh-Hant': zhHant, en };

export function getMessages(locale: Locale) {
    return messages[locale] ?? messages['zh-Hant'];
}
