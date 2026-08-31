/**
 * Tests for resolving a storyboard frame's linked assets into R2V reference
 * image slots.
 *
 * Every frame already carries character_ids / scene_id / prop_ids, so the
 * slots can be filled by exact lookup instead of guessing names out of the
 * prose description. Before this, all 13 frames of EP.02 had zero
 * [characterN:] tags and the user filled every slot by hand from a dropdown.
 */
import { describe, it, expect } from 'vitest';
import { frameLinkedAssetNames, resolveFrameReferenceSlots } from '@/lib/frameReferenceSlots';

const project = {
    characters: [
        { id: 'c1', name: '张启山 (浴袍)', image_url: 'assets/characters/zqs.png' },
        { id: 'c2', name: '吴老狗 (浴袍)', image_url: 'assets/characters/wlg.png' },
        { id: 'c3', name: '无图角色' },
    ],
    scenes: [
        { id: 's1', name: '赛博朋克风高级私人浴室', image_url: 'assets/scenes/bath.png' },
    ],
    props: [
        { id: 'p1', name: '丝绒盒子', image_url: 'assets/props/box.png' },
        { id: 'p2', name: '智能手环/定位玉镯', image_url: 'assets/props/band.png' },
        { id: 'p3', name: '无图道具' },
    ],
};

describe('resolveFrameReferenceSlots', () => {
    it('按 角色 → 场景 → 道具 的顺序填槽', () => {
        const frame = { character_ids: ['c2', 'c1'], scene_id: 's1', prop_ids: ['p1'] };

        const { slots } = resolveFrameReferenceSlots(frame, project, 9);

        expect(slots.map((s) => s.name)).toEqual([
            '吴老狗 (浴袍)',
            '张启山 (浴袍)',
            '赛博朋克风高级私人浴室',
            '丝绒盒子',
        ]);
    });

    it('每个槽都带可用的参考图 URL', () => {
        const frame = { character_ids: ['c1'], scene_id: 's1', prop_ids: [] };

        const { slots } = resolveFrameReferenceSlots(frame, project, 9);

        expect(slots[0].url).toBe('assets/characters/zqs.png');
        expect(slots[1].url).toBe('assets/scenes/bath.png');
    });

    it('同一素材被引用两次只占一个槽', () => {
        const frame = { character_ids: ['c1', 'c1'], scene_id: null, prop_ids: [] };

        const { slots } = resolveFrameReferenceSlots(frame, project, 9);

        expect(slots).toHaveLength(1);
    });

    it('还没有参考图的素材跳过，并记入缺图清单', () => {
        const frame = { character_ids: ['c1', 'c3'], scene_id: null, prop_ids: ['p3'] };

        const { slots, missing } = resolveFrameReferenceSlots(frame, project, 9);

        expect(slots.map((s) => s.name)).toEqual(['张启山 (浴袍)']);
        expect(missing).toEqual(['无图角色', '无图道具']);
    });

    it('超过模型的参考图上限时截断，并说明截掉了谁', () => {
        const frame = { character_ids: ['c1', 'c2'], scene_id: 's1', prop_ids: ['p1', 'p2'] };

        const { slots, truncated } = resolveFrameReferenceSlots(frame, project, 3);

        expect(slots).toHaveLength(3);
        expect(slots.map((s) => s.name)).toEqual([
            '张启山 (浴袍)',
            '吴老狗 (浴袍)',
            '赛博朋克风高级私人浴室',
        ]);
        expect(truncated).toEqual(['丝绒盒子', '智能手环/定位玉镯']);
    });

    it('分镜没有任何素材关联时返回空，不抛错', () => {
        const { slots, missing, truncated } = resolveFrameReferenceSlots({}, project, 9);

        expect(slots).toEqual([]);
        expect(missing).toEqual([]);
        expect(truncated).toEqual([]);
    });

    it('引用了已被删除的素材 id 时安全跳过', () => {
        const frame = { character_ids: ['ghost'], scene_id: 's1', prop_ids: [] };

        const { slots } = resolveFrameReferenceSlots(frame, project, 9);

        expect(slots.map((s) => s.name)).toEqual(['赛博朋克风高级私人浴室']);
    });

    it('角色优先读 reference_sheet 的选中变体，其次才是旧字段', () => {
        const withSheet = {
            ...project,
            characters: [{
                id: 'c1',
                name: '张启山 (浴袍)',
                reference_sheet: {
                    selected_image_id: 'v2',
                    image_variants: [
                        { id: 'v1', url: 'assets/characters/old.png' },
                        { id: 'v2', url: 'assets/characters/sheet.png' },
                    ],
                },
                image_url: 'assets/characters/legacy.png',
            }],
        };
        const frame = { character_ids: ['c1'], scene_id: null, prop_ids: [] };

        const { slots } = resolveFrameReferenceSlots(frame, withSheet, 9);

        expect(slots[0].url).toBe('assets/characters/sheet.png');
    });
});

describe('frameLinkedAssetNames', () => {
    it('按 角色 → 场景 → 道具 的顺序列出关联素材名', () => {
        const frame = { character_ids: ['c2', 'c1'], scene_id: 's1', prop_ids: ['p1'] };

        expect(frameLinkedAssetNames(frame, project)).toEqual([
            '吴老狗 (浴袍)',
            '张启山 (浴袍)',
            '赛博朋克风高级私人浴室',
            '丝绒盒子',
        ]);
    });

    it('包含还没有参考图的素材 —— 标签声明意图，图片可以之后再生成', () => {
        const frame = { character_ids: ['c3'], scene_id: null, prop_ids: ['p3'] };

        expect(frameLinkedAssetNames(frame, project)).toEqual(['无图角色', '无图道具']);
    });

    it('重复引用去重', () => {
        const frame = { character_ids: ['c1', 'c1'], scene_id: null, prop_ids: [] };

        expect(frameLinkedAssetNames(frame, project)).toEqual(['张启山 (浴袍)']);
    });

    it('没有关联时返回空数组', () => {
        expect(frameLinkedAssetNames({}, project)).toEqual([]);
    });
});
