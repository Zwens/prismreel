'use client';

import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Shot sequence store — the multi-shot video workflow's own state.
//
// Deliberately independent of usePlaygroundStore: that store models one
// compose form (single mode/prompt/media), and its queue/pump machinery
// assumes one active request stream. A shot sequence is N independently
// retriable units, so this store keeps its own array instead of forcing
// that shape into the single-compose model.
// ---------------------------------------------------------------------------

export const MAX_SHOTS = 10;

export type ShotStatus = 'idle' | 'queued' | 'processing' | 'completed' | 'failed';

export interface Shot {
  id: string;
  prompt: string;
  media: string[];
  mediaType: 'image' | 'video' | null;
  status: ShotStatus;
  generationId?: string;
  outputPath?: string;
  error?: string;
}

/** Mode inference precedence: a video attachment always wins (v2v ignores
 *  extra images by design — see design doc's mode-inference table). */
export function inferShotMode(
  shot: Pick<Shot, 'media' | 'mediaType'>,
): 'r2v' | 'i2v' | 'v2v' | 't2v' {
  if (shot.mediaType === 'video') return 'v2v';
  if (shot.media.length >= 2) return 'r2v';
  if (shot.media.length === 1) return 'i2v';
  return 't2v';
}

function makeEmptyShot(): Shot {
  return {
    id: crypto.randomUUID(),
    prompt: '',
    media: [],
    mediaType: null,
    status: 'idle',
  };
}

export interface ShotSequenceState {
  shots: Shot[];
  addShot: (atIndex?: number) => void;
  removeShot: (id: string) => void;
  moveShot: (id: string, toIndex: number) => void;
  updateShotPrompt: (id: string, prompt: string) => void;
  setShotMedia: (id: string, media: string[], mediaType: 'image' | 'video' | null) => void;
  setShotStatus: (
    id: string,
    status: ShotStatus,
    patch?: Partial<Pick<Shot, 'generationId' | 'outputPath' | 'error'>>,
  ) => void;
  reset: () => void;
}

export const useShotSequenceStore = create<ShotSequenceState>((set, get) => ({
  shots: [makeEmptyShot()],

  addShot: (atIndex) => {
    const { shots } = get();
    if (shots.length >= MAX_SHOTS) return;
    const next = [...shots];
    const insertAt = atIndex === undefined ? next.length : Math.max(0, Math.min(atIndex, next.length));
    next.splice(insertAt, 0, makeEmptyShot());
    set({ shots: next });
  },

  removeShot: (id) => {
    set({ shots: get().shots.filter((s) => s.id !== id) });
  },

  moveShot: (id, toIndex) => {
    const shots = [...get().shots];
    const fromIndex = shots.findIndex((s) => s.id === id);
    if (fromIndex === -1) return;
    const [moved] = shots.splice(fromIndex, 1);
    const clampedTo = Math.max(0, Math.min(toIndex, shots.length));
    shots.splice(clampedTo, 0, moved);
    set({ shots });
  },

  updateShotPrompt: (id, prompt) => {
    set({ shots: get().shots.map((s) => (s.id === id ? { ...s, prompt } : s)) });
  },

  setShotMedia: (id, media, mediaType) => {
    set({ shots: get().shots.map((s) => (s.id === id ? { ...s, media, mediaType } : s)) });
  },

  setShotStatus: (id, status, patch) => {
    set({
      shots: get().shots.map((s) => (s.id === id ? { ...s, status, ...patch } : s)),
    });
  },

  reset: () => set({ shots: [makeEmptyShot()] }),
}));
