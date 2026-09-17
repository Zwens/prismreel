"use client";

import { useEffect } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import { useSettingsStore, THEME_PRESETS } from '@/store/settingsStore';
import { getMessages } from '@/lib/i18n';
import { LightboxProvider } from '@/components/shared/preview/LightboxProvider';
import ToastContainer from '@/components/shared/ToastContainer';
import { MotionConfig } from 'framer-motion';
import { installAuthInterceptor } from '@/lib/authInterceptor';

export function Providers({ children }: { children: React.ReactNode }) {
    const locale = useSettingsStore((s) => s.locale);
    const theme = useSettingsStore((s) => s.theme);
    const animations = useSettingsStore((s) => s.animations);
    const messages = getMessages(locale);

    useEffect(() => {
        installAuthInterceptor();
    }, []);

    useEffect(() => {
        const html = document.documentElement;
        // 移除全部 5 個預設 class + 舊版遺留的 dark/light，再加當前主題
        html.classList.remove(...THEME_PRESETS, 'dark', 'light');
        html.classList.add(theme);
    }, [theme]);

    useEffect(() => {
        // animations=false → 掛 html.no-motion，CSS 據此降低/禁用過渡動畫
        document.documentElement.classList.toggle('no-motion', !animations);
    }, [animations]);

    useEffect(() => {
        document.documentElement.lang = locale;
    }, [locale]);

    return (
        <NextIntlClientProvider locale={locale} messages={messages} timeZone="Asia/Shanghai">
            {/* MotionConfig: respect OS prefers-reduced-motion ("user"); when the
             *  in-app 動效 toggle is off, force-reduce Framer animations ("always"). */}
            <MotionConfig reducedMotion={animations ? "user" : "always"}>
                {/* LightboxProvider must wrap any subtree that uses PreviewImage /
                 *  PreviewVideo. Singleton portal — see Issue 14 design notes in
                 *  LightboxProvider.tsx. */}
                <LightboxProvider>
                    {children}
                    <ToastContainer />
                </LightboxProvider>
            </MotionConfig>
        </NextIntlClientProvider>
    );
}
