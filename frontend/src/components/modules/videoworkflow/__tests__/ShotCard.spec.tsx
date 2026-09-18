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
        generate: vi.fn().mockResolvedValue({ id: 'g1', status: 'processing', outputs: [] }),
        getGenerationStatus: vi.fn(),
        getGeneration: vi.fn(),
        getHistory: vi.fn().mockResolvedValue([]),
    },
}));

import ShotCard from '../ShotCard';
import { useShotSequenceStore } from '../useShotSequenceStore';

describe('ShotCard', () => {
    beforeEach(() => {
        useShotSequenceStore.getState().reset();
    });

    it('renders the prompt textarea and updates the store on change', () => {
        const shot = useShotSequenceStore.getState().shots[0];
        renderWithIntl(<ShotCard shot={shot} index={0} onRemove={() => {}} />);

        const textarea = screen.getByRole('textbox');
        fireEvent.change(textarea, { target: { value: 'a robot dancing' } });

        expect(useShotSequenceStore.getState().shots[0].prompt).toBe('a robot dancing');
    });

    it('calls onRemove when the remove button is clicked', () => {
        const shot = useShotSequenceStore.getState().shots[0];
        const onRemove = vi.fn();
        renderWithIntl(<ShotCard shot={shot} index={0} onRemove={onRemove} />);

        fireEvent.click(screen.getByRole('button', { name: '删除镜头' }));
        expect(onRemove).toHaveBeenCalled();
    });

    it('disables the generate button when the prompt is empty', () => {
        const shot = useShotSequenceStore.getState().shots[0];
        renderWithIntl(<ShotCard shot={shot} index={0} onRemove={() => {}} />);

        const generateButton = screen.getByRole('button', { name: '生成此镜头' });
        expect(generateButton).toBeDisabled();
    });
});
