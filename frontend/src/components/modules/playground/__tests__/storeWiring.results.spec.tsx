import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * Store-wiring regression suite — result surfaces and the prompt history.
 *
 * Companion to storeWiring.compose.spec.tsx; same purpose (see its header):
 * pin the `usePlaygroundStore` seam in both directions before D5 swaps it for
 * a context-injected store.
 *
 * The writes covered here are the ones with no visible confirmation of their
 * own — marking a best-of-batch, pushing a result back into the compose panel,
 * reusing a past prompt. If any of them silently stops reaching the store the
 * UI still looks completely normal.
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

vi.mock('@/lib/api', () => ({
    API_URL: 'http://localhost:17177',
    api: {},
    playgroundApi: {
        getHistory: vi.fn().mockResolvedValue([]),
        createTemplate: vi.fn(),
        deleteTemplate: vi.fn(),
        saveOutputToLibrary: vi.fn(),
    },
}));

import ResultCard from '../ResultCard';
import PromptHistoryDrawer from '../PromptHistoryDrawer';
import { usePlaygroundStore, type PlaygroundGeneration } from '../usePlaygroundStore';

const store = () => usePlaygroundStore.getState();

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
    usePlaygroundStore.setState({
        mode: 't2i',
        modelId: '',
        prompt: '',
        inputMedia: [],
        history: [],
        featuredByGen: {},
        showHistoryDrawer: false,
        showTemplateModal: false,
        modelPreferences: {},
    });
});

describe('ResultCard ↔ store', () => {
    it('records the best-of-batch pick in the store', () => {
        const gen = generation();
        renderWithIntl(<ResultCard generation={gen} />);

        fireEvent.click(screen.getByRole('button', { name: '精选' }));

        expect(store().featuredByGen).toEqual({ g1: 'o1' });
    });

    it('shows the featured badge for the output the store marks as featured', () => {
        usePlaygroundStore.setState({ featuredByGen: { g1: 'o1' } });
        renderWithIntl(<ResultCard generation={generation()} />);

        expect(screen.getByText('精选')).toBeInTheDocument();
    });

    it('shows no featured badge when the store marks a different output', () => {
        usePlaygroundStore.setState({ featuredByGen: { g1: 'other-output' } });
        renderWithIntl(<ResultCard generation={generation()} />);

        expect(screen.queryByText('精选')).not.toBeInTheDocument();
    });

    it('pushes an image result back into the compose panel as an i2i reference', () => {
        renderWithIntl(<ResultCard generation={generation()} />);

        fireEvent.click(screen.getByTitle('用作参考图'));

        expect(store().inputMedia).toEqual(['output/playground/a.png']);
        expect(store().mode).toBe('i2i');
    });

    it('sends a video result to v2v rather than i2i', () => {
        const gen = generation({
            outputs: [
                {
                    id: 'o1',
                    media_path: 'output/playground/a.mp4',
                    media_type: 'video',
                    saved_to_library: false,
                } as any,
            ],
        });
        renderWithIntl(<ResultCard generation={gen} />);

        fireEvent.click(screen.getByTitle('用作参考图'));

        expect(store().mode).toBe('v2v');
    });

    it('honours the per-mode model preference held in the store', () => {
        usePlaygroundStore.setState({ modelPreferences: { i2i: 'seedream-5-0-260128' } });
        renderWithIntl(<ResultCard generation={generation()} />);

        fireEvent.click(screen.getByTitle('用作参考图'));

        expect(store().modelId).toBe('seedream-5-0-260128');
    });
});

describe('PromptHistoryDrawer ↔ store', () => {
    it('stays closed while the store says so', () => {
        renderWithIntl(<PromptHistoryDrawer />);

        expect(screen.queryByText('Prompt 历史')).not.toBeInTheDocument();
    });

    it('opens when the store flag flips', () => {
        usePlaygroundStore.setState({ showHistoryDrawer: true });
        renderWithIntl(<PromptHistoryDrawer />);

        expect(screen.getByText('Prompt 历史')).toBeInTheDocument();
    });

    it('lists prompts from the store history', () => {
        usePlaygroundStore.setState({
            showHistoryDrawer: true,
            history: [generation({ prompt: '穿过雾港的渡轮' })],
        });
        renderWithIntl(<PromptHistoryDrawer />);

        expect(screen.getByText('穿过雾港的渡轮')).toBeInTheDocument();
    });

    it('loads a past prompt back into the store when picked', async () => {
        usePlaygroundStore.setState({
            showHistoryDrawer: true,
            history: [generation({ prompt: '穿过雾港的渡轮' })],
        });
        renderWithIntl(<PromptHistoryDrawer />);

        // "复制" is the drawer's apply action — it writes the past prompt into
        // the compose box via the store and closes the drawer.
        fireEvent.click(screen.getByRole('button', { name: '复制' }));

        expect(store().prompt).toBe('穿过雾港的渡轮');
        // The drawer unmounts behind a 250ms exit transition, so the flag flips late.
        await waitFor(() => expect(store().showHistoryDrawer).toBe(false));
    });
});
