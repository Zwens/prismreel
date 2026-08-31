/**
 * Tests for auto-completing [characterN:name] reference tags in a shot prompt.
 *
 * R2V resolves reference images by parsing these tags out of the prompt, but
 * nothing writes them: across EP.02's 13 shots there were 0 tags while every
 * shot already carried exact character_ids / scene_id / prop_ids. The user had
 * to click each asset chip by hand or generate with no references at all.
 *
 * The slot number is load-bearing — slot N maps to reference_image_urls[N-1] —
 * so an existing tag's number must never be renumbered, and one asset must
 * never occupy two slots.
 */
import { describe, it, expect } from 'vitest';
import { augmentPromptWithAssetTags } from '@/lib/assetTags';

describe('augmentPromptWithAssetTags', () => {
    it('给没有标签的提示词按顺序补上槽位', () => {
        const { prompt, added } = augmentPromptWithAssetTags(
            '热气腾腾的浴室内，两人隔着水汽相对而立。',
            ['张启山 (浴袍)', '吴老狗 (浴袍)', '赛博朋克风高级私人浴室'],
        );

        expect(prompt).toContain('[character1:张启山 (浴袍)]');
        expect(prompt).toContain('[character2:吴老狗 (浴袍)]');
        expect(prompt).toContain('[character3:赛博朋克风高级私人浴室]');
        expect(added).toEqual(['张启山 (浴袍)', '吴老狗 (浴袍)', '赛博朋克风高级私人浴室']);
    });

    it('原有正文一个字不改，标签只追加在末尾', () => {
        const original = '热气腾腾的浴室内，两人隔着水汽相对而立。';

        const { prompt } = augmentPromptWithAssetTags(original, ['张启山 (浴袍)']);

        expect(prompt.startsWith(original)).toBe(true);
    });

    it('已存在的标签不重复添加，槽位号原样保留', () => {
        const { prompt, added } = augmentPromptWithAssetTags(
            '[character2:吴老狗 (浴袍)] 掏出一个盒子。',
            ['张启山 (浴袍)', '吴老狗 (浴袍)'],
        );

        expect(prompt).toContain('[character2:吴老狗 (浴袍)]');
        expect(prompt).not.toContain('[character1:吴老狗 (浴袍)]');
        expect(added).toEqual(['张启山 (浴袍)']);
    });

    it('新槽位号接在已用的最大号之后，不与旧号冲突', () => {
        const { prompt } = augmentPromptWithAssetTags(
            '[character3:吴老狗 (浴袍)] 站在门口。',
            ['吴老狗 (浴袍)', '玻璃水杯'],
        );

        expect(prompt).toContain('[character4:玻璃水杯]');
    });

    it('全部素材都已引用时原样返回，不留多余空白', () => {
        const original = '[character1:张启山 (浴袍)] 抬起头。';

        const { prompt, added } = augmentPromptWithAssetTags(original, ['张启山 (浴袍)']);

        expect(prompt).toBe(original);
        expect(added).toEqual([]);
    });

    it('没有关联素材时原样返回', () => {
        const original = '空镜：雨水打在窗上。';

        const { prompt, added } = augmentPromptWithAssetTags(original, []);

        expect(prompt).toBe(original);
        expect(added).toEqual([]);
    });

    it('素材名里的括号等正则元字符不会破坏匹配', () => {
        // '张启山 (浴袍)' contains regex-special parens; a naive RegExp built
        // from the raw name would never match the tag that is already there.
        const original = '[character1:张启山 (浴袍)] 靠在池边。';

        const { added } = augmentPromptWithAssetTags(original, ['张启山 (浴袍)']);

        expect(added).toEqual([]);
    });

    it('同一素材在关联里重复出现只占一个槽位', () => {
        const { prompt, added } = augmentPromptWithAssetTags(
            '两人对峙。',
            ['张启山 (浴袍)', '张启山 (浴袍)'],
        );

        expect(added).toEqual(['张启山 (浴袍)']);
        expect(prompt).toContain('[character1:张启山 (浴袍)]');
        expect(prompt).not.toContain('[character2:');
    });

    it('空提示词也能补出标签', () => {
        const { prompt } = augmentPromptWithAssetTags('', ['玻璃水杯']);

        expect(prompt.trim()).toBe('[character1:玻璃水杯]');
    });
});
