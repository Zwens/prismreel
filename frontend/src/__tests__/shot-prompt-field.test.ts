/**
 * The shot prompt lives in one of two frame fields, and reader and writer
 * must agree on which.
 *
 * frameToShotNode read `visual_description || action_description` while every
 * edit was persisted to `action_description`. For a frame that had a
 * visual_description — 10 of EP.02's 13 — the write was therefore invisible:
 * reference tags vanished on reload, and so did any prompt the user typed by
 * hand. One function now decides the field, and both sides call it.
 */
import { describe, it, expect } from 'vitest';
import { shotPromptField, readShotPrompt } from '@/components/modules/storyboard-r2v/shotNodeHelpers';

describe('shotPromptField', () => {
    it('有 visual_description 时以它为准', () => {
        const frame = { visual_description: '润色后的画面描述', action_description: '粗描述' };

        expect(shotPromptField(frame)).toBe('visual_description');
    });

    it('没有 visual_description 时落到 action_description', () => {
        const frame = { action_description: '粗描述' };

        expect(shotPromptField(frame)).toBe('action_description');
    });

    it('visual_description 为空字符串时不算数', () => {
        const frame = { visual_description: '', action_description: '粗描述' };

        expect(shotPromptField(frame)).toBe('action_description');
    });

    it('两个都没有时仍返回 action_description，作为写入落点', () => {
        expect(shotPromptField({})).toBe('action_description');
    });
});

describe('readShotPrompt', () => {
    it('读的正是 shotPromptField 指定的那个字段', () => {
        const withVisual = { visual_description: 'A', action_description: 'B' };
        const withoutVisual = { action_description: 'B' };

        expect(readShotPrompt(withVisual)).toBe('A');
        expect(readShotPrompt(withoutVisual)).toBe('B');
    });

    it('两个字段都缺时返回空串', () => {
        expect(readShotPrompt({})).toBe('');
    });

    it('对任意 frame，读到的内容等于写入字段里的内容 —— 读写闭环', () => {
        // The property that was broken: writing through the chosen field and
        // reading back must round-trip.
        for (const frame of [
            { visual_description: 'v', action_description: 'a' },
            { action_description: 'a' },
            { visual_description: 'v' },
        ] as any[]) {
            const field = shotPromptField(frame);
            const next = { ...frame, [field]: '新写入的提示词' };
            expect(readShotPrompt(next)).toBe('新写入的提示词');
        }
    });
});
