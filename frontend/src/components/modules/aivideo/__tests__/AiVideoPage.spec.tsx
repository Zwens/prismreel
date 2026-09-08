import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * The standalone AI-video page.
 *
 * Two things matter here and nothing else does. First, it must run on its own
 * store: it is the reason the playground store became a factory, and if it ever
 * shares state with the创作台 the two pages will overwrite each other's mode,
 * prompt and input media. Second, it must not repeat the empty-mode hole the
 * playground has — when a mode offers no model, ModelSelector's auto-adopt
 * effect is skipped and the stale model id from the previous mode is what gets
 * submitted.
 *
 * The catalog is stubbed rather than read for real: the DashScope removal is
 * actively rewriting it, and a page spec that breaks because a family was
 * retired is a spec that will be deleted rather than fixed. The stub also lets
 * v2v be genuinely empty, which is the only way to exercise the empty state.
 */

// vi.hoisted: vi.mock is lifted above plain consts, so the stub has to be too.
const catalogStub = vi.hoisted(() => ({
    models: {
        'stub-t2v': {
            id: 'stub-t2v',
            display_name: 'Stub T2V',
            family: 'seedance',
            description: 'text to video',
            capabilities: ['t2v'],
            status: 'available',
            ui: { recommended: true, order: 10, badges: [] },
            duration: { type: 'slider', min: 4, max: 12, step: 1, default: 5 },
            params: { resolution: { options: ['720p'], default: '720p' }, seed: true },
            inputs: {},
        },
        'stub-i2v': {
            id: 'stub-i2v',
            display_name: 'Stub I2V',
            family: 'seedance',
            description: 'image to video',
            capabilities: ['i2v'],
            status: 'available',
            ui: { recommended: true, order: 10, badges: [] },
            duration: { type: 'slider', min: 4, max: 12, step: 1, default: 5 },
            params: { resolution: { options: ['720p'], default: '720p' }, seed: true },
            inputs: {},
        },
        // Deliberately no v2v model — that mode is the empty-state fixture.
    },
}));

vi.mock('@/generated/modelCatalog.json', () => ({ default: catalogStub }));

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => {
            const { initial, animate, exit, variants, transition, whileHover, ...rest } = props;
            return <div {...rest}>{children}</div>;
        },
    },
    AnimatePresence: ({ children }: any) => <>{children}</>,
}));

vi.mock('lucide-react', () => {
    const cache = new Map<string, any>();
    return new Proxy({} as Record<string, any>, {
        get: (_target, prop) => {
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

const mockGenerate = vi.fn().mockResolvedValue({
    id: 'gen-1',
    mode: 't2v',
    model_id: 'stub-t2v',
    prompt: '',
    status: 'completed',
    input_media: [],
    parameters: {},
    batch_size: 1,
    outputs: [],
    created_at: new Date().toISOString(),
});

vi.mock('@/lib/api', () => ({
    API_URL: 'http://localhost:17177',
    api: {
        listLibraryAssets: vi.fn().mockResolvedValue({ characters: [], scenes: [], props: [] }),
        listSeries: vi.fn().mockResolvedValue([]),
        getProjects: vi.fn().mockResolvedValue([]),
        getProject: vi.fn().mockResolvedValue({ frames: [] }),
    },
    playgroundApi: {
        generate: (...a: any[]) => mockGenerate(...a),
        getHistory: vi.fn().mockResolvedValue([]),
        getTemplates: vi.fn().mockResolvedValue([]),
        getGeneration: vi.fn().mockResolvedValue(null),
        getGenerationStatus: vi.fn().mockResolvedValue({ status: 'pending' }),
        deleteGeneration: vi.fn(),
        createTemplate: vi.fn(),
        deleteTemplate: vi.fn(),
        saveOutputToLibrary: vi.fn(),
    },
}));

import AiVideoPage from '../AiVideoPage';
import { playgroundStore } from '@/components/modules/playground/usePlaygroundStore';

beforeEach(() => {
    vi.clearAllMocks();
    playgroundStore.setState({ mode: 't2i', prompt: '', inputMedia: [], queue: [] });
});

describe('AiVideoPage — its own store', () => {
    it('opens on a video mode instead of the shared default t2i', async () => {
        renderWithIntl(<AiVideoPage />);

        expect(await screen.findByRole('button', { name: '文生视频' })).toHaveAttribute(
            'aria-pressed',
            'true',
        );
    });

    it('keeps its prompt out of the playground store', () => {
        renderWithIntl(<AiVideoPage />);

        fireEvent.change(screen.getByPlaceholderText('描述你想生成的内容...'), {
            target: { value: '海面上的暴风雨' },
        });

        expect(playgroundStore.getState().prompt).toBe('');
    });

    it('keeps its mode out of the playground store', () => {
        renderWithIntl(<AiVideoPage />);

        fireEvent.click(screen.getByRole('button', { name: '图生视频' }));

        expect(playgroundStore.getState().mode).toBe('t2i');
    });

    it('enqueues into its own store, leaving the playground queue empty', async () => {
        renderWithIntl(<AiVideoPage />);

        fireEvent.change(screen.getByPlaceholderText('描述你想生成的内容...'), {
            target: { value: '海面上的暴风雨' },
        });
        fireEvent.click(screen.getByRole('button', { name: /^生成/ }));

        await waitFor(() => expect(mockGenerate).toHaveBeenCalled());
        expect(mockGenerate).toHaveBeenCalledWith(
            expect.objectContaining({ mode: 't2v', prompt: '海面上的暴风雨' }),
        );
        expect(playgroundStore.getState().queue).toHaveLength(0);
    });
});

describe('AiVideoPage — video only', () => {
    it('offers the three video modes', async () => {
        renderWithIntl(<AiVideoPage />);

        expect(await screen.findByRole('button', { name: '文生视频' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '图生视频' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '视频编辑' })).toBeInTheDocument();
    });

    it('offers no image modes', () => {
        renderWithIntl(<AiVideoPage />);

        expect(screen.queryByRole('button', { name: '文生图' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: '图生图' })).not.toBeInTheDocument();
    });

    it('picks a model that can actually do the selected mode', async () => {
        renderWithIntl(<AiVideoPage />);

        fireEvent.click(screen.getByRole('button', { name: '图生视频' }));

        expect(await screen.findByText('Stub I2V')).toBeInTheDocument();
    });
});

describe('AiVideoPage — a mode with no model', () => {
    // The playground silently keeps the previous mode's model id here and lets
    // the user submit it. This page refuses instead.
    it('says so rather than showing a stale model', () => {
        renderWithIntl(<AiVideoPage />);

        fireEvent.click(screen.getByRole('button', { name: '视频编辑' }));

        expect(screen.getByText('该模式暂无可用模型')).toBeInTheDocument();
        expect(screen.queryByText('Stub T2V')).not.toBeInTheDocument();
    });

    it('refuses to generate', () => {
        renderWithIntl(<AiVideoPage />);

        fireEvent.change(screen.getByPlaceholderText('描述你想生成的内容...'), {
            target: { value: '海面上的暴风雨' },
        });
        fireEvent.click(screen.getByRole('button', { name: '视频编辑' }));

        expect(screen.getByRole('button', { name: /^生成/ })).toBeDisabled();
    });
});
