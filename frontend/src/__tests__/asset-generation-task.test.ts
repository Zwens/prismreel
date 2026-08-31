/**
 * Tests for submitAssetGeneration — the single-asset submit path shared by
 * the workbench modal and the Cast batch button.
 *
 * The batch queue's concurrency ceiling is only real if a queued task stays
 * "in flight" until the asset has actually finished generating. The modal
 * fires the poll and forgets it, which is fine for one asset but would let a
 * batch submit every asset at once. Hence: the returned promise must settle
 * on the poll's terminal state, not on the submit response.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const generateAsset = vi.fn();
const getTaskStatus = vi.fn();
const getProject = vi.fn();

vi.mock('@/lib/api', () => ({
    api: {
        generateAsset: (...args: unknown[]) => generateAsset(...args),
        getTaskStatus: (...args: unknown[]) => getTaskStatus(...args),
        getProject: (...args: unknown[]) => getProject(...args),
    },
}));

vi.mock('@/store/toastStore', () => ({
    toast: {
        progress: vi.fn(() => 'toast-1'),
        dismiss: vi.fn(),
        success: vi.fn(),
        error: vi.fn(),
        warning: vi.fn(),
    },
}));

import { submitAssetGeneration, activePolls } from '@/lib/assetGenerationTask';

const store = {
    updateProject: vi.fn(),
    addGeneratingTask: vi.fn(),
    removeGeneratingTask: vi.fn(),
};

function params(overrides: Record<string, unknown> = {}) {
    return {
        projectId: 'proj-1',
        entityId: 'char-1',
        kind: 'character' as const,
        prompt: '张启山，硬朗',
        stylePreset: 'realistic',
        stylePositive: 'cinematic',
        negativePrompt: 'text, watermark',
        applyStyle: true,
        batchSize: 1,
        t: (key: string) => key,
        getStore: () => store,
        pollIntervalMs: 5,
        ...overrides,
    };
}

beforeEach(() => {
    activePolls.forEach((interval) => clearInterval(interval));
    activePolls.clear();
    vi.clearAllMocks();
    getProject.mockResolvedValue({ id: 'proj-1', characters: [], scenes: [], props: [] });
});

describe('submitAssetGeneration', () => {
    it('等到轮询报告完成后才 resolve，而不是提交返回就 resolve', async () => {
        generateAsset.mockResolvedValue({ _task_id: 'task-1' });
        let polls = 0;
        getTaskStatus.mockImplementation(async () => {
            polls += 1;
            return { status: polls < 3 ? 'processing' : 'completed' };
        });

        let settled = false;
        const promise = submitAssetGeneration(params()).then(() => { settled = true; });

        expect(settled).toBe(false);
        await promise;
        expect(settled).toBe(true);
        expect(polls).toBe(3);
    });

    it('后端报告失败时 reject，让批量把它计为失败', async () => {
        generateAsset.mockResolvedValue({ _task_id: 'task-1' });
        getTaskStatus.mockResolvedValue({ status: 'failed', error: '模型拒绝了该提示词' });

        await expect(submitAssetGeneration(params())).rejects.toThrow('模型拒绝了该提示词');
    });

    it('提交本身失败时 reject 并清掉生成中状态', async () => {
        generateAsset.mockRejectedValue(new Error('network down'));

        await expect(submitAssetGeneration(params())).rejects.toThrow('network down');
        expect(store.removeGeneratingTask).toHaveBeenCalledWith('char-1', 'reference_sheet');
    });

    it('同步返回结果（无 task_id）时直接 resolve', async () => {
        generateAsset.mockResolvedValue({ id: 'proj-1', characters: [] });

        await submitAssetGeneration(params());

        expect(getTaskStatus).not.toHaveBeenCalled();
        expect(store.updateProject).toHaveBeenCalled();
    });

    it('场景与道具用 all 作为 generationType，角色用 reference_sheet', async () => {
        generateAsset.mockResolvedValue({ id: 'proj-1' });

        await submitAssetGeneration(params({ kind: 'scene', entityId: 'scene-1' }));

        expect(store.addGeneratingTask).toHaveBeenCalledWith('scene-1', 'all', 1);
    });
});
