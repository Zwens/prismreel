/**
 * Tests for useShotGeneration.generateShot — drives ONE shot from "generate
 * pressed" to a terminal status (completed/failed), writing progress back
 * into useShotSequenceStore via setShotStatus.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const generate = vi.fn();
const getGenerationStatus = vi.fn();
const getGeneration = vi.fn();

vi.mock('@/lib/api', () => ({
  playgroundApi: {
    generate: (...args: unknown[]) => generate(...args),
    getGenerationStatus: (...args: unknown[]) => getGenerationStatus(...args),
    getGeneration: (...args: unknown[]) => getGeneration(...args),
  },
}));

import { useShotSequenceStore } from '@/components/modules/videoworkflow/useShotSequenceStore';
import { useShotGeneration } from '@/components/modules/videoworkflow/useShotGeneration';

function makeResponse(overrides: Partial<any> = {}) {
  return {
    id: 'gen-1',
    mode: 'i2v',
    model_id: 'model-x',
    prompt: 'a cat',
    negative_prompt: undefined,
    input_media: ['a.png'],
    parameters: {},
    batch_size: 1,
    outputs: [],
    status: 'processing',
    error: undefined,
    created_at: '2026-09-18T00:00:00Z',
    ...overrides,
  };
}

describe('useShotGeneration.generateShot', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useShotSequenceStore.getState().reset();
  });

  it('is a no-op on an empty prompt', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    const { generateShot } = useShotGeneration();

    await generateShot(shot);

    expect(generate).not.toHaveBeenCalled();
    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('idle');
  });

  it('marks the shot processing, then completed with the output path on success', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    useShotSequenceStore.getState().updateShotPrompt(shot.id, 'a cat walking');
    useShotSequenceStore.getState().setShotMedia(shot.id, ['a.png'], 'image');

    generate.mockResolvedValue(makeResponse({ status: 'processing' }));
    getGenerationStatus.mockResolvedValue({ id: 'gen-1', status: 'completed', outputs: [], error: undefined });
    getGeneration.mockResolvedValue(
      makeResponse({
        status: 'completed',
        outputs: [{ id: 'out-1', media_path: 'playground/videos/out.mp4', media_type: 'video', saved_to_library: false }],
      }),
    );

    const { generateShot } = useShotGeneration({ pollIntervalMs: 5 });
    const updatedShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    await generateShot(updatedShot);

    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('completed');
    expect(finalShot.outputPath).toBe('playground/videos/out.mp4');
    expect(generate).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'i2v', prompt: 'a cat walking', input_media: ['a.png'] }),
    );
  });

  it('marks the shot completed immediately when generate() resolves already-terminal', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    useShotSequenceStore.getState().updateShotPrompt(shot.id, 'a fast cat');

    generate.mockResolvedValue(
      makeResponse({
        status: 'completed',
        outputs: [{ id: 'out-1', media_path: 'playground/videos/fast.mp4', media_type: 'video', saved_to_library: false }],
      }),
    );

    const { generateShot } = useShotGeneration();
    const updatedShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    await generateShot(updatedShot);

    expect(getGenerationStatus).not.toHaveBeenCalled();
    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('completed');
    expect(finalShot.outputPath).toBe('playground/videos/fast.mp4');
  });

  it('marks the shot failed with the error message when generate rejects', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    useShotSequenceStore.getState().updateShotPrompt(shot.id, 'a dog running');

    generate.mockRejectedValue(new Error('quota exceeded'));

    const { generateShot } = useShotGeneration();
    const updatedShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    await generateShot(updatedShot);

    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('failed');
    expect(finalShot.error).toContain('quota exceeded');
  });

  it('marks the shot failed when the generation itself reaches status failed via polling', async () => {
    const shot = useShotSequenceStore.getState().shots[0];
    useShotSequenceStore.getState().updateShotPrompt(shot.id, 'a bird flying');

    generate.mockResolvedValue(makeResponse({ status: 'processing' }));
    getGenerationStatus.mockResolvedValue({ id: 'gen-1', status: 'failed', outputs: [], error: 'model error' });
    getGeneration.mockResolvedValue(makeResponse({ status: 'failed', error: 'model error' }));

    const { generateShot } = useShotGeneration({ pollIntervalMs: 5 });
    const updatedShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    await generateShot(updatedShot);

    const finalShot = useShotSequenceStore.getState().shots.find((s) => s.id === shot.id)!;
    expect(finalShot.status).toBe('failed');
    expect(finalShot.error).toBe('model error');
  });
});
