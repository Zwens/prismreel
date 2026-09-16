'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  playgroundApi,
  type PlaygroundDepthCapability,
  type PlaygroundDepthJob,
  type PlaygroundGenerationResponse,
} from '@/lib/api';
import { buildComposePrompt, buildOutfitOnlyPrompt, buildThreeViewPrompt, type SheetStyle } from './prompts';

// ---------------------------------------------------------------------------
// The three-step dance-swap flow.
//
// Deliberately NOT wired through the shared playground compose state / queue:
// each step here has its own inputs, its own artifact and its own retry, and
// stuffing that through a single-slot "current prompt + current media" store
// would make step 2 clobber step 1. The generations still go through the normal
// /playground/generate endpoint, so history, cost tracking and save-to-library
// all keep working.
// ---------------------------------------------------------------------------

const POLL_MS = 2000;
const DEPTH_POLL_MS = 1000;

/** Gemini image model used for the character sheet. */
const SHEET_MODEL = 'gemini-3-pro-image';
/** The only model that takes reference images and a reference video together. */
const COMPOSE_MODEL = 'seedance-2.5-v2v';

export type StepState = 'idle' | 'running' | 'done' | 'error';

export interface StepResult {
  generationId: string;
  outputId: string;
  mediaPath: string;
  mediaType: 'image' | 'video';
}

export interface DanceSwapState {
  // step 1 — character sheet
  portraitPath: string | null;
  outfitRefPath: string | null;
  outfit: string;
  sheetStyle: SheetStyle;
  sheetState: StepState;
  sheetError: string | null;
  sheet: StepResult | null;

  // step 2 — motion reference
  danceVideoPath: string | null;
  depthCapability: PlaygroundDepthCapability | null;
  depthJob: PlaygroundDepthJob | null;
  depthState: StepState;
  depthError: string | null;
  maxSeconds: number | null;
  targetFps: number | null;

  // step 3 — compose
  scene: string;
  composePrompt: string;
  composePromptDirty: boolean;
  useSheet: boolean;
  resolution: string;
  composeState: StepState;
  composeError: string | null;
  composed: StepResult | null;
}

const INITIAL: DanceSwapState = {
  portraitPath: null,
  outfitRefPath: null,
  outfit: '',
  sheetStyle: 'illustration',
  sheetState: 'idle',
  sheetError: null,
  sheet: null,

  danceVideoPath: null,
  depthCapability: null,
  depthJob: null,
  depthState: 'idle',
  depthError: null,
  maxSeconds: null,
  targetFps: null,

  scene: '',
  composePrompt: '',
  composePromptDirty: false,
  useSheet: true,
  resolution: '720p',
  composeState: 'idle',
  composeError: null,
  composed: null,
};

/** Turn an API error into something worth showing.
 *
 * Vendor moderation rejections arrive as a FastAPI 500 whose detail carries
 * Ark's own message. That message is the single most useful thing the user can
 * see here (it names which input was rejected and why), so it is surfaced
 * verbatim rather than replaced with a generic failure string.
 */
function describeError(err: unknown): string {
  const anyErr = err as { response?: { data?: { detail?: string } }; message?: string };
  return anyErr?.response?.data?.detail || anyErr?.message || String(err);
}

function firstOutput(gen: PlaygroundGenerationResponse): StepResult | null {
  const out = gen.outputs?.[0];
  if (!out) return null;
  return {
    generationId: gen.id,
    outputId: out.id,
    mediaPath: out.media_path,
    mediaType: out.media_type as 'image' | 'video',
  };
}

export function useDanceSwap() {
  const [state, setState] = useState<DanceSwapState>(INITIAL);
  const pollers = useRef<Set<ReturnType<typeof setInterval>>>(new Set());

  const patch = useCallback((p: Partial<DanceSwapState>) => {
    setState((s) => ({ ...s, ...p }));
  }, []);

  // Clear every poller on unmount — a wizard left mid-run otherwise keeps
  // hitting the backend for the rest of the session.
  useEffect(() => {
    const active = pollers.current;
    return () => {
      active.forEach(clearInterval);
      active.clear();
    };
  }, []);

  // -- capability probe -------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    playgroundApi
      .getDepthCapability()
      .then((cap) => {
        if (!cancelled) patch({ depthCapability: cap });
      })
      .catch(() => {
        /* the UI degrades to "unknown hardware", which is fine */
      });
    return () => {
      cancelled = true;
    };
  }, [patch]);

  // -- shared: run a generation and wait for it -------------------------

  const runGeneration = useCallback(
    (body: Parameters<typeof playgroundApi.generate>[0]): Promise<PlaygroundGenerationResponse> =>
      playgroundApi.generate(body).then(
        (gen) =>
          new Promise<PlaygroundGenerationResponse>((resolve, reject) => {
            const timer = setInterval(async () => {
              try {
                const status = await playgroundApi.getGenerationStatus(gen.id);
                if (status.status === 'completed') {
                  clearInterval(timer);
                  pollers.current.delete(timer);
                  resolve(await playgroundApi.getGeneration(gen.id));
                } else if (status.status === 'failed') {
                  clearInterval(timer);
                  pollers.current.delete(timer);
                  reject(new Error(status.error || '生成失败'));
                }
              } catch (err) {
                clearInterval(timer);
                pollers.current.delete(timer);
                reject(err);
              }
            }, POLL_MS);
            pollers.current.add(timer);
          }),
      ),
    [],
  );

  // -- step 1 -----------------------------------------------------------

  const uploadPortrait = useCallback(
    (file: File) => playgroundApi.uploadMedia(file).then((r) => patch({ portraitPath: r.path })),
    [patch],
  );

  const uploadOutfitRef = useCallback(
    (file: File) => playgroundApi.uploadMedia(file).then((r) => patch({ outfitRefPath: r.path })),
    [patch],
  );

  const generateSheet = useCallback(async () => {
    if (!state.portraitPath) return;
    patch({ sheetState: 'running', sheetError: null });
    try {
      const refs = [state.portraitPath, state.outfitRefPath].filter(Boolean) as string[];
      const gen = await runGeneration({
        mode: 'i2i',
        model_id: SHEET_MODEL,
        prompt: buildThreeViewPrompt(state.outfit, state.sheetStyle),
        input_media: refs,
        // Landscape so three full-body views sit side by side without being
        // squeezed. Note the separator: size_to_aspect_ratio parses "W*H" and
        // silently falls back to 1:1 on anything else, which crops a full-body
        // sheet off at the feet.
        parameters: { size: '1536*1024' },
        batch_size: 1,
      });
      patch({ sheetState: 'done', sheet: firstOutput(gen) });
    } catch (err) {
      patch({ sheetState: 'error', sheetError: describeError(err) });
    }
  }, [state.portraitPath, state.outfitRefPath, state.outfit, state.sheetStyle, patch, runGeneration]);

  // -- step 2 -----------------------------------------------------------

  const uploadDanceVideo = useCallback(
    (file: File) =>
      playgroundApi.uploadVideo(file).then((r) => patch({ danceVideoPath: r.path, depthJob: null, depthState: 'idle' })),
    [patch],
  );

  const generateDepth = useCallback(async () => {
    if (!state.danceVideoPath) return;
    patch({ depthState: 'running', depthError: null });
    try {
      const job = await playgroundApi.createDepthJob({
        source_video: state.danceVideoPath,
        encoder: 'auto',
        max_seconds: state.maxSeconds ?? undefined,
        target_fps: state.targetFps ?? undefined,
      });
      patch({ depthJob: job });

      const timer = setInterval(async () => {
        try {
          const latest = await playgroundApi.getDepthJob(job.id);
          patch({ depthJob: latest });
          if (latest.status === 'completed') {
            clearInterval(timer);
            pollers.current.delete(timer);
            patch({ depthState: 'done' });
          } else if (latest.status === 'failed') {
            clearInterval(timer);
            pollers.current.delete(timer);
            patch({ depthState: 'error', depthError: latest.error || '深度视频生成失败' });
          }
        } catch (err) {
          clearInterval(timer);
          pollers.current.delete(timer);
          patch({ depthState: 'error', depthError: describeError(err) });
        }
      }, DEPTH_POLL_MS);
      pollers.current.add(timer);
    } catch (err) {
      patch({ depthState: 'error', depthError: describeError(err) });
    }
  }, [state.danceVideoPath, state.maxSeconds, state.targetFps, patch]);

  // -- step 3 -----------------------------------------------------------

  /** The prompt the compose step will send, unless the user has edited it. */
  const suggestedPrompt = state.useSheet && state.sheet
    ? buildComposePrompt({ outfit: state.outfit, scene: state.scene, hasSheet: true })
    : buildOutfitOnlyPrompt({ outfit: state.outfit, scene: state.scene });

  const effectivePrompt = state.composePromptDirty ? state.composePrompt : suggestedPrompt;

  const compose = useCallback(async () => {
    const motion = state.depthJob?.output_path || state.danceVideoPath;
    if (!motion) return;

    patch({ composeState: 'running', composeError: null });
    try {
      // input_media[0] is the motion clip; anything after it is a reference
      // image. That ordering is the contract the v2v backend path expects.
      const media = [motion];
      if (state.useSheet && state.sheet) media.push(state.sheet.mediaPath);

      const gen = await runGeneration({
        mode: 'v2v',
        model_id: COMPOSE_MODEL,
        prompt: effectivePrompt,
        input_media: media,
        parameters: {
          task_type: 'reference',
          resolution: state.resolution,
          // 'reference' is the one omni sub-type with no ratio/duration
          // constraint, so the output can simply follow the source clip.
          aspect_ratio: 'adaptive',
        },
        batch_size: 1,
      });
      patch({ composeState: 'done', composed: firstOutput(gen) });
    } catch (err) {
      patch({ composeState: 'error', composeError: describeError(err) });
    }
  }, [
    state.depthJob, state.danceVideoPath, state.useSheet, state.sheet,
    state.resolution, effectivePrompt, patch, runGeneration,
  ]);

  // -- library ----------------------------------------------------------

  const saveToLibrary = useCallback(
    (result: StepResult, category: string) =>
      playgroundApi.saveToLibrary(result.generationId, result.outputId, category),
    [],
  );

  const reset = useCallback(() => setState(INITIAL), []);

  return {
    state,
    patch,
    effectivePrompt,
    suggestedPrompt,
    actions: {
      uploadPortrait,
      uploadOutfitRef,
      generateSheet,
      uploadDanceVideo,
      generateDepth,
      compose,
      saveToLibrary,
      reset,
    },
  };
}
