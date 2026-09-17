'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api,
  playgroundApi,
  type PlaygroundDepthCapability,
  type PlaygroundDepthJob,
  type PlaygroundGenerationResponse,
} from '@/lib/api';
import { buildComposePrompt, buildOutfitOnlyPrompt, buildThreeViewPrompt, type SheetStyle } from './prompts';
import type { GridOverlaySize } from '@/components/shared/GridOverlayPicker';
import { GRID_OVERLAY_NEGATIVE_PROMPT, GRID_OVERLAY_GUIDANCE_PROMPT } from '../usePlaygroundStore';

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
  /** 'generate': AI creates the three-view sheet from the uploaded portrait.
   *  'upload': the user already has a three-view sheet, skip generation and
   *  use the uploaded image directly. */
  sheetSource: 'generate' | 'upload';
  portraitPath: string | null;
  outfitRefPath: string | null;
  outfit: string;
  sheetStyle: SheetStyle;
  sheetState: StepState;
  sheetError: string | null;
  sheet: StepResult | null;
  /** True once any of the step-1 inputs the sheet was built from carries a
   *  baked-in grid overlay — drives the step-3 "exclude grid lines" checkbox. */
  sheetHasGridOverlay: boolean;
  /** Checkbox state — whether GRID_OVERLAY_NEGATIVE_PROMPT is appended to the
   *  compose prompt. Auto-set to true the moment sheetHasGridOverlay flips on. */
  appendGridOverlayNegative: boolean;

  // step 2 — motion reference
  /** 'extract': server runs depth extraction on the uploaded clip (needs a
   *  GPU). 'upload': the uploaded clip already IS the depth/motion video,
   *  skip extraction and feed it straight to compose. */
  motionSource: 'extract' | 'upload';
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
  /** 'adaptive' follows the motion clip's own ratio; anything else is an
   *  explicit override. task_type 'reference' has no ratio constraint, so
   *  the request can safely carry whatever the user picks here. */
  aspectRatio: string;
  /** Seconds, or null to follow the motion clip's own length (sent as -1). */
  duration: number | null;
  composeState: StepState;
  composeError: string | null;
  composed: StepResult | null;
}

const INITIAL: DanceSwapState = {
  sheetSource: 'generate',
  portraitPath: null,
  outfitRefPath: null,
  outfit: '',
  sheetStyle: 'illustration',
  sheetState: 'idle',
  sheetError: null,
  sheet: null,
  sheetHasGridOverlay: false,
  appendGridOverlayNegative: false,

  motionSource: 'extract',
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
  aspectRatio: 'adaptive',
  duration: null,
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
                  reject(new Error(status.error || '生成失敗'));
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
    (file: File, gridSize: GridOverlaySize = 0) =>
      playgroundApi.uploadMedia(file, gridSize).then((r) =>
        patch({
          portraitPath: r.path,
          sheetHasGridOverlay: gridSize > 0 || state.sheetHasGridOverlay,
          appendGridOverlayNegative: gridSize > 0 ? true : state.appendGridOverlayNegative,
        }),
      ),
    [patch, state.sheetHasGridOverlay, state.appendGridOverlayNegative],
  );

  const uploadOutfitRef = useCallback(
    (file: File, gridSize: GridOverlaySize = 0) =>
      playgroundApi.uploadMedia(file, gridSize).then((r) =>
        patch({
          outfitRefPath: r.path,
          sheetHasGridOverlay: gridSize > 0 || state.sheetHasGridOverlay,
          appendGridOverlayNegative: gridSize > 0 ? true : state.appendGridOverlayNegative,
        }),
      ),
    [patch, state.sheetHasGridOverlay, state.appendGridOverlayNegative],
  );

  const generateSheet = useCallback(async (gridSize: GridOverlaySize = 0) => {
    if (!state.portraitPath) return;
    patch({ sheetState: 'running', sheetError: null });
    try {
      const refs = [state.portraitPath, state.outfitRefPath].filter(Boolean) as string[];
      const gen = await runGeneration({
        mode: 'i2i',
        model_id: SHEET_MODEL,
        prompt: buildThreeViewPrompt(state.outfit, state.sheetStyle, gridSize > 0),
        input_media: refs,
        // Landscape so three full-body views sit side by side without being
        // squeezed. Note the separator: size_to_aspect_ratio parses "W*H" and
        // silently falls back to 1:1 on anything else, which crops a full-body
        // sheet off at the feet.
        parameters: { size: '1536*1024' },
        batch_size: 1,
      });
      const result = firstOutput(gen);
      // The user asked for a grid on the sheet itself — burn it into the
      // freshly generated image the same way an upload would carry one in,
      // so the checkbox below (and downstream consumers) see it consistently.
      if (result && gridSize > 0) {
        await playgroundApi.applyGridToMedia(result.mediaPath, gridSize);
      }
      patch({
        sheetState: 'done',
        sheet: result,
        useSheet: true,
        sheetHasGridOverlay: gridSize > 0,
        appendGridOverlayNegative: gridSize > 0 ? true : state.appendGridOverlayNegative,
      });
    } catch (err) {
      patch({ sheetState: 'error', sheetError: describeError(err) });
    }
  }, [state.portraitPath, state.outfitRefPath, state.outfit, state.sheetStyle, state.appendGridOverlayNegative, patch, runGeneration]);

  /** 'upload' mode: the user already has a three-view sheet. There's no
   *  generation behind it, so generationId/outputId are empty — saveToLibrary
   *  branches on that to skip the history-lookup save path. */
  const uploadSheet = useCallback(
    (file: File, gridSize: GridOverlaySize = 0) =>
      playgroundApi.uploadMedia(file, gridSize).then((r) =>
        patch({
          sheetState: 'done',
          sheetError: null,
          sheet: { generationId: '', outputId: '', mediaPath: r.path, mediaType: 'image' },
          useSheet: true,
          sheetHasGridOverlay: gridSize > 0,
          appendGridOverlayNegative: gridSize > 0 ? true : state.appendGridOverlayNegative,
        }),
      ),
    [patch, state.appendGridOverlayNegative],
  );

  /** Same as uploadSheet, but the path comes from AssetSourcePicker (library /
   *  series / project / history / official) instead of a fresh file upload —
   *  the asset already lives on the server, but a requested grid still needs
   *  to be burned in server-side (the source asset itself has no grid). */
  const pickSheet = useCallback(
    (path: string, gridSize: GridOverlaySize = 0) => {
      const apply = gridSize > 0
        ? playgroundApi.applyGridToMedia(path, gridSize)
        : Promise.resolve(null);
      return apply.then(() =>
        patch({
          sheetState: 'done',
          sheetError: null,
          sheet: { generationId: '', outputId: '', mediaPath: path, mediaType: 'image' },
          useSheet: true,
          sheetHasGridOverlay: gridSize > 0,
          appendGridOverlayNegative: gridSize > 0 ? true : state.appendGridOverlayNegative,
        }),
      );
    },
    [patch, state.appendGridOverlayNegative],
  );

  // -- step 2 -----------------------------------------------------------

  const uploadDanceVideo = useCallback(
    (file: File) =>
      playgroundApi.uploadVideo(file).then((r) =>
        patch({
          danceVideoPath: r.path,
          depthJob: null,
          // In 'upload' mode the clip already IS the motion video — no
          // extraction to run, so it's ready as soon as it lands.
          depthState: state.motionSource === 'upload' ? 'done' : 'idle',
        }),
      ),
    [patch, state.motionSource],
  );

  /** Same as uploadDanceVideo's 'upload' path, but the clip comes from
   *  AssetSourcePicker instead of a fresh file upload. */
  const pickDanceVideo = useCallback(
    (path: string) =>
      patch({ danceVideoPath: path, depthJob: null, depthState: 'done' }),
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
            patch({ depthState: 'error', depthError: latest.error || '深度影片生成失敗' });
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
      const sheetInComposition = state.useSheet && state.sheet;
      if (sheetInComposition) media.push(state.sheet!.mediaPath);

      // The sheet may carry a baked-in grid overlay (see step 1) — tell the
      // model how to read it and, unless the user unticked the checkbox,
      // keep the grid lines themselves out of the rendered output.
      const gridActive = sheetInComposition && state.sheetHasGridOverlay;
      const finalPrompt = gridActive
        ? `${GRID_OVERLAY_GUIDANCE_PROMPT} ${effectivePrompt}`
        : effectivePrompt;

      const gen = await runGeneration({
        mode: 'v2v',
        model_id: COMPOSE_MODEL,
        prompt: finalPrompt,
        negative_prompt: gridActive && state.appendGridOverlayNegative ? GRID_OVERLAY_NEGATIVE_PROMPT : undefined,
        input_media: media,
        parameters: {
          task_type: 'reference',
          resolution: state.resolution,
          aspect_ratio: state.aspectRatio,
          duration: state.duration ?? -1,
        },
        batch_size: 1,
      });
      patch({ composeState: 'done', composed: firstOutput(gen) });
    } catch (err) {
      patch({ composeState: 'error', composeError: describeError(err) });
    }
  }, [
    state.depthJob, state.danceVideoPath, state.useSheet, state.sheet, state.sheetHasGridOverlay,
    state.appendGridOverlayNegative, state.resolution, state.aspectRatio, state.duration,
    effectivePrompt, patch, runGeneration,
  ]);

  // -- library ----------------------------------------------------------

  const saveToLibrary = useCallback(
    (result: StepResult, category: string) => {
      // Uploaded (not generated) media has no history entry to save-from —
      // register it as a library asset directly instead.
      if (!result.generationId || !result.outputId) {
        return api.createLibraryAsset(category, {
          name: state.outfit || '換裝角色',
          image_url: result.mediaPath,
        });
      }
      return playgroundApi.saveToLibrary(result.generationId, result.outputId, category);
    },
    [state.outfit],
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
      uploadSheet,
      pickSheet,
      uploadDanceVideo,
      pickDanceVideo,
      generateDepth,
      compose,
      saveToLibrary,
      reset,
    },
  };
}
