import { describe, it, expect } from 'vitest';
import { getMessages, SUPPORTED_LOCALES } from '@/lib/i18n';

const getKeys = (obj: Record<string, unknown>, prefix = ''): string[] => {
    return Object.entries(obj).flatMap(([key, value]) => {
        const path = prefix ? `${prefix}.${key}` : key;
        if (typeof value === 'object' && value !== null) {
            return getKeys(value as Record<string, unknown>, path);
        }
        return [path];
    });
};

describe('i18n configuration', () => {
    it('SUPPORTED_LOCALES contains zh, zh-Hant and en', () => {
        expect(SUPPORTED_LOCALES).toContain('zh');
        expect(SUPPORTED_LOCALES).toContain('zh-Hant');
        expect(SUPPORTED_LOCALES).toContain('en');
        expect(SUPPORTED_LOCALES).toHaveLength(3);
    });

    it('getMessages returns messages for zh', () => {
        const messages = getMessages('zh');
        expect(messages).toBeDefined();
        expect(messages.common.save).toBe('保存');
        expect(messages.nav.workspace).toBe("漫画生成");
        expect(messages.settings.title).toBe('设置');
    });

    it('getMessages returns messages for zh-Hant', () => {
        const messages = getMessages('zh-Hant');
        expect(messages).toBeDefined();
        expect(messages.common.save).toBe('儲存');
        expect(messages.nav.workspace).toBe("漫畫生成");
        expect(messages.settings.title).toBe('設定');
    });

    it('getMessages returns messages for en', () => {
        const messages = getMessages('en');
        expect(messages).toBeDefined();
        expect(messages.common.save).toBe('Save');
        expect(messages.nav.workspace).toBe("Comic Generator");
        expect(messages.settings.title).toBe('Settings');
    });

    it('zh, zh-Hant and en have identical key structure', () => {
        const zh = getMessages('zh');
        const zhHant = getMessages('zh-Hant');
        const en = getMessages('en');

        const zhKeys = getKeys(zh).sort();
        const zhHantKeys = getKeys(zhHant).sort();
        const enKeys = getKeys(en).sort();
        expect(zhHantKeys).toEqual(zhKeys);
        expect(zhKeys).toEqual(enKeys);
    });

    it('getMessages falls back to zh-Hant for unknown locale', () => {
        // @ts-expect-error testing invalid input
        const messages = getMessages('fr');
        expect(messages.common.save).toBe('儲存');
    });
});
