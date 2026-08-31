/**
 * Tests for planning a「一键生成全部」video run.
 *
 * Video generation is the expensive step, so the plan is computed up front
 * and shown in a confirm dialog: the user has to see how many shots will run
 * and which were left out before a single provider call is made. Discovering
 * "shot 07 had no reference images" only after it fails in the queue is what
 * this avoids.
 */
import { describe, it, expect } from 'vitest';
import { planBatchVideoRun } from '@/lib/batchGeneration';

type Shot = {
    id: string;
    tabMode: 'direct_r2v' | 't2i_i2v';
    videoUrl?: string;
    videoTaskId?: string;
    videoStatus?: 'pending' | 'processing' | 'completed' | 'failed';
};

const shot = (id: string, over: Partial<Shot> = {}): Shot => ({
    id,
    tabMode: 'direct_r2v',
    ...over,
});

/** Default probes: every shot is generatable. */
const allReady = {
    hasReferences: () => true,
    hasFirstFrame: () => true,
};

describe('planBatchVideoRun', () => {
    it('把没有视频的镜头排进待跑清单', () => {
        const shots = [shot('a'), shot('b')];

        const plan = planBatchVideoRun(shots, allReady);

        expect(plan.ready.map((s) => s.id)).toEqual(['a', 'b']);
        expect(plan.skipped).toEqual([]);
    });

    it('已经有视频的镜头跳过，不覆盖已出的片子', () => {
        const shots = [
            shot('a'),
            shot('done', { videoUrl: 'video/x.mp4', videoStatus: 'completed' }),
        ];

        const plan = planBatchVideoRun(shots, allReady);

        expect(plan.ready.map((s) => s.id)).toEqual(['a']);
        expect(plan.skipped).toEqual([
            { shot: shots[1], reason: 'already-generated' },
        ]);
    });

    it('已在生成中的镜头不重复排队', () => {
        const shots = [
            shot('a'),
            shot('running', { videoTaskId: 't1', videoStatus: 'processing' }),
            shot('queued', { videoTaskId: 't2', videoStatus: 'pending' }),
        ];

        const plan = planBatchVideoRun(shots, allReady);

        expect(plan.ready.map((s) => s.id)).toEqual(['a']);
        expect(plan.skipped.map((s) => s.reason)).toEqual(['in-flight', 'in-flight']);
    });

    it('上次失败的镜头会重新排进来 —— 重试正是批量该做的', () => {
        const shots = [shot('failed_once', { videoTaskId: 't1', videoStatus: 'failed' })];

        const plan = planBatchVideoRun(shots, allReady);

        expect(plan.ready.map((s) => s.id)).toEqual(['failed_once']);
    });

    it('R2V 镜头缺参考图时排除，并点名原因', () => {
        const shots = [shot('has_refs'), shot('no_refs')];
        const plan = planBatchVideoRun(shots, {
            hasReferences: (s: Shot) => s.id === 'has_refs',
            hasFirstFrame: () => true,
        });

        expect(plan.ready.map((s) => s.id)).toEqual(['has_refs']);
        expect(plan.skipped).toEqual([
            { shot: shots[1], reason: 'missing-refs' },
        ]);
    });

    it('I2V 镜头缺首帧时排除，走的是另一套前置条件', () => {
        const shots = [shot('i2v', { tabMode: 't2i_i2v' })];
        const plan = planBatchVideoRun(shots, {
            // An I2V shot must not be judged by the R2V reference check.
            hasReferences: () => false,
            hasFirstFrame: () => false,
        });

        expect(plan.ready).toEqual([]);
        expect(plan.skipped).toEqual([
            { shot: shots[0], reason: 'missing-first-frame' },
        ]);
    });

    it('I2V 镜头有首帧就能跑，不要求参考图', () => {
        const shots = [shot('i2v', { tabMode: 't2i_i2v' })];
        const plan = planBatchVideoRun(shots, {
            hasReferences: () => false,
            hasFirstFrame: () => true,
        });

        expect(plan.ready.map((s) => s.id)).toEqual(['i2v']);
    });

    it('保持镜头原有顺序，批量按分镜顺序出片', () => {
        const shots = [shot('c'), shot('a'), shot('b')];

        const plan = planBatchVideoRun(shots, allReady);

        expect(plan.ready.map((s) => s.id)).toEqual(['c', 'a', 'b']);
    });

    it('全部都跑不了时 ready 为空，不抛错', () => {
        const shots = [shot('x', { videoUrl: 'v.mp4' })];

        const plan = planBatchVideoRun(shots, allReady);

        expect(plan.ready).toEqual([]);
        expect(plan.skipped).toHaveLength(1);
    });
});
