import { screen, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * 音色选择器在 DashScope 下线后的形态。
 *
 * 音色克隆与音色设计随 CosyVoice 一起消失：Gemini 只有 30 个固定预置音色，
 * BytePlus Ark 平台没有任何 TTS 模型（2026-09-08 实测 43 个在售模型无一个
 * 语音输出），两个可用平台都不提供复刻能力，没有替代方案。
 *
 * 所以「我的复刻」「我的设计」两个 tab 必须整个消失，而不是留着点进去报错
 * 或显示空列表 —— 留一个永远无法完成的入口比没有入口更糟。
 */

vi.mock('lucide-react', () => {
    const cache = new Map<string, any>();
    return new Proxy({} as Record<string, any>, {
        get: (_target, prop) => {
            // `then` 必须返回 undefined，否则 vi.mock 的模块 promise 会被误当
            // thenable 递归解析；`has` 必须为 true，否则命名导出检查会报
            // No "X" export。两者缺一都会让整个 run 挂掉（同事踩过）。
            if (typeof prop !== 'string' || prop === 'then') return undefined;
            if (prop === '__esModule') return true;
            if (!cache.has(prop)) {
                const Icon = (props: any) => <span data-testid={`icon-${prop}`} {...props} />;
                Icon.displayName = prop;
                cache.set(prop, Icon);
            }
            return cache.get(prop);
        },
        has: () => true,
    });
});

const getVoices = vi.fn();

vi.mock('@/lib/api', () => ({
    API_URL: 'http://localhost:17177',
    api: {
        get getVoices() { return getVoices; },
    },
}));

const GEMINI_VOICES = [
    { model_id: 'Kore', name: 'Kore · 科瑞 (知性女)', gender: 'Female', model: 'gemini-3.1-flash-tts-preview' },
    { model_id: 'Achird', name: 'Achird · 王良三 (暖心男)', gender: 'Male', model: 'gemini-3.1-flash-tts-preview' },
    { model_id: 'Algenib', name: 'Algenib · 壁宿一 (低音男)', gender: 'Male', model: 'gemini-3.1-flash-tts-preview' },
];

beforeEach(() => {
    vi.clearAllMocks();
    getVoices.mockResolvedValue(GEMINI_VOICES);
});

async function renderPicker(props: Record<string, unknown> = {}) {
    const { default: VoicePickerModal } = await import('../VoicePickerModal');
    return renderWithIntl(
        <VoicePickerModal
            isOpen
            onClose={() => {}}
            onApply={() => {}}
            characterName="林晚"
            seriesId="series-1"
            {...props}
        />,
    );
}

describe('VoicePickerModal 在 Gemini 迁移后', () => {
    it('渲染后端返回的 Gemini 音色', async () => {
        await renderPicker();
        await waitFor(() => {
            expect(screen.getByText(/科瑞/)).toBeTruthy();
        });
        expect(screen.getByText(/王良三/)).toBeTruthy();
    });

    it('不再出现「我的复刻」入口', async () => {
        await renderPicker();
        await waitFor(() => expect(getVoices).toHaveBeenCalled());
        expect(screen.queryByText(/复刻/)).toBeNull();
    });

    it('不再出现「我的设计」入口', async () => {
        await renderPicker();
        await waitFor(() => expect(getVoices).toHaveBeenCalled());
        expect(screen.queryByText(/我的设计/)).toBeNull();
    });

    it('不再调用任何自定义音色接口', async () => {
        // 克隆端点已从后端删除；还在调用只会拿到 404，并在控制台刷错误。
        const api = (await import('@/lib/api')).api as Record<string, unknown>;
        for (const dead of ['cloneVoice', 'listCustomVoices', 'deleteCustomVoice',
                            'previewDesignVoice', 'acceptDesignVoice', 'designVoicePreview']) {
            expect(api[dead]).toBeUndefined();
        }
    });

    it('没有系列 id 时依然可用', async () => {
        // 「请先关联到系列」的提示只为克隆 tab 存在；系统音色与系列无关，
        // 孤立项目不该因此选不了音色。
        await renderPicker({ seriesId: null });
        await waitFor(() => {
            expect(screen.getByText(/科瑞/)).toBeTruthy();
        });
    });
});
