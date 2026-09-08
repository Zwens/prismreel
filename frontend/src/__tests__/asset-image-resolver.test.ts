import { describe, it, expect } from 'vitest';
import { resolveAssetMedia } from '@/lib/assetImageResolver';

// resolveAssetMedia() is the single normalisation point the four-source
// AssetSourcePicker uses to turn a library / series / project / history record
// into something the playground can put in input_media.
//
// The four sources store their image in four different shapes, and characters
// alone carry two schema eras. Every one of those shapes is pinned here so a
// picker tab can't silently render blank tiles.

describe('resolveAssetMedia — character', () => {
    it('prefers the selected variant of the new reference_sheet container', () => {
        const character = {
            id: 'c1',
            name: '林晚',
            reference_sheet: {
                selected_image_id: 'v2',
                image_variants: [
                    { id: 'v1', url: 'output/library/c1-a.png', created_at: 1 },
                    { id: 'v2', url: 'output/library/c1-b.png', created_at: 2 },
                ],
            },
        };

        expect(resolveAssetMedia(character, 'character')?.path).toBe('output/library/c1-b.png');
    });

    it('falls back to the legacy full_body_asset when reference_sheet is empty', () => {
        const character = {
            id: 'c1',
            name: '林晚',
            reference_sheet: { selected_image_id: null, image_variants: [] },
            full_body_asset: {
                selected_id: 'v9',
                variants: [{ id: 'v9', url: 'output/library/legacy.png', created_at: 1 }],
            },
        };

        expect(resolveAssetMedia(character, 'character')?.path).toBe('output/library/legacy.png');
    });

    it('falls back to the top-level image_url when neither container has variants', () => {
        const character = { id: 'c1', name: '林晚', image_url: 'output/library/flat.png' };

        expect(resolveAssetMedia(character, 'character')?.path).toBe('output/library/flat.png');
    });
});

describe('resolveAssetMedia — scene and prop', () => {
    it('prefers the selected variant of image_asset', () => {
        const scene = {
            id: 's1',
            name: '雨夜天台',
            image_url: 'output/series/stale.png',
            image_asset: {
                selected_id: 'v2',
                variants: [
                    { id: 'v1', url: 'output/series/s1-a.png', created_at: 1 },
                    { id: 'v2', url: 'output/series/s1-b.png', created_at: 2 },
                ],
            },
        };

        expect(resolveAssetMedia(scene, 'scene')?.path).toBe('output/series/s1-b.png');
    });

    it('falls back to image_url when image_asset has no variants', () => {
        const prop = { id: 'p1', name: '旧怀表', image_url: 'output/series/p1.png' };

        expect(resolveAssetMedia(prop, 'prop')?.path).toBe('output/series/p1.png');
    });
});

describe('resolveAssetMedia — storyboard frame', () => {
    it('takes the active T2I candidate at t2i_selected_index', () => {
        const frame = {
            id: 'f1',
            image_url: 'output/storyboard/f1-old.png',
            t2i_image_urls: [
                'output/storyboard/f1-a.png',
                'output/storyboard/f1-b.png',
                'output/storyboard/f1-c.png',
            ],
            t2i_selected_index: 1,
        };

        expect(resolveAssetMedia(frame, 'frame')?.path).toBe('output/storyboard/f1-b.png');
    });

    it('clamps an out-of-range t2i_selected_index instead of returning undefined', () => {
        const frame = {
            id: 'f1',
            t2i_image_urls: ['output/storyboard/f1-a.png', 'output/storyboard/f1-b.png'],
            t2i_selected_index: 7,
        };

        expect(resolveAssetMedia(frame, 'frame')?.path).toBe('output/storyboard/f1-b.png');
    });

    it('prefers rendered_image_url over image_url when there is no T2I history', () => {
        const frame = {
            id: 'f1',
            image_url: 'output/storyboard/raw.png',
            rendered_image_url: 'output/storyboard/rendered.png',
            t2i_image_urls: [],
        };

        expect(resolveAssetMedia(frame, 'frame')?.path).toBe('output/storyboard/rendered.png');
    });
});

describe('resolveAssetMedia — generation output', () => {
    it('reads media_path and reports an image', () => {
        const output = { id: 'o1', media_path: 'output/playground/gen.png' };

        const resolved = resolveAssetMedia(output, 'generation');
        expect(resolved?.path).toBe('output/playground/gen.png');
        expect(resolved?.type).toBe('image');
    });

    it('reports a video for a video extension so video-only slots can filter', () => {
        const output = { id: 'o1', media_path: 'output/playground/gen.MP4' };

        expect(resolveAssetMedia(output, 'generation')?.type).toBe('video');
    });
});

describe('resolveAssetMedia — no resolvable image', () => {
    it('returns null for an asset that has no image at all', () => {
        expect(resolveAssetMedia({ id: 'c1', name: '未生成' }, 'character')).toBeNull();
    });

    it('returns null rather than throwing on a null asset', () => {
        expect(resolveAssetMedia(null, 'scene')).toBeNull();
    });
});
