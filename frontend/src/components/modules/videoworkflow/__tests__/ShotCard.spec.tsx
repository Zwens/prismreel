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

let pickerOnSelect: ((path: string) => void) | null = null;

vi.mock('../../playground/AssetSourcePicker', () => ({
    default: ({ isOpen, onSelect }: { isOpen: boolean; onSelect: (path: string) => void }) => {
        pickerOnSelect = onSelect;
        if (!isOpen) return null;
        return (
            <button type="button" data-testid="pick-video-asset" onClick={() => onSelect('clip.mp4')}>
                pick video
            </button>
        );
    },
}));

import ShotCard from '../ShotCard';
import { useShotSequenceStore } from '../useShotSequenceStore';

describe('ShotCard', () => {
    beforeEach(() => {
        useShotSequenceStore.getState().reset();
        pickerOnSelect = null;
        vi.restoreAllMocks();
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

    it('calls onMoveUp/onMoveDown and respects canMoveUp/canMoveDown disabling', () => {
        const shot = useShotSequenceStore.getState().shots[0];
        const onMoveUp = vi.fn();
        const onMoveDown = vi.fn();
        renderWithIntl(
            <ShotCard
                shot={shot}
                index={1}
                onRemove={() => {}}
                onMoveUp={onMoveUp}
                onMoveDown={onMoveDown}
                canMoveUp={true}
                canMoveDown={false}
            />,
        );

        const moveUpButton = screen.getByRole('button', { name: '上移镜头' });
        const moveDownButton = screen.getByRole('button', { name: '下移镜头' });
        expect(moveUpButton).not.toBeDisabled();
        expect(moveDownButton).toBeDisabled();

        fireEvent.click(moveUpButton);
        expect(onMoveUp).toHaveBeenCalledTimes(1);
    });

    it('asks for confirmation before replacing existing images with a video, and skips the replacement on cancel', () => {
        const shot = useShotSequenceStore.getState().shots[0];
        useShotSequenceStore.getState().setShotMedia(shot.id, ['a.png'], 'image');
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

        const updatedShot = useShotSequenceStore.getState().shots[0];
        renderWithIntl(<ShotCard shot={updatedShot} index={0} onRemove={() => {}} />);

        fireEvent.click(screen.getByText('从素材库选取'));
        expect(pickerOnSelect).not.toBeNull();
        pickerOnSelect!('clip.mp4');

        expect(confirmSpy).toHaveBeenCalled();
        expect(useShotSequenceStore.getState().shots[0].media).toEqual(['a.png']);
        expect(useShotSequenceStore.getState().shots[0].mediaType).toBe('image');
    });

    it('replaces images with the video once the user confirms', () => {
        const shot = useShotSequenceStore.getState().shots[0];
        useShotSequenceStore.getState().setShotMedia(shot.id, ['a.png'], 'image');
        vi.spyOn(window, 'confirm').mockReturnValue(true);

        const updatedShot = useShotSequenceStore.getState().shots[0];
        renderWithIntl(<ShotCard shot={updatedShot} index={0} onRemove={() => {}} />);

        fireEvent.click(screen.getByText('从素材库选取'));
        pickerOnSelect!('clip.mp4');

        expect(useShotSequenceStore.getState().shots[0].media).toEqual(['clip.mp4']);
        expect(useShotSequenceStore.getState().shots[0].mediaType).toBe('video');
    });
});
