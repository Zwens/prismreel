'use client';

import { playgroundApi } from '@/lib/api';
import { useShotSequenceStore, inferShotMode, type Shot } from './useShotSequenceStore';
import { getModelsForMode } from '../playground/playgroundModels';

// ---------------------------------------------------------------------------
// Drives ONE shot from "generate pressed" to a terminal status.
//
// A thin, shot-scoped sibling of playground/useGenerationRunner.ts —
// deliberately not shared. That hook's queue/pump model exists to throttle
// one compose form's rapid-fire requests against maxConcurrent; here, each
// shot already IS one bounded, independently-retriable unit, and "Generate
// all" is just N calls to this function. Reusing the pump would mean routing
// N independent shots through a single-compose queue that has no notion of
// "which shot does this generation belong to."
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export interface ShotGenerationRunner {
  generateShot: (shot: Shot) => Promise<void>;
}

export interface UseShotGenerationOptions {
  /** Poll interval override for tests — production callers omit this and
   *  get POLL_INTERVAL_MS. Mirrors assetGenerationTask.ts's pollIntervalMs
   *  convention rather than faking timers. */
  pollIntervalMs?: number;
}

export function useShotGeneration(options: UseShotGenerationOptions = {}): ShotGenerationRunner {
  const pollIntervalMs = options.pollIntervalMs ?? POLL_INTERVAL_MS;
  // Imperative action, not a subscription: generateShot never needs to
  // re-render whoever called useShotGeneration() when a shot's status
  // changes elsewhere, so read setShotStatus off the vanilla store API
  // instead of subscribing via the store's React hook form.
  const setShotStatus = useShotSequenceStore.getState().setShotStatus;

  function finalize(
    shotId: string,
    status: 'completed' | 'failed',
    outputs: Array<{ media_path: string }>,
    error?: string,
  ) {
    if (status === 'failed') {
      setShotStatus(shotId, 'failed', { error: error || 'Generation failed' });
      return;
    }
    const outputPath = outputs[0]?.media_path;
    if (!outputPath) {
      setShotStatus(shotId, 'failed', { error: 'Generation completed with no output' });
      return;
    }
    setShotStatus(shotId, 'completed', { outputPath });
  }

  const generateShot = async (shot: Shot) => {
    if (!shot.prompt.trim()) return;

    setShotStatus(shot.id, 'queued');
    const mode = inferShotMode(shot);
    const modelId = getModelsForMode(mode)[0]?.id;
    if (!modelId) {
      setShotStatus(shot.id, 'failed', { error: 'No model available for this mode' });
      return;
    }

    let generationId: string;
    try {
      const resp = await playgroundApi.generate({
        mode,
        model_id: modelId,
        prompt: shot.prompt.trim(),
        input_media: shot.media.length > 0 ? shot.media : undefined,
      });
      generationId = resp.id;
      setShotStatus(shot.id, 'processing', { generationId });

      if (resp.status === 'completed' || resp.status === 'failed') {
        finalize(shot.id, resp.status, resp.outputs, resp.error);
        return;
      }
    } catch (err) {
      setShotStatus(shot.id, 'failed', { error: err instanceof Error ? err.message : String(err) });
      return;
    }

    const deadline = Date.now() + POLL_TIMEOUT_MS;
    while (Date.now() < deadline) {
      await sleep(pollIntervalMs);
      try {
        const statusResp = await playgroundApi.getGenerationStatus(generationId);
        if (statusResp.status === 'completed' || statusResp.status === 'failed') {
          const full = await playgroundApi.getGeneration(generationId);
          finalize(shot.id, full.status as 'completed' | 'failed', full.outputs, full.error);
          return;
        }
      } catch (err) {
        setShotStatus(shot.id, 'failed', { error: err instanceof Error ? err.message : String(err) });
        return;
      }
    }

    setShotStatus(shot.id, 'failed', { error: 'Generation timed out' });
  };

  return { generateShot };
}
