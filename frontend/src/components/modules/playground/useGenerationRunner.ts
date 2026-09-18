'use client';

import { useEffect, useCallback, useRef } from 'react';
import { usePlaygroundStore, usePlaygroundStoreApi, GRID_OVERLAY_NEGATIVE_PROMPT, GRID_OVERLAY_GUIDANCE_PROMPT, type PlaygroundMode, type PlaygroundGeneration, type QueuedRequest } from './usePlaygroundStore';
import { playgroundApi, type PlaygroundGenerationResponse } from '@/lib/api';

// ---------------------------------------------------------------------------
// Shared generation runner
//
// Everything between "user pressed generate" and "the result is in the store":
// initial history/template load, the client-side queue pump, the POST, and the
// status poller.
//
// Lifted out of PlaygroundPage so the standalone AI-video page can drive the
// same machinery against its own store instance. It reads the store through the
// same context-aware hooks as everything else, so which store it drives is
// decided by the provider above it — the hook itself has no idea there are two.
// ---------------------------------------------------------------------------

/** Polling interval for generation status (ms) */
const POLL_INTERVAL = 2000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert API response to store-compatible PlaygroundGeneration */
export function toGeneration(resp: PlaygroundGenerationResponse): PlaygroundGeneration {
  return {
    id: resp.id,
    mode: resp.mode as PlaygroundMode,
    model_id: resp.model_id,
    prompt: resp.prompt,
    negative_prompt: resp.negative_prompt,
    input_media: resp.input_media,
    parameters: resp.parameters,
    batch_size: resp.batch_size,
    outputs: resp.outputs.map((o) => ({
      id: o.id,
      media_path: o.media_path,
      media_type: o.media_type as 'image' | 'video',
      thumbnail_path: o.thumbnail_path,
      saved_to_library: o.saved_to_library,
      // 用量计费字段：main 的 usage tracking 依赖它们，抽出 runner 时漏掉了
      total_tokens: o.total_tokens,
      cost_usd: o.cost_usd,
    })),
    status: resp.status as PlaygroundGeneration['status'],
    error: resp.error,
    created_at: resp.created_at,
  };
}

export interface GenerationRunner {
  /** Enqueue the store's current compose state. No-op on an empty prompt. */
  generate: () => Promise<void>;
}

export function useGenerationRunner(): GenerationRunner {
  const mode = usePlaygroundStore((s) => s.mode);
  const modelId = usePlaygroundStore((s) => s.modelId);
  const prompt = usePlaygroundStore((s) => s.prompt);
  const negativePrompt = usePlaygroundStore((s) => s.negativePrompt);
  const appendGridOverlayNegative = usePlaygroundStore((s) => s.appendGridOverlayNegative);
  const inputMediaHasGridOverlay = usePlaygroundStore((s) => s.inputMediaHasGridOverlay);
  const inputMedia = usePlaygroundStore((s) => s.inputMedia);
  const parameters = usePlaygroundStore((s) => s.parameters);
  const batchSize = usePlaygroundStore((s) => s.batchSize);
  const history = usePlaygroundStore((s) => s.history);
  const setHistory = usePlaygroundStore((s) => s.setHistory);
  const setTemplates = usePlaygroundStore((s) => s.setTemplates);
  const startGeneration = usePlaygroundStore((s) => s.startGeneration);
  const updateGeneration = usePlaygroundStore((s) => s.updateGeneration);
  // The pump needs a snapshot, not a subscription: re-rendering the page on
  // every queue mutation just to read it would fight the pump it drives.
  const storeApi = usePlaygroundStoreApi();
  const enqueueRequest = usePlaygroundStore((s) => s.enqueueRequest);
  const markDispatching = usePlaygroundStore((s) => s.markDispatching);
  const removeFromQueue = usePlaygroundStore((s) => s.removeFromQueue);
  const queue = usePlaygroundStore((s) => s.queue);
  const activeCount = usePlaygroundStore((s) => s.activeGenerationIds.length);
  const maxConcurrent = usePlaygroundStore((s) => s.maxConcurrent);

  const pollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  // ─── Fetch initial data on mount ───────────────────────────────────────────

  useEffect(() => {
    playgroundApi.getHistory().then((items) => {
      setHistory(items.map(toGeneration));
    }).catch((err) => {
      console.error('[Playground] Failed to fetch history:', err);
    });

    playgroundApi.getTemplates().then((items) => {
      setTemplates(
        items.map((t) => ({
          id: t.id,
          name: t.name,
          category: t.category,
          prompt: t.prompt,
          negative_prompt: t.negative_prompt,
          default_mode: t.default_mode as PlaygroundMode | undefined,
          default_model_id: t.default_model_id,
          default_parameters: t.default_parameters,
          created_at: t.created_at,
          updated_at: t.updated_at,
        }))
      );
    }).catch((err) => {
      console.error('[Playground] Failed to fetch templates:', err);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Cleanup poll timers ───────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      pollTimers.current.forEach((timer) => clearInterval(timer));
      pollTimers.current.clear();
    };
  }, []);

  // ─── Status poller ─────────────────────────────────────────────────────────

  const startPolling = useCallback((generationId: string) => {
    // Prevent duplicate timers
    if (pollTimers.current.has(generationId)) return;

    const timer = setInterval(async () => {
      try {
        const statusResp = await playgroundApi.getGenerationStatus(generationId);
        const isTerminal = statusResp.status === 'completed' || statusResp.status === 'failed';

        // Fetch full generation data for complete update
        const fullResp = await playgroundApi.getGeneration(generationId);
        updateGeneration(toGeneration(fullResp));

        if (isTerminal) {
          clearInterval(timer);
          pollTimers.current.delete(generationId);
        }
      } catch (err) {
        console.error('[Playground] Poll failed for', generationId, err);
        clearInterval(timer);
        pollTimers.current.delete(generationId);
      }
    }, POLL_INTERVAL);

    pollTimers.current.set(generationId, timer);
  }, [updateGeneration]);

  // ─── Generate handler — enqueue a request; the dispatcher runs it ──────────

  // Grid overlays are now burned in at upload/asset-pick time (library or
  // MediaInput's "pick from library" flow) — inputMediaHasGridOverlay already
  // reflects each reference's true state by the time generate is pressed.
  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) return;
    // Auto-detect i2i: t2i + reference images -> i2i
    const effectiveMode = (mode === 't2i' && inputMedia.length > 0) ? 'i2i' : mode;
    // Grid overlay lines are baked into the pixels — leaving them out of the
    // negative prompt lets the model reproduce them in the output.
    const effectiveNegativePrompt = appendGridOverlayNegative
      ? [negativePrompt, GRID_OVERLAY_NEGATIVE_PROMPT].filter(Boolean).join(', ')
      : negativePrompt;
    // Tell the model the grid is a proportion guide, not part of the subject,
    // whenever any current reference actually carries one.
    const effectivePrompt = inputMediaHasGridOverlay.some(Boolean)
      ? `${GRID_OVERLAY_GUIDANCE_PROMPT} ${prompt.trim()}`
      : prompt.trim();
    enqueueRequest({
      mode: effectiveMode,
      modelId,
      prompt: effectivePrompt,
      negativePrompt: effectiveNegativePrompt || undefined,
      inputMedia,
      parameters,
      batchSize,
    });
  }, [mode, modelId, prompt, negativePrompt, appendGridOverlayNegative, inputMedia, inputMediaHasGridOverlay, parameters, batchSize, enqueueRequest]);

  // ─── Queue dispatcher — POST a queued request, then poll for status ────────

  const dispatchRequest = useCallback(async (req: QueuedRequest) => {
    try {
      const resp = await playgroundApi.generate({
        mode: req.mode,
        model_id: req.modelId,
        prompt: req.prompt,
        negative_prompt: req.negativePrompt || undefined,
        input_media: req.inputMedia.length > 0 ? req.inputMedia : undefined,
        parameters: Object.keys(req.parameters).length > 0 ? req.parameters : undefined,
        batch_size: req.batchSize > 1 ? req.batchSize : undefined,
      });
      const gen = toGeneration(resp);
      startGeneration(gen);
      removeFromQueue(req.id);
      if (gen.status !== 'completed' && gen.status !== 'failed') {
        startPolling(gen.id);
      }
    } catch (err) {
      console.error('[Playground] Dispatch failed:', err);
      removeFromQueue(req.id);
    }
  }, [startGeneration, removeFromQueue, startPolling]);

  // Pump: dispatch pending requests up to the concurrency limit.
  const pump = useCallback(() => {
    const s = storeApi.getState();
    const dispatching = s.queue.filter((q) => q.status === 'dispatching').length;
    let slots = s.maxConcurrent - s.activeGenerationIds.length - dispatching;
    if (slots <= 0) return;
    for (const req of s.queue) {
      if (slots <= 0) break;
      if (req.status !== 'pending') continue;
      slots -= 1;
      markDispatching(req.id);
      dispatchRequest(req);
    }
  }, [markDispatching, dispatchRequest, storeApi]);

  // Run the pump whenever the queue, in-flight count, or concurrency changes.
  useEffect(() => {
    pump();
  }, [queue, activeCount, maxConcurrent, pump]);

  return { generate: handleGenerate };
}
