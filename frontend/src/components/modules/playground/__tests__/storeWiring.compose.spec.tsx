import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * Store-wiring regression suite — compose column.
 *
 * These specs exist for one reason: D5 of the AI-video design replaces the
 * direct `usePlaygroundStore(...)` binding in every playground component with a
 * store injected through React context, so the standalone AI-video page can run
 * a second, independent store. That refactor's failure mode is silent — a
 * component left reading the old module-level singleton still renders, still
 * accepts clicks, and simply stops agreeing with the page around it.
 *
 * So every test here asserts the seam itself in both directions: state put into
 * the store must reach the component, and interaction with the component must
 * land back in the store. Nothing here asserts styling for its own sake.
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
    api: {
        listLibraryAssets: vi.fn().mockResolvedValue({
            characters: [{ id: 'c1', name: '林晚', image_url: 'output/library/linwan.png' }],
            scenes: [],
            props: [],
        }),
        listSeries: vi.fn().mockResolvedValue([]),
        getProjects: vi.fn().mockResolvedValue([]),
        getProject: vi.fn().mockResolvedValue({ frames: [] }),
    },
    playgroundApi: {
        getHistory: vi.fn().mockResolvedValue([]),
        createTemplate: vi.fn(),
        deleteTemplate: vi.fn(),
    },
}));

import ModeSelector from '../ModeSelector';
import PromptInput from '../PromptInput';
import MediaInput from '../MediaInput';
import QueuePanel from '../QueuePanel';
import { playgroundStore } from '../usePlaygroundStore';

const store = () => playgroundStore.getState();

beforeEach(() => {
    playgroundStore.setState({
        mode: 't2i',
        modelId: '',
        prompt: '',
        negativePrompt: '',
        inputMedia: [],
        parameters: {},
        batchSize: 1,
        showTemplateModal: false,
        showHistoryDrawer: false,
        queue: [],
        activeGenerationIds: [],
        history: [],
        templates: [],
    });
});

describe('ModeSelector ↔ store', () => {
    it('writes the clicked mode back to the store', () => {
        renderWithIntl(<ModeSelector />);

        fireEvent.click(screen.getByRole('button', { name: '图生图' }));

        expect(store().mode).toBe('i2i');
    });

    it('marks the pill that matches the store mode as active', () => {
        playgroundStore.setState({ mode: 'r2v' });
        renderWithIntl(<ModeSelector />);

        expect(screen.getByRole('button', { name: '参考生' }).className).toContain(
            'atelier-pill-tab-active',
        );
        expect(screen.getByRole('button', { name: '文生图' }).className).not.toContain(
            'atelier-pill-tab-active',
        );
    });
});

describe('PromptInput ↔ store', () => {
    it('renders the prompt held in the store', () => {
        playgroundStore.setState({ prompt: '雨夜的天台，霓虹反光' });
        renderWithIntl(<PromptInput />);

        expect(screen.getByPlaceholderText('描述你想生成的内容...')).toHaveValue(
            '雨夜的天台，霓虹反光',
        );
    });

    it('writes typing back to the store', () => {
        renderWithIntl(<PromptInput />);

        fireEvent.change(screen.getByPlaceholderText('描述你想生成的内容...'), {
            target: { value: '一只在屋顶行走的猫' },
        });

        expect(store().prompt).toBe('一只在屋顶行走的猫');
    });

    it('passes a long prompt into the store untruncated', () => {
        // main 的 6af0f0a（unbounded prompt）移除了 2000 字截断
        renderWithIntl(<PromptInput />);

        fireEvent.change(screen.getByPlaceholderText('描述你想生成的内容...'), {
            target: { value: 'x'.repeat(2500) },
        });

        expect(store().prompt).toHaveLength(2500);
    });

    it('opens the template modal through the store, not local state', () => {
        renderWithIntl(<PromptInput />);

        fireEvent.click(screen.getByRole('button', { name: '模板' }));

        expect(store().showTemplateModal).toBe(true);
    });

    it('opens the history drawer through the store, not local state', () => {
        renderWithIntl(<PromptInput />);

        fireEvent.click(screen.getByRole('button', { name: '历史' }));

        expect(store().showHistoryDrawer).toBe(true);
    });

    it('round-trips the negative prompt', () => {
        renderWithIntl(<PromptInput />);

        fireEvent.click(screen.getByText('负面提示词'));
        fireEvent.change(screen.getByPlaceholderText('不希望出现的内容...'), {
            target: { value: '模糊, 低画质' },
        });

        expect(store().negativePrompt).toBe('模糊, 低画质');
    });
});

describe('MediaInput ↔ store', () => {
    it('appends the asset picked from the library to inputMedia', async () => {
        playgroundStore.setState({ mode: 'i2v' });
        renderWithIntl(<MediaInput />);

        fireEvent.click(screen.getAllByRole('button', { name: '从资产库选取' })[0]);
        fireEvent.click(await screen.findByRole('option', { name: /林晚/ }));
        fireEvent.click(screen.getByRole('button', { name: '选择' }));

        await waitFor(() => expect(store().inputMedia).toEqual(['output/library/linwan.png']));
    });
});

describe('QueuePanel ↔ store', () => {
    it('counts the requests waiting in the store queue', () => {
        playgroundStore.setState({
            queue: [
                { id: 'q1', status: 'pending', enqueuedAt: 1 } as any,
                { id: 'q2', status: 'pending', enqueuedAt: 2 } as any,
            ],
        });
        renderWithIntl(<QueuePanel />);

        expect(screen.getByRole('button', { name: /队列/ }).textContent).toContain('2');
    });

    it('writes a lowered concurrency limit back to the store', () => {
        playgroundStore.setState({ maxConcurrent: 3 });
        renderWithIntl(<QueuePanel />);

        fireEvent.click(screen.getByRole('button', { name: /队列/ }));
        fireEvent.click(screen.getByTestId('icon-Minus').closest('button')!);

        expect(store().maxConcurrent).toBe(2);
    });
});
