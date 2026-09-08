import { screen, fireEvent } from '@testing-library/react';
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
        getHistory: vi.fn().mockResolvedValue([]),
        uploadMedia: vi.fn(),
    },
}));

import MediaInput from '../MediaInput';
import { playgroundStore } from '../usePlaygroundStore';

beforeEach(() => {
    playgroundStore.setState({ mode: 'i2v', inputMedia: [] });
});

describe('MediaInput — asset source', () => {
    // The playground's picker used to be history-only, so a character sheet the
    // user had just built in the library was unreachable from a first-frame
    // slot. Opening the picker must now land on the library.
    it('opens the four-source picker, which starts on the global library', async () => {
        renderWithIntl(<MediaInput />);

        fireEvent.click(screen.getByRole('button', { name: '从资产库选取' }));

        expect(await screen.findByRole('tab', { name: '素材库' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: '系列' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: '项目' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: '生成历史' })).toBeInTheDocument();
    });
});
