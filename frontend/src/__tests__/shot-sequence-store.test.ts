import { describe, it, expect, beforeEach } from 'vitest';
import { inferShotMode, useShotSequenceStore, MAX_SHOTS } from '@/components/modules/videoworkflow/useShotSequenceStore';

describe('inferShotMode', () => {
  it('returns t2v for no media', () => {
    expect(inferShotMode({ media: [], mediaType: null })).toBe('t2v');
  });

  it('returns i2v for exactly one image', () => {
    expect(inferShotMode({ media: ['a.png'], mediaType: 'image' })).toBe('i2v');
  });

  it('returns r2v for two or more images', () => {
    expect(inferShotMode({ media: ['a.png', 'b.png'], mediaType: 'image' })).toBe('r2v');
    expect(inferShotMode({ media: ['a.png', 'b.png', 'c.png'], mediaType: 'image' })).toBe('r2v');
  });

  it('returns v2v when mediaType is video, regardless of media array length', () => {
    expect(inferShotMode({ media: ['a.mp4'], mediaType: 'video' })).toBe('v2v');
  });
});

describe('useShotSequenceStore', () => {
  beforeEach(() => {
    useShotSequenceStore.getState().reset();
  });

  it('starts with one empty shot', () => {
    expect(useShotSequenceStore.getState().shots).toHaveLength(1);
    expect(useShotSequenceStore.getState().shots[0].status).toBe('idle');
  });

  it('addShot appends by default', () => {
    useShotSequenceStore.getState().addShot();
    expect(useShotSequenceStore.getState().shots).toHaveLength(2);
  });

  it('addShot inserts at the given index', () => {
    const { addShot } = useShotSequenceStore.getState();
    addShot(); // now 2 shots, indices 0,1
    const firstId = useShotSequenceStore.getState().shots[0].id;
    const secondId = useShotSequenceStore.getState().shots[1].id;
    addShot(1); // insert between them
    const ids = useShotSequenceStore.getState().shots.map((s) => s.id);
    expect(ids[0]).toBe(firstId);
    expect(ids[2]).toBe(secondId);
    expect(ids).toHaveLength(3);
  });

  it('addShot is a no-op at MAX_SHOTS', () => {
    const { addShot } = useShotSequenceStore.getState();
    for (let i = 0; i < MAX_SHOTS + 5; i++) addShot();
    expect(useShotSequenceStore.getState().shots.length).toBe(MAX_SHOTS);
  });

  it('removeShot removes by id', () => {
    const { addShot, removeShot } = useShotSequenceStore.getState();
    addShot();
    const idToRemove = useShotSequenceStore.getState().shots[0].id;
    removeShot(idToRemove);
    expect(useShotSequenceStore.getState().shots.find((s) => s.id === idToRemove)).toBeUndefined();
  });

  it('moveShot reorders', () => {
    const { addShot, moveShot } = useShotSequenceStore.getState();
    addShot();
    addShot();
    const ids = useShotSequenceStore.getState().shots.map((s) => s.id);
    moveShot(ids[0], 2);
    const newIds = useShotSequenceStore.getState().shots.map((s) => s.id);
    expect(newIds).toEqual([ids[1], ids[2], ids[0]]);
  });

  it('updateShotPrompt and setShotMedia update the right shot only', () => {
    const { addShot, updateShotPrompt, setShotMedia } = useShotSequenceStore.getState();
    addShot();
    const [firstId, secondId] = useShotSequenceStore.getState().shots.map((s) => s.id);
    updateShotPrompt(firstId, 'a cat walking');
    setShotMedia(secondId, ['x.png', 'y.png'], 'image');

    const shots = useShotSequenceStore.getState().shots;
    expect(shots.find((s) => s.id === firstId)!.prompt).toBe('a cat walking');
    expect(shots.find((s) => s.id === secondId)!.media).toEqual(['x.png', 'y.png']);
    expect(shots.find((s) => s.id === firstId)!.media).toEqual([]);
  });

  it('setShotStatus patches status and extra fields', () => {
    const { setShotStatus } = useShotSequenceStore.getState();
    const id = useShotSequenceStore.getState().shots[0].id;
    setShotStatus(id, 'completed', { outputPath: 'playground/videos/out.mp4' });
    const shot = useShotSequenceStore.getState().shots.find((s) => s.id === id)!;
    expect(shot.status).toBe('completed');
    expect(shot.outputPath).toBe('playground/videos/out.mp4');
  });
});
