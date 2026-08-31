/**
 * Tests for the「一键生成所有素材」batch queue on Cast (Step 3).
 *
 * Generating six assets one by one means opening the workbench modal six
 * times. The batch button skips the modal and reuses the same per-asset
 * submit path, so the only new logic worth isolating is: which assets to
 * pick, and how hard to hit the image API while doing it.
 */
import { describe, it, expect } from 'vitest';
import {
    BATCH_VARIANT_COUNT,
    pickPendingAssets,
    runWithConcurrencyLimit,
} from '@/lib/batchGeneration';

const items = [
    { id: 'c1', name: '吴老狗 (浴袍)', kind: 'character' as const, status: 'pending' as const },
    { id: 'c2', name: '张启山 (浴袍)', kind: 'character' as const, status: 'pending' as const },
    { id: 's1', name: '澡堂', kind: 'scene' as const, status: 'ready' as const, referenceImageUrl: 'assets/scenes/a.png' },
    { id: 'p1', name: '木盆', kind: 'prop' as const, status: 'pending' as const },
];

describe('pickPendingAssets', () => {
    it('只挑出待生成的素材', () => {
        expect(pickPendingAssets(items).map((i) => i.id)).toEqual(['c1', 'c2', 'p1']);
    });

    it('跳过已有参考图的素材，不覆盖已生成结果', () => {
        expect(pickPendingAssets(items).some((i) => i.id === 's1')).toBe(false);
    });

    it('全部生成完毕时返回空数组', () => {
        const allReady = items.map((i) => ({ ...i, status: 'ready' as const }));
        expect(pickPendingAssets(allReady)).toEqual([]);
    });
});

describe('BATCH_VARIANT_COUNT', () => {
    it('批量每个素材只生成 1 张，避免翻倍消耗额度', () => {
        // The workbench modal defaults to 2 variants; a batch of six assets
        // would silently double the spend.
        expect(BATCH_VARIANT_COUNT).toBe(1);
    });
});

describe('runWithConcurrencyLimit', () => {
    it('并发数不超过上限', async () => {
        let running = 0;
        let peak = 0;
        const factories = Array.from({ length: 6 }, () => async () => {
            running += 1;
            peak = Math.max(peak, running);
            await new Promise((r) => setTimeout(r, 5));
            running -= 1;
        });

        await runWithConcurrencyLimit(factories, 2);

        expect(peak).toBe(2);
    });

    it('全部任务都会执行', async () => {
        const seen: number[] = [];
        const factories = Array.from({ length: 5 }, (_, i) => async () => {
            seen.push(i);
        });

        await runWithConcurrencyLimit(factories, 2);

        expect(seen.sort()).toEqual([0, 1, 2, 3, 4]);
    });

    it('单个任务失败不中断队列，并回报成败计数', async () => {
        const done: string[] = [];
        const factories = [
            async () => { done.push('ok1'); },
            async () => { throw new Error('boom'); },
            async () => { done.push('ok2'); },
        ];

        const result = await runWithConcurrencyLimit(factories, 2);

        expect(done).toEqual(['ok1', 'ok2']);
        expect(result.succeeded).toBe(2);
        expect(result.failed).toBe(1);
    });
});
