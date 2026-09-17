import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Locale = 'zh' | 'zh-Hant' | 'en';

/**
 * 5 預設主題（Tasty Sam 主題系統）。
 * 3 暗（atelier-dark 默認 / bridge-dark / brand-dark）+ 2 亮（atelier-light / brand-light）。
 * 與 globals.css 的 html.<id> block、Providers/layout 切換邏輯一一對應。
 */
export type ThemePreset =
    | 'atelier-dark'
    | 'bridge-dark'
    | 'brand-dark'
    | 'atelier-light'
    | 'brand-light';

export const THEME_PRESETS: ThemePreset[] = [
    'atelier-dark',
    'bridge-dark',
    'brand-dark',
    'atelier-light',
    'brand-light',
];

export const DEFAULT_THEME: ThemePreset = 'atelier-dark';

interface SettingsStore {
    locale: Locale;
    theme: ThemePreset;
    // 全局動效開關。true = 啓用 motion（默認）；false = 降低動效，
    // 由 Providers 掛載 html.no-motion 類來落地（無障礙/性能偏好）。
    animations: boolean;
    setLocale: (locale: Locale) => void;
    setTheme: (theme: ThemePreset) => void;
    setAnimations: (animations: boolean) => void;
}

export const useSettingsStore = create<SettingsStore>()(
    persist(
        (set) => ({
            locale: 'zh-Hant',
            theme: DEFAULT_THEME,
            animations: true,
            setLocale: (locale: Locale) => set({ locale }),
            setTheme: (theme: ThemePreset) => set({ theme }),
            setAnimations: (animations: boolean) => set({ animations }),
        }),
        {
            name: 'prismreel-settings',
            version: 1,
            // v0→v1：舊版只有 'dark' | 'light'。按產品決策，統一升級到新默認
            // atelier-dark（不保留舊觀感）。非法/缺失值同樣回落默認。
            migrate: (persisted: unknown, version: number) => {
                const state = (persisted ?? {}) as Partial<SettingsStore>;
                const animations = typeof state.animations === 'boolean' ? state.animations : true;
                if (version < 1 || !THEME_PRESETS.includes(state.theme as ThemePreset)) {
                    return { ...state, theme: DEFAULT_THEME, animations } as SettingsStore;
                }
                return { ...state, animations } as SettingsStore;
            },
        }
    )
);
