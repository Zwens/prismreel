import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * A mode with no model behind it.
 *
 * ModelSelector adopts a valid model whenever the current one cannot serve the
 * selected mode — but only when the mode has something to adopt. With an empty
 * list the effect is skipped entirely, so the previous mode's model id survives
 * in the store and gets submitted against a mode it cannot serve. The collapsed
 * selector goes on showing that model's name, so nothing on screen says
 * otherwise; the "no model" line only exists inside the opened dropdown.
 *
 * This is not hypothetical. Retiring the wan and happyhorse families during the
 * DashScope removal briefly left v2v with nothing, and t2i's adopted
 * gemini-3-pro-image stayed selected after switching to it.
 *
 * The catalog is stubbed down to a single t2v model so every other mode is
 * genuinely empty — the real catalog covers every mode, which is exactly why
 * this went unnoticed.
 */

const catalogStub = vi.hoisted(() => ({
    models: {
        'only-t2v': {
            id: 'only-t2v',
            display_name: 'Only T2V',
            family: 'seedance',
            description: 'the one model in this catalog',
            capabilities: ['t2v'],
            status: 'available',
            ui: { recommended: true, order: 10, badges: [] },
            duration: { type: 'slider', min: 4, max: 12, step: 1, default: 5 },
            params: { resolution: { options: ['720p'], default: '720p' }, seed: true },
            inputs: {},
        },
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
    id: 'g1', mode: 't2v', model_id: 'only-t2v', prompt: '', status: 'completed',
    input_media: [], parameters: {}, batch_size: 1, outputs: [],
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

import ModelSelector from '../ModelSelector';
import { VideoGenWorkspace } from '../VideoGenPage';
import {
    playgroundStore,
    createPlaygroundStore,
    PlaygroundStoreProvider,
    type PlaygroundState,
    type PlaygroundStoreApi,
} from '../usePlaygroundStore';

const store = () => playgroundStore.getState();

// VideoGenPage owns its own store instance rather than the module-level
// singleton (2026-09-18 nav reorg). Build that instance here and feed it to
// the exported workspace component directly, same pattern as storeWiring.surfaces.
function renderVideoGen(initial: Partial<PlaygroundState> = {}) {
    const videoStore: PlaygroundStoreApi = createPlaygroundStore();
    videoStore.setState({
        playgroundStage: 'compose',
        mode: 't2v', modelId: '', prompt: '', negativePrompt: '', inputMedia: [],
        parameters: {}, batchSize: 1, history: [], templates: [], queue: [],
        activeGenerationIds: [], maxConcurrent: 3, modelPreferences: {},
        ...initial,
    });
    renderWithIntl(
        <PlaygroundStoreProvider store={videoStore}>
            <VideoGenWorkspace />
        </PlaygroundStoreProvider>,
    );
    return () => videoStore.getState();
}

beforeEach(() => {
    vi.clearAllMocks();
    playgroundStore.setState({
        // 三段式 UI 默认停在 select；这些用例测的是 compose 的提交行为
        playgroundStage: 'compose',
        mode: 't2v', modelId: '', prompt: '', negativePrompt: '', inputMedia: [],
        parameters: {}, batchSize: 1, history: [], templates: [], queue: [],
        activeGenerationIds: [], maxConcurrent: 3, modelPreferences: {},
    });
});

describe('ModelSelector — a mode with nothing to offer', () => {
    it('adopts the one valid model while the mode can be served', () => {
        renderWithIntl(<ModelSelector />);

        expect(store().modelId).toBe('only-t2v');
    });

    it('drops the stale model id when the mode changes to one with no model', async () => {
        renderWithIntl(<ModelSelector />);
        expect(store().modelId).toBe('only-t2v');

        playgroundStore.setState({ mode: 'i2v' });

        await waitFor(() => expect(store().modelId).toBe(''));
    });

    it('stops presenting the stale model as the current selection', async () => {
        renderWithIntl(<ModelSelector />);
        playgroundStore.setState({ mode: 'i2v' });

        await waitFor(() =>
            expect(screen.queryByText('Only T2V')).not.toBeInTheDocument(),
        );
    });
});

describe('VideoGenPage — a mode with nothing to offer', () => {
    it('still generates while the mode has a model', async () => {
        renderVideoGen({ prompt: '海面上的暴风雨' });

        fireEvent.click(screen.getByRole('button', { name: '生成' }));

        await waitFor(() => expect(mockGenerate).toHaveBeenCalled());
    });

    it('refuses to generate for a mode no model can serve', async () => {
        const getState = renderVideoGen({ prompt: '海面上的暴风雨', mode: 'i2v' });

        await waitFor(() => expect(getState().modelId).toBe(''));
        expect(screen.getByRole('button', { name: '生成' })).toBeDisabled();
    });

    it('says why instead of leaving the button dead', () => {
        renderVideoGen({ prompt: '海面上的暴风雨', mode: 'i2v' });

        expect(screen.getByText('当前模式无可用模型')).toBeInTheDocument();
    });
});
