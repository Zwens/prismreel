import { screen, fireEvent, within } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

/**
 * The point of D5, asserted directly.
 *
 * The other storeWiring specs all render without a provider, so they exercise
 * the fallback to the default instance — which proves the playground still
 * works, and proves nothing at all about isolation. These do the opposite: two
 * subtrees, two stores, and the demand that neither can see the other.
 *
 * That is the whole reason the store became a factory. If it ever stops holding,
 * the standalone AI-video page and the playground will quietly overwrite each
 * other's mode / prompt / inputMedia, and the symptom will show up as "the
 * playground randomly switched modes", far from the cause.
 */

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
    playgroundApi: {},
}));

import ModeSelector from '../ModeSelector';
import {
    createPlaygroundStore,
    playgroundStore,
    PlaygroundStoreProvider,
} from '../usePlaygroundStore';

beforeEach(() => {
    playgroundStore.setState({ mode: 't2i', prompt: '', inputMedia: [] });
});

describe('PlaygroundStoreProvider — instance isolation', () => {
    it('renders each subtree against its own store', () => {
        const left = createPlaygroundStore();
        const right = createPlaygroundStore();
        left.setState({ mode: 'i2i' });
        right.setState({ mode: 'r2v' });

        renderWithIntl(
            <>
                <div data-testid="left">
                    <PlaygroundStoreProvider store={left}>
                        <ModeSelector />
                    </PlaygroundStoreProvider>
                </div>
                <div data-testid="right">
                    <PlaygroundStoreProvider store={right}>
                        <ModeSelector />
                    </PlaygroundStoreProvider>
                </div>
            </>,
        );

        expect(
            within(screen.getByTestId('left')).getByRole('button', { name: '图生图' }).className,
        ).toContain('atelier-pill-tab-active');
        expect(
            within(screen.getByTestId('right')).getByRole('button', { name: '参考生' }).className,
        ).toContain('atelier-pill-tab-active');
    });

    it('keeps a write inside the subtree that made it', () => {
        const left = createPlaygroundStore();
        const right = createPlaygroundStore();

        renderWithIntl(
            <>
                <div data-testid="left">
                    <PlaygroundStoreProvider store={left}>
                        <ModeSelector />
                    </PlaygroundStoreProvider>
                </div>
                <div data-testid="right">
                    <PlaygroundStoreProvider store={right}>
                        <ModeSelector />
                    </PlaygroundStoreProvider>
                </div>
            </>,
        );

        fireEvent.click(
            within(screen.getByTestId('left')).getByRole('button', { name: '编辑' }),
        );

        expect(left.getState().mode).toBe('v2v');
        expect(right.getState().mode).toBe('t2i');
        expect(playgroundStore.getState().mode).toBe('t2i');
    });

    it('leaves the default instance untouched by a provided subtree', () => {
        const scoped = createPlaygroundStore();

        renderWithIntl(
            <PlaygroundStoreProvider store={scoped}>
                <ModeSelector />
            </PlaygroundStoreProvider>,
        );

        fireEvent.click(screen.getByRole('button', { name: '图生图' }));

        expect(scoped.getState().mode).toBe('i2i');
        expect(playgroundStore.getState().mode).toBe('t2i');
    });

    // The playground itself renders no provider, so this fallback is what keeps
    // it working unchanged after the refactor.
    it('falls back to the default instance when there is no provider', () => {
        renderWithIntl(<ModeSelector />);

        fireEvent.click(screen.getByRole('button', { name: '图生图' }));

        expect(playgroundStore.getState().mode).toBe('i2i');
    });

    it('gives each new instance its own defaults rather than shared state', () => {
        const a = createPlaygroundStore();
        a.setState({ prompt: '只属于 a 的提示词' });
        const b = createPlaygroundStore();

        expect(b.getState().prompt).toBe('');
        expect(a.getState().prompt).toBe('只属于 a 的提示词');
    });
});
