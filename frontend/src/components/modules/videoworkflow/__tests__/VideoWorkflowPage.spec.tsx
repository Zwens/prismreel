import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

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
        listLibraryAssets: vi.fn().mockResolvedValue({ characters: [], scenes: [], props: [] }),
        listSeries: vi.fn().mockResolvedValue([]),
        getProjects: vi.fn().mockResolvedValue([]),
        getProject: vi.fn().mockResolvedValue({ frames: [] }),
    },
    playgroundApi: {
        generate: vi.fn(),
        getGenerationStatus: vi.fn(),
        getGeneration: vi.fn(),
        getHistory: vi.fn().mockResolvedValue([]),
        concat: vi.fn(),
    },
}));

import { playgroundApi } from '@/lib/api';
import VideoWorkflowPage from '../VideoWorkflowPage';
import { useShotSequenceStore, MAX_SHOTS } from '../useShotSequenceStore';

describe('VideoWorkflowPage', () => {
    beforeEach(() => {
        useShotSequenceStore.getState().reset();
    });

    it('renders one shot card initially and can add another', () => {
        renderWithIntl(<VideoWorkflowPage />);
        expect(screen.getAllByRole('textbox')).toHaveLength(1);

        fireEvent.click(screen.getByRole('button', { name: '新增镜头' }));
        expect(screen.getAllByRole('textbox')).toHaveLength(2);
    });

    it('caps shots at MAX_SHOTS — the add button disables at the limit', () => {
        renderWithIntl(<VideoWorkflowPage />);
        const addButton = screen.getByRole('button', { name: '新增镜头' });
        for (let i = 1; i < MAX_SHOTS; i++) fireEvent.click(addButton);

        expect(screen.getAllByRole('textbox')).toHaveLength(MAX_SHOTS);
        expect(screen.getByRole('button', { name: /已达镜头数量上限/ })).toBeDisabled();
    });

    it('disables combine until every shot is completed, then calls concat with outputs in order', async () => {
        renderWithIntl(<VideoWorkflowPage />);
        const combineButton = screen.getByRole('button', { name: '合成完整影片' });
        expect(combineButton).toBeDisabled();

        // Simulate two completed shots directly via the store (unit-level assertion,
        // not exercising the full generate flow — that's useShotGeneration's own test).
        const [firstId] = useShotSequenceStore.getState().shots.map((s) => s.id);
        useShotSequenceStore.getState().addShot();
        const [, secondId] = useShotSequenceStore.getState().shots.map((s) => s.id);
        useShotSequenceStore.getState().setShotStatus(firstId, 'completed', { outputPath: 'playground/videos/a.mp4' });
        useShotSequenceStore.getState().setShotStatus(secondId, 'completed', { outputPath: 'playground/videos/b.mp4' });

        (playgroundApi.concat as any).mockResolvedValue({ path: 'playground/videos/workflow_final.mp4' });

        await waitFor(() => expect(combineButton).not.toBeDisabled());
        fireEvent.click(combineButton);

        await waitFor(() =>
            expect(playgroundApi.concat).toHaveBeenCalledWith(['playground/videos/a.mp4', 'playground/videos/b.mp4']),
        );
    });

    it('does not re-generate a shot that is already queued/processing when Generate all is clicked twice', async () => {
        (playgroundApi.generate as any).mockResolvedValue({ id: 'g1', status: 'processing', outputs: [] });
        useShotSequenceStore.getState().updateShotPrompt(
            useShotSequenceStore.getState().shots[0].id,
            'a robot dancing',
        );

        renderWithIntl(<VideoWorkflowPage />);
        const generateAllButton = screen.getByRole('button', { name: '全部生成' });

        fireEvent.click(generateAllButton);
        await waitFor(() => expect(playgroundApi.generate).toHaveBeenCalledTimes(1));

        fireEvent.click(generateAllButton);
        // Flush any microtasks the second click's generateShot calls might have queued.
        await waitFor(() => expect(playgroundApi.generate).toHaveBeenCalledTimes(1));
    });
});
