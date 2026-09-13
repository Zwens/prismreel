import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * Store-wiring regression suite — gallery, detail, templates and the page shell.
 *
 * Completes the coverage the other three storeWiring specs started (see the
 * compose spec header for why this suite exists at all).
 *
 * The awkward one here is ResultGallery: it reaches the store three different
 * ways — a whole-store destructure, actions closed over in callbacks, and one
 * bare `playgroundStore.getState()` at module scope inside the delete
 * handler. That last call sits outside the React tree, so a context provider
 * cannot reach it; whoever does D5 has to rewrite it by hand. The delete test
 * below is what will catch them if they don't.
 */

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

const mockDeleteGeneration = vi.fn().mockResolvedValue({});
const mockGenerate = vi.fn().mockResolvedValue({
    id: 'new-gen',
    mode: 't2i',
    model_id: 'gemini-3.1-flash-image',
    prompt: '雨夜的天台',
    status: 'completed',
    input_media: [],
    parameters: {},
    batch_size: 1,
    outputs: [],
    created_at: new Date().toISOString(),
});
const mockCreateTemplate = vi.fn();

vi.mock('@/lib/api', () => ({
    API_URL: 'http://localhost:17177',
    api: {
        listLibraryAssets: vi.fn().mockResolvedValue({ characters: [], scenes: [], props: [] }),
        listSeries: vi.fn().mockResolvedValue([]),
        getProjects: vi.fn().mockResolvedValue([]),
        getProject: vi.fn().mockResolvedValue({ frames: [] }),
    },
    playgroundApi: {
        deleteGeneration: (...a: any[]) => mockDeleteGeneration(...a),
        generate: (...a: any[]) => mockGenerate(...a),
        getGeneration: vi.fn().mockResolvedValue(null),
        getGenerationStatus: vi.fn().mockResolvedValue({ status: 'pending' }),
        getHistory: vi.fn().mockResolvedValue([]),
        getTemplates: vi.fn().mockResolvedValue([]),
        createTemplate: (...a: any[]) => mockCreateTemplate(...a),
        deleteTemplate: vi.fn(),
        saveOutputToLibrary: vi.fn(),
    },
}));

import ResultGallery from '../ResultGallery';
import DetailPanel from '../DetailPanel';
import PromptTemplateModal from '../PromptTemplateModal';
import PlaygroundPage from '../PlaygroundPage';
import { playgroundStore, type PlaygroundGeneration } from '../usePlaygroundStore';

const store = () => playgroundStore.getState();

function generation(overrides: Partial<PlaygroundGeneration> = {}): PlaygroundGeneration {
    return {
        id: 'g1',
        mode: 't2i',
        model_id: 'gemini-3.1-flash-image',
        prompt: '雨夜的天台',
        status: 'completed',
        input_media: [],
        parameters: {},
        batch_size: 1,
        created_at: new Date().toISOString(),
        outputs: [
            {
                id: 'o1',
                media_path: 'output/playground/a.png',
                media_type: 'image',
                saved_to_library: false,
            },
        ],
        ...overrides,
    } as PlaygroundGeneration;
}

beforeEach(() => {
    vi.clearAllMocks();
    playgroundStore.setState({
        // 三段式 UI 默认停在 select；这些用例测的是 compose 的提交行为
        playgroundStage: 'compose',
        mode: 't2i',
        modelId: 'gemini-3.1-flash-image',
        prompt: '',
        negativePrompt: '',
        inputMedia: [],
        parameters: {},
        batchSize: 1,
        history: [],
        templates: [],
        queue: [],
        activeGenerationIds: [],
        featuredByGen: {},
        favoriteTemplateIds: [],
        showTemplateModal: false,
        showHistoryDrawer: false,
        modelPreferences: {},
    });
});

describe('ResultGallery ↔ store', () => {
    it('renders the generations held in the store history', () => {
        playgroundStore.setState({ history: [generation({ prompt: '穿过雾港的渡轮' })] });
        renderWithIntl(<ResultGallery />);

        expect(screen.getByText('穿过雾港的渡轮')).toBeInTheDocument();
    });

    it('falls back to the empty state when the store history is empty', () => {
        renderWithIntl(<ResultGallery />);

        expect(screen.getByText('暂无生成结果')).toBeInTheDocument();
    });

    it('filters the store history by media kind', () => {
        playgroundStore.setState({
            history: [
                generation({ id: 'g1', prompt: '一张图', mode: 't2i' }),
                generation({ id: 'g2', prompt: '一段视频', mode: 't2v' }),
            ],
        });
        renderWithIntl(<ResultGallery />);

        fireEvent.click(screen.getByRole('button', { name: '视频' }));

        expect(screen.getByText('一段视频')).toBeInTheDocument();
        expect(screen.queryByText('一张图')).not.toBeInTheDocument();
    });

    // Guards the module-scope playgroundStore.getState() in handleDelete —
    // the one call site a React context provider cannot reach.
    it('removes the deleted generation from the store, not just the local view', async () => {
        // Delete is only offered on a failed generation — that is the card that
        // renders the button, so the store's only getState() call site is
        // reachable exclusively through this path.
        playgroundStore.setState({
            history: [generation({ status: 'failed', error: 'provider rejected the request' })],
        });
        renderWithIntl(<ResultGallery />);

        fireEvent.click(screen.getByRole('button', { name: /删除/ }));

        await waitFor(() => expect(store().history).toHaveLength(0));
        expect(mockDeleteGeneration).toHaveBeenCalledWith('g1');
    });

    // ResultGallery passes an explicit targetMode, unlike ResultCard's default.
    it('sends an image to i2v rather than i2i when asked to generate video', () => {
        playgroundStore.setState({ history: [generation()] });
        renderWithIntl(<ResultGallery />);

        fireEvent.click(screen.getByTitle('生成视频'));

        expect(store().mode).toBe('i2v');
        expect(store().inputMedia).toEqual(['output/playground/a.png']);
    });
});

describe('DetailPanel ↔ store', () => {
    // The panel is handed a generation by prop but deliberately prefers the
    // store's copy, so a save//featured update made elsewhere stays in sync.
    it('prefers the store copy of the generation over the prop it was given', () => {
        const stale = generation({ prompt: '旧的提示词' });
        playgroundStore.setState({ history: [generation({ prompt: '新的提示词' })] });

        renderWithIntl(
            <DetailPanel
                generation={stale}
                allGenerations={[stale]}
                onClose={() => {}}
                onNavigate={() => {}}
            />,
        );

        expect(screen.getByText(/新的提示词/)).toBeInTheDocument();
        expect(screen.queryByText(/旧的提示词/)).not.toBeInTheDocument();
    });

    it('records the featured pick in the store', () => {
        const gen = generation();
        playgroundStore.setState({ history: [gen] });
        renderWithIntl(
            <DetailPanel
                generation={gen}
                allGenerations={[gen]}
                onClose={() => {}}
                onNavigate={() => {}}
            />,
        );

        fireEvent.click(screen.getByRole('button', { name: /精选/ }));

        expect(store().featuredByGen).toEqual({ g1: 'o1' });
    });
});

describe('PromptTemplateModal ↔ store', () => {
    it('stays closed while the store flag is false', () => {
        renderWithIntl(<PromptTemplateModal />);

        expect(screen.queryByText('Prompt 模板')).not.toBeInTheDocument();
    });

    it('lists the templates held in the store', () => {
        playgroundStore.setState({
            showTemplateModal: true,
            templates: [
                { id: 't1', name: '赛博雨夜', category: 'image', prompt: '霓虹, 湿地面' } as any,
            ],
        });
        renderWithIntl(<PromptTemplateModal />);

        expect(screen.getByText('赛博雨夜')).toBeInTheDocument();
    });

    it('applies a template through the store', async () => {
        playgroundStore.setState({
            showTemplateModal: true,
            templates: [
                { id: 't1', name: '赛博雨夜', category: 'image', prompt: '霓虹, 湿地面' } as any,
            ],
        });
        renderWithIntl(<PromptTemplateModal />);

        fireEvent.click(screen.getByRole('button', { name: '套用' }));

        expect(store().prompt).toBe('霓虹, 湿地面');
        // Applying also closes the modal behind a 250ms transition. Await it, or
        // the timer fires after teardown and setState explodes on a dead tree.
        await waitFor(() => expect(store().showTemplateModal).toBe(false));
    });

    it('keeps the favourite toggle in the store, not in local state', () => {
        playgroundStore.setState({
            showTemplateModal: true,
            templates: [
                { id: 't1', name: '赛博雨夜', category: 'image', prompt: '霓虹, 湿地面' } as any,
            ],
        });
        renderWithIntl(<PromptTemplateModal />);

        fireEvent.click(screen.getByTitle('收藏'));

        expect(store().favoriteTemplateIds).toContain('t1');
    });
});

describe('PlaygroundPage ↔ store', () => {
    // The generate button does not POST directly — it enqueues, and a pump
    // dispatches under the concurrency limit. Both halves live in the store.
    it('enqueues the compose state rather than posting straight away', async () => {
        playgroundStore.setState({
            prompt: '雨夜的天台',
            maxConcurrent: 0, // hold the pump so the request stays observable in the queue
        });
        renderWithIntl(<PlaygroundPage />);

        fireEvent.click(screen.getByRole('button', { name: '生成' }));

        await waitFor(() => expect(store().queue).toHaveLength(1));
        expect(store().queue[0]).toMatchObject({
            prompt: '雨夜的天台',
            mode: 't2i',
            status: 'pending',
        });
        expect(mockGenerate).not.toHaveBeenCalled();
    });

    it('auto-detects i2i from the store when t2i already has reference media', async () => {
        playgroundStore.setState({
            prompt: '换成黄昏',
            mode: 't2i',
            inputMedia: ['output/library/linwan.png'],
            maxConcurrent: 0,
        });
        renderWithIntl(<PlaygroundPage />);

        fireEvent.click(screen.getByRole('button', { name: '生成' }));

        await waitFor(() => expect(store().queue).toHaveLength(1));
        expect(store().queue[0].mode).toBe('i2i');
    });

    // Guards the pump's playgroundStore.getState() at PlaygroundPage.tsx:204 —
    // the second call site a context provider cannot reach.
    it('pumps a queued request out to the API and drains the queue', async () => {
        playgroundStore.setState({ prompt: '雨夜的天台', maxConcurrent: 2 });
        renderWithIntl(<PlaygroundPage />);

        fireEvent.click(screen.getByRole('button', { name: '生成' }));

        await waitFor(() => expect(mockGenerate).toHaveBeenCalledTimes(1));
        expect(mockGenerate).toHaveBeenCalledWith(
            expect.objectContaining({ prompt: '雨夜的天台', mode: 't2i' }),
        );
        await waitFor(() => expect(store().queue).toHaveLength(0));
    });

    // The pump reads queue / maxConcurrent / activeGenerationIds off the store to
    // decide how many slots are free; break that read and it dispatches anyway.
    it('holds a request back when the store says every slot is busy', async () => {
        playgroundStore.setState({
            prompt: '雨夜的天台',
            maxConcurrent: 1,
            activeGenerationIds: ['already-running'],
        });
        renderWithIntl(<PlaygroundPage />);

        fireEvent.click(screen.getByRole('button', { name: '生成' }));

        await waitFor(() => expect(store().queue).toHaveLength(1));
        expect(store().queue[0].status).toBe('pending');
        expect(mockGenerate).not.toHaveBeenCalled();
    });

    it('refuses to enqueue when the store holds no prompt', () => {
        renderWithIntl(<PlaygroundPage />);

        fireEvent.click(screen.getByRole('button', { name: '生成' }));

        expect(store().queue).toHaveLength(0);
    });
});
