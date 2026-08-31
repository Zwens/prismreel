/**
 * Tests for [characterN:name] tag → asset resolution.
 *
 * The tag labels are written by the LLM that drafts / polishes a shot
 * prompt, and it routinely shortens an asset's real name — "机械鸟" for
 * "现代智能机械鸟", "二月红" for "二月红 (现代)". Exact-match lookup
 * dropped those references, so R2V generation refused the shot with
 * "引用的「机械鸟」尚未生成图片" while the asset sat right there in the
 * cast, generated and ready.
 */
import { describe, it, expect } from 'vitest';
import { resolveAssetByTagName } from '@/lib/assetTags';

const characters = [
    { name: '张启山 (现代)' },
    { name: '二月红 (现代)' },
    { name: '霍仙姑 (现代)' },
];
const scenes = [{ name: '现代高层会议室' }, { name: '现代都市夜景' }];
const props = [
    { name: '现代智能机械鸟' },
    { name: '老式粗陶酒碗' },
    { name: '现代酒杯/茶盏' },
    { name: '现代酒杯与茶盏' },
];
const pools = [characters, scenes, props];

describe('resolveAssetByTagName', () => {
    it('精确匹配优先', () => {
        expect(resolveAssetByTagName('张启山 (现代)', pools)?.name).toBe('张启山 (现代)');
        expect(resolveAssetByTagName('现代都市夜景', pools)?.name).toBe('现代都市夜景');
    });

    it('忽略首尾空白', () => {
        expect(resolveAssetByTagName('  现代智能机械鸟 ', pools)?.name).toBe('现代智能机械鸟');
    });

    it('LLM 写的简称能唯一还原到全名', () => {
        expect(resolveAssetByTagName('机械鸟', pools)?.name).toBe('现代智能机械鸟');
        expect(resolveAssetByTagName('二月红', pools)?.name).toBe('二月红 (现代)');
        expect(resolveAssetByTagName('霍仙姑', pools)?.name).toBe('霍仙姑 (现代)');
    });

    it('标签比素材名更长时也能还原', () => {
        expect(resolveAssetByTagName('老式粗陶酒碗（特写）'.slice(0, 6), pools)?.name).toBe('老式粗陶酒碗');
    });

    it('简称有歧义时不猜，返回 undefined', () => {
        // 同时命中「现代酒杯/茶盏」和「现代酒杯与茶盏」
        expect(resolveAssetByTagName('现代酒杯', pools)).toBeUndefined();
    });

    it('完全无关的名字返回 undefined', () => {
        expect(resolveAssetByTagName('青铜门', pools)).toBeUndefined();
        expect(resolveAssetByTagName('', pools)).toBeUndefined();
    });

    it('精确匹配不会被靠前池子的模糊匹配抢走', () => {
        const withOverlap = [[{ name: '红衣人' }], [{ name: '红' }]];
        expect(resolveAssetByTagName('红', withOverlap)?.name).toBe('红');
    });

    it('容忍池子里的空值', () => {
        expect(resolveAssetByTagName('机械鸟', [undefined as any, props])?.name).toBe('现代智能机械鸟');
    });
});
