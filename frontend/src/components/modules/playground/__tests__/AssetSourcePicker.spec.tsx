import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithIntl } from '@/test-utils/intl';
import { vi, describe, it, expect, beforeEach } from 'vitest';

// framer-motion: strip animation props so the tree renders synchronously.
vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => {
            const { initial, animate, exit, variants, transition, whileHover, ...rest } = props;
            return <div {...rest}>{children}</div>;
        },
    },
    AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// lucide-react: a Proxy rather than a hand-listed set. Enumerating icons is how
// the SeriesDetailPage spec lost 25 tests to one missing icon — an unlisted icon
// renders as undefined and takes the whole page down with a misleading
// "text not found".
vi.mock('lucide-react', () => {
    const cache = new Map<string, any>();
    return new Proxy({} as Record<string, any>, {
        // `then` must stay undefined or the module namespace looks thenable to
        // the loader, which awaits it and hangs the run forever.
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
        // Without this the loader rejects every named import as undeclared.
        has: () => true,
    });
});

const mockListLibraryAssets = vi.fn();
const mockListSeries = vi.fn();
const mockGetProjects = vi.fn();
const mockGetProject = vi.fn();
const mockGetHistory = vi.fn();
const mockGetOfficialCharacters = vi.fn();

vi.mock('@/lib/api', () => ({
    API_URL: 'http://localhost:17177',
    api: {
        listLibraryAssets: (...a: any[]) => mockListLibraryAssets(...a),
        listSeries: (...a: any[]) => mockListSeries(...a),
        getProjects: (...a: any[]) => mockGetProjects(...a),
        getProject: (...a: any[]) => mockGetProject(...a),
    },
    playgroundApi: {
        getHistory: (...a: any[]) => mockGetHistory(...a),
        getOfficialCharacters: (...a: any[]) => mockGetOfficialCharacters(...a),
    },
}));

const mockRememberOfficialCharacter = vi.fn();

vi.mock('@/lib/officialCharacterCache', () => ({
    isOfficialCharacterRef: (path: string) => path.startsWith('asset://'),
    rememberOfficialCharacter: (...a: any[]) => mockRememberOfficialCharacter(...a),
    getOfficialCharacterDisplay: (path: string) =>
        mockRememberOfficialCharacter.mock.calls.find((c) => c[0] === path)?.[1],
}));

import AssetSourcePicker from '../AssetSourcePicker';

// ── Test data ──

const globalPool = {
    characters: [
        {
            id: 'c1',
            name: '林晚',
            reference_sheet: {
                selected_image_id: 'v1',
                image_variants: [{ id: 'v1', url: 'output/library/linwan.png', created_at: 1 }],
            },
        },
        // No image yet — must be skipped rather than rendered as a blank tile.
        { id: 'c2', name: '未生成' },
    ],
    scenes: [{ id: 's1', name: '雨夜天台', image_url: 'output/library/rooftop.png' }],
    props: [],
};

const seriesList = [
    {
        id: 'ser1',
        title: '雾港',
        characters: [{ id: 'sc1', name: '陈默', image_url: 'output/series/chenmo.png' }],
        scenes: [],
        props: [],
    },
];

const projectList = [{ id: 'proj1', title: '第一集', series_id: 'ser1' }];

const projectDetail = {
    id: 'proj1',
    title: '第一集',
    frames: [
        {
            id: 'f1',
            t2i_image_urls: ['output/storyboard/f1-a.png', 'output/storyboard/f1-b.png'],
            t2i_selected_index: 1,
        },
    ],
};

const history = [
    {
        id: 'g1',
        status: 'completed',
        outputs: [{ id: 'o1', media_path: 'output/playground/gen.png' }],
        input_media: [],
    },
];

const officialCharacters = [
    {
        asset_id: 'oc1',
        nationality: '日本',
        occupation: '偶像',
        biography: '一个官方角色',
        thumbnail_url: 'https://cdn.example.com/oc1.png',
    },
];

function setup(props: Partial<React.ComponentProps<typeof AssetSourcePicker>> = {}) {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    renderWithIntl(
        <AssetSourcePicker
            isOpen
            onClose={onClose}
            onSelect={onSelect}
            accept="image"
            {...props}
        />,
    );
    return { onSelect, onClose };
}

beforeEach(() => {
    vi.clearAllMocks();
    mockListLibraryAssets.mockResolvedValue(globalPool);
    mockListSeries.mockResolvedValue(seriesList);
    mockGetProjects.mockResolvedValue(projectList);
    mockGetProject.mockResolvedValue(projectDetail);
    mockGetHistory.mockResolvedValue(history);
    mockGetOfficialCharacters.mockResolvedValue(officialCharacters);
});

// ── Tests ──

describe('AssetSourcePicker — sources', () => {
    it('offers all five sources, not just generation history', async () => {
        setup();

        expect(await screen.findByRole('tab', { name: '素材库' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: '系列' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: '项目' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: '生成历史' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: '官方角色' })).toBeInTheDocument();
    });

    it('opens on the global library rather than history', async () => {
        setup();

        await waitFor(() => expect(mockListLibraryAssets).toHaveBeenCalled());
        expect(mockGetHistory).not.toHaveBeenCalled();
    });
});

describe('AssetSourcePicker — library tab', () => {
    it('renders a tile for every asset that resolves to an image', async () => {
        setup();

        expect(await screen.findByRole('option', { name: /林晚/ })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: /雨夜天台/ })).toBeInTheDocument();
    });

    it('skips an asset with no resolvable image instead of showing a blank tile', async () => {
        setup();

        await screen.findByRole('option', { name: /林晚/ });
        expect(screen.queryByRole('option', { name: /未生成/ })).not.toBeInTheDocument();
    });

    it('hands the resolved variant path to onSelect on confirm', async () => {
        const { onSelect } = setup();

        fireEvent.click(await screen.findByRole('option', { name: /林晚/ }));
        fireEvent.click(screen.getByRole('button', { name: '选择' }));

        expect(onSelect).toHaveBeenCalledWith('output/library/linwan.png');
    });
});

describe('AssetSourcePicker — series tab', () => {
    it('shows the assets of the series the user picks', async () => {
        setup();

        fireEvent.click(await screen.findByRole('tab', { name: '系列' }));

        fireEvent.click(await screen.findByRole('button', { name: '雾港' }));
        expect(await screen.findByRole('option', { name: /陈默/ })).toBeInTheDocument();
    });
});

describe('AssetSourcePicker — project tab', () => {
    it('shows the active T2I frame of the project the user picks', async () => {
        const { onSelect } = setup();

        fireEvent.click(await screen.findByRole('tab', { name: '项目' }));
        fireEvent.click(await screen.findByRole('button', { name: '第一集' }));

        fireEvent.click(await screen.findByRole('option', { name: /f1/ }));
        fireEvent.click(screen.getByRole('button', { name: '选择' }));

        expect(onSelect).toHaveBeenCalledWith('output/storyboard/f1-b.png');
    });
});

describe('AssetSourcePicker — history tab', () => {
    it('still lists completed generation outputs', async () => {
        const { onSelect } = setup();

        fireEvent.click(await screen.findByRole('tab', { name: '生成历史' }));

        fireEvent.click(await screen.findByRole('option', { name: /gen\.png/ }));
        fireEvent.click(screen.getByRole('button', { name: '选择' }));

        expect(onSelect).toHaveBeenCalledWith('output/playground/gen.png');
    });
});

describe('AssetSourcePicker — accept filter', () => {
    it('hides images when the slot only accepts video', async () => {
        mockGetHistory.mockResolvedValue([
            {
                id: 'g1',
                status: 'completed',
                outputs: [
                    { id: 'o1', media_path: 'output/playground/gen.png' },
                    { id: 'o2', media_path: 'output/playground/clip.mp4' },
                ],
                input_media: [],
            },
        ]);
        setup({ accept: 'video' });

        fireEvent.click(await screen.findByRole('tab', { name: '生成历史' }));

        expect(await screen.findByRole('option', { name: /clip\.mp4/ })).toBeInTheDocument();
        expect(screen.queryByRole('option', { name: /gen\.png/ })).not.toBeInTheDocument();
    });

    it('hides the character and scene sources entirely for a video-only slot', async () => {
        setup({ accept: 'video' });

        expect(await screen.findByRole('tab', { name: '生成历史' })).toBeInTheDocument();
        expect(screen.queryByRole('tab', { name: '素材库' })).not.toBeInTheDocument();
        expect(screen.queryByRole('tab', { name: '官方角色' })).not.toBeInTheDocument();
    });
});

describe('AssetSourcePicker — official character source', () => {
    it('lists official characters fetched from the dedicated endpoint', async () => {
        setup();

        fireEvent.click(await screen.findByRole('tab', { name: '官方角色' }));

        expect(await screen.findByRole('option', { name: /日本 · 偶像/ })).toBeInTheDocument();
        expect(mockGetOfficialCharacters).toHaveBeenCalled();
    });

    it('remembers the thumbnail/label for the asset:// path and selects it on confirm', async () => {
        const { onSelect } = setup();

        fireEvent.click(await screen.findByRole('tab', { name: '官方角色' }));
        fireEvent.click(await screen.findByRole('option', { name: /日本 · 偶像/ }));
        fireEvent.click(screen.getByRole('button', { name: '选择' }));

        expect(mockRememberOfficialCharacter).toHaveBeenCalledWith('asset://oc1', {
            thumbnailUrl: 'https://cdn.example.com/oc1.png',
            label: '日本 · 偶像',
        });
        expect(onSelect).toHaveBeenCalledWith('asset://oc1');
    });

    it('does not fetch official characters until that tab is opened', async () => {
        setup();

        await waitFor(() => expect(mockListLibraryAssets).toHaveBeenCalled());
        expect(mockGetOfficialCharacters).not.toHaveBeenCalled();
    });
});
