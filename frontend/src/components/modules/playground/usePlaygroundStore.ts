import { createContext, createElement, useContext, type ReactNode } from 'react';
import { createStore, useStore, type StateCreator } from 'zustand';
import type { GridOverlayChoice } from '@/components/shared/GridOverlayPicker';

// ---------------------------------------------------------------------------
// Featured (best-of-batch) persistence — client-side localStorage only.
// Map of generationId -> the one outputId marked "featured" within that batch.
// ---------------------------------------------------------------------------

const FEATURED_LS_KEY = 'prismreel:playground:featured';

function loadFeatured(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  try {
    return JSON.parse(window.localStorage.getItem(FEATURED_LS_KEY) || '{}') as Record<string, string>;
  } catch {
    return {};
  }
}

function saveFeatured(map: Record<string, string>): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(FEATURED_LS_KEY, JSON.stringify(map));
  } catch {
    /* ignore quota / serialization errors */
  }
}

// ---------------------------------------------------------------------------
// Generation queue — client-side concurrency gate. Default concurrency is
// persisted to localStorage; queued ids use a simple module counter.
// ---------------------------------------------------------------------------

const CONCURRENCY_LS_KEY = 'prismreel:playground:concurrency';
const DEFAULT_CONCURRENCY = 3;

function loadConcurrency(): number {
  if (typeof window === 'undefined') return DEFAULT_CONCURRENCY;
  const raw = Number(window.localStorage.getItem(CONCURRENCY_LS_KEY));
  return Number.isFinite(raw) && raw >= 1 && raw <= 8 ? raw : DEFAULT_CONCURRENCY;
}

function saveConcurrency(n: number): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CONCURRENCY_LS_KEY, String(n));
  } catch {
    /* ignore */
  }
}

let queueSeq = 0;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PlaygroundMode = 't2i' | 'i2i' | 't2v' | 'i2v' | 'r2v' | 'v2v';

// 'dance' is the multi-step character-swap wizard. It is a stage rather than
// a PlaygroundMode because it is not a model capability — it composes i2i
// and v2v internally, and adding it to PlaygroundMode would leak a
// non-existent capability into model filtering and per-mode preferences.
export type PlaygroundStage = 'select' | 'compose' | 'results' | 'dance';

export interface PlaygroundOutput {
  id: string;
  media_path: string;
  media_type: 'image' | 'video';
  thumbnail_path?: string;
  saved_to_library: boolean;
  total_tokens?: number;
  cost_usd?: number;
}

export interface PlaygroundGeneration {
  id: string;
  mode: PlaygroundMode;
  model_id: string;
  prompt: string;
  negative_prompt?: string;
  input_media: string[];
  parameters: Record<string, any>;
  batch_size: number;
  outputs: PlaygroundOutput[];
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error?: string;
  created_at: string;
}

/** Card count as ResultGallery's grid actually renders it: a completed
 *  generation expands into one tile per output, everything else (pending /
 *  processing / failed) is one tile. Keeps header badges honest against what
 *  the grid shows instead of drifting to a separate outputs.length sum. */
export function countVisibleResults(history: PlaygroundGeneration[]): number {
  return history.reduce(
    (n, g) => n + (g.status === 'completed' && g.outputs.length > 0 ? g.outputs.length : 1),
    0,
  );
}

export interface PlaygroundTemplate {
  id: string;
  name: string;
  category: string;
  prompt: string;
  negative_prompt?: string;
  default_mode?: PlaygroundMode;
  default_model_id?: string;
  default_parameters: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface QueuedRequest {
  id: string;
  mode: PlaygroundMode;
  modelId: string;
  prompt: string;
  negativePrompt?: string;
  inputMedia: string[];
  parameters: Record<string, any>;
  batchSize: number;
  status: 'pending' | 'dispatching';
  enqueuedAt: number;
}

// ---------------------------------------------------------------------------
// State & Actions
// ---------------------------------------------------------------------------

/** Negative prompt fragment appended when any input reference carries a grid
 *  overlay — forced (source: 'upload', just baked in by apply_grid_overlay)
 *  or opt-in (source: 'library', a checkbox next to the prompt). */
export const GRID_OVERLAY_NEGATIVE_PROMPT =
  'no grid lines, no overlay, no mesh, clean skin, smooth image';

/** Positive-prompt fragment telling the model how to read a grid-overlaid
 *  reference image: the grid is a proportion/composition aid, not part of
 *  the subject, and must not be reproduced in the output. Prepended whenever
 *  any input reference carries a baked-in grid overlay. */
export const GRID_OVERLAY_GUIDANCE_PROMPT =
  'The reference image has a proportion grid overlaid on it to help you read ' +
  'body proportions and composition accurately. Use the grid only as a ' +
  'measurement guide — do not reproduce the grid lines in the output.';

/** Positive-prompt equivalent of GRID_OVERLAY_NEGATIVE_PROMPT, for models
 *  whose backend adapter never wires a negative_prompt field through (e.g.
 *  BytePlus Ark / Seedance — see _generate_video_seedance in service.py,
 *  which drops gen.negative_prompt entirely). Append to the main prompt
 *  instead of relying on a negative_prompt param that silently goes nowhere. */
export const GRID_OVERLAY_EXCLUDE_PROMPT_SUFFIX =
  'Output a clean image with no grid lines, no overlay mesh, smooth uninterrupted skin and surfaces.';

export interface PlaygroundState {
  // Current input
  mode: PlaygroundMode;
  modelId: string;
  prompt: string;
  negativePrompt: string;
  inputMedia: string[];
  /** Parallel to inputMedia by index: true when that entry is known to carry
   *  a baked-in grid overlay (fresh upload with gridSize>0, or a library pick
   *  whose selected variant has has_grid_overlay). Drives whether MediaInput
   *  shows the "exclude grid lines" checkbox at all. */
  inputMediaHasGridOverlay: boolean[];
  /** Checkbox state — whether GRID_OVERLAY_NEGATIVE_PROMPT is appended to the
   *  negative prompt on generate. Auto-set to true whenever a grid-overlay
   *  reference is added (forced for fresh uploads, pre-checked but toggleable
   *  for library picks), left as-is otherwise. */
  appendGridOverlayNegative: boolean;
  setAppendGridOverlayNegative: (value: boolean) => void;
  /** User's current grid-overlay choice for media not yet burned in. Applied
   *  at generate time (not at upload time) so picking images and choosing a
   *  grid style are independent steps — see GridOverlayChoice in
   *  GridOverlayPicker.tsx. */
  pendingGridChoice: GridOverlayChoice;
  setPendingGridChoice: (choice: GridOverlayChoice) => void;
  parameters: Record<string, any>;
  batchSize: number;

  // Model preferences (mode -> last used modelId)
  modelPreferences: Partial<Record<PlaygroundMode, string>>;

  // History
  history: PlaygroundGeneration[];

  // Templates
  templates: PlaygroundTemplate[];

  // UI
  isGenerating: boolean;
  activeGenerationIds: string[];
  showAdvancedParams: boolean;
  showTemplateModal: boolean;
  showHistoryDrawer: boolean;

  // Page-level stage (select mode -> compose inputs -> view results)
  playgroundStage: PlaygroundStage;
  setPlaygroundStage: (stage: PlaygroundStage) => void;

  // Template favorites (local, not persisted to backend)
  favoriteTemplateIds: string[];
  toggleTemplateFavorite: (id: string) => void;
  isTemplateFavorited: (id: string) => boolean;

  // Featured output per generation (best-of-batch); one per batch, localStorage-persisted
  featuredByGen: Record<string, string>;
  toggleFeatured: (genId: string, outputId: string) => void;
  isFeatured: (genId: string, outputId: string) => boolean;

  // Generation queue (client-side concurrency gate)
  queue: QueuedRequest[];
  maxConcurrent: number;
  enqueueRequest: (req: Omit<QueuedRequest, 'id' | 'status' | 'enqueuedAt'>) => void;
  markDispatching: (id: string) => void;
  removeFromQueue: (id: string) => void;
  setMaxConcurrent: (n: number) => void;

  // Actions — input setters
  setMode: (mode: PlaygroundMode) => void;
  setModelId: (modelId: string) => void;
  setPrompt: (prompt: string) => void;
  setNegativePrompt: (neg: string) => void;
  /** hasGridOverlay, parallel to media by index, defaults to all-false when
   *  omitted. Auto re-derives appendGridOverlayNegative: true the moment any
   *  entry is true, otherwise left as the user last set it. */
  setInputMedia: (media: string[], hasGridOverlay?: boolean[]) => void;
  /** Push a generated result back into the compose panel as reference input,
   *  switching to the appropriate mode. Image → i2i (default) or i2v when an
   *  explicit targetMode is given; video → v2v. Respects per-mode model
   *  preference (same behavior as setMode). */
  useResultAsReference: (
    mediaPath: string,
    mediaType: 'image' | 'video',
    targetMode?: PlaygroundMode,
  ) => void;
  setParameters: (params: Record<string, any>) => void;
  setBatchSize: (size: number) => void;
  setShowAdvancedParams: (show: boolean) => void;
  setShowTemplateModal: (show: boolean) => void;
  setShowHistoryDrawer: (show: boolean) => void;

  // Actions — generation lifecycle
  startGeneration: (gen: PlaygroundGeneration) => void;
  updateGeneration: (gen: PlaygroundGeneration) => void;
  removeGeneration: (id: string) => void;

  // Actions — history
  setHistory: (history: PlaygroundGeneration[]) => void;
  appendToHistory: (gen: PlaygroundGeneration) => void;

  // Actions — templates
  setTemplates: (templates: PlaygroundTemplate[]) => void;
  addTemplate: (template: PlaygroundTemplate) => void;
  updateTemplate: (template: PlaygroundTemplate) => void;
  removeTemplate: (id: string) => void;
  applyTemplate: (template: PlaygroundTemplate) => void;

  // Actions — reset
  resetInput: () => void;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULT_MODE: PlaygroundMode = 't2i';
const DEFAULT_MODEL_ID = '';
const DEFAULT_PROMPT = '';
const DEFAULT_BATCH_SIZE = 1;

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

const initPlaygroundState: StateCreator<PlaygroundState> = (set, get) => ({
  // -- Current input --------------------------------------------------------
  mode: DEFAULT_MODE,
  modelId: DEFAULT_MODEL_ID,
  prompt: DEFAULT_PROMPT,
  negativePrompt: '',
  inputMedia: [],
  inputMediaHasGridOverlay: [],
  appendGridOverlayNegative: false,
  setAppendGridOverlayNegative: (value) => set({ appendGridOverlayNegative: value }),
  pendingGridChoice: 'none',
  setPendingGridChoice: (choice) => set({ pendingGridChoice: choice }),
  parameters: {},
  batchSize: DEFAULT_BATCH_SIZE,

  // -- Model preferences ----------------------------------------------------
  modelPreferences: {},

  // -- History ---------------------------------------------------------------
  history: [],

  // -- Templates -------------------------------------------------------------
  templates: [],

  // -- UI --------------------------------------------------------------------
  isGenerating: false,
  activeGenerationIds: [],
  showAdvancedParams: false,
  showTemplateModal: false,
  showHistoryDrawer: false,

  // -- Page-level stage --------------------------------------------------------
  playgroundStage: 'select',
  setPlaygroundStage: (playgroundStage) => set({ playgroundStage }),

  // -- Template favorites ----------------------------------------------------
  favoriteTemplateIds: [],
  toggleTemplateFavorite: (id) => {
    const { favoriteTemplateIds } = get();
    if (favoriteTemplateIds.includes(id)) {
      set({ favoriteTemplateIds: favoriteTemplateIds.filter((fid) => fid !== id) });
    } else {
      set({ favoriteTemplateIds: [...favoriteTemplateIds, id] });
    }
  },
  isTemplateFavorited: (id) => get().favoriteTemplateIds.includes(id),

  // -- Featured output (best-of-batch, one per generation) -------------------
  featuredByGen: loadFeatured(),
  toggleFeatured: (genId, outputId) => {
    const next = { ...get().featuredByGen };
    if (next[genId] === outputId) delete next[genId];
    else next[genId] = outputId;
    saveFeatured(next);
    set({ featuredByGen: next });
  },
  isFeatured: (genId, outputId) => get().featuredByGen[genId] === outputId,

  // -- Generation queue (client-side concurrency gate) -----------------------
  queue: [],
  maxConcurrent: loadConcurrency(),
  enqueueRequest: (req) =>
    set((s) => ({
      queue: [
        ...s.queue,
        { ...req, id: `q${++queueSeq}`, status: 'pending' as const, enqueuedAt: Date.now() },
      ],
    })),
  markDispatching: (id) =>
    set((s) => ({
      queue: s.queue.map((q) => (q.id === id ? { ...q, status: 'dispatching' as const } : q)),
    })),
  removeFromQueue: (id) => set((s) => ({ queue: s.queue.filter((q) => q.id !== id) })),
  setMaxConcurrent: (n) => {
    const clamped = Math.max(1, Math.min(8, Math.round(n)));
    saveConcurrency(clamped);
    set({ maxConcurrent: clamped });
  },

  // =========================================================================
  // Actions
  // =========================================================================

  // -- Input setters ---------------------------------------------------------

  setMode: (mode) => {
    const { modelPreferences } = get();
    const preferredModel = modelPreferences[mode];
    set({
      mode,
      ...(preferredModel !== undefined ? { modelId: preferredModel } : {}),
    });
  },

  setModelId: (modelId) => {
    const { mode, modelPreferences } = get();
    set({
      modelId,
      modelPreferences: { ...modelPreferences, [mode]: modelId },
    });
  },

  setPrompt: (prompt) => set({ prompt }),

  setNegativePrompt: (negativePrompt) => set({ negativePrompt }),

  setInputMedia: (inputMedia, hasGridOverlay) => {
    const flags = hasGridOverlay ?? inputMedia.map(() => false);
    set((s) => ({
      inputMedia,
      inputMediaHasGridOverlay: flags,
      appendGridOverlayNegative: flags.some(Boolean) ? true : s.appendGridOverlayNegative,
    }));
  },

  useResultAsReference: (mediaPath, mediaType, targetMode) => {
    const { modelPreferences } = get();
    const mode: PlaygroundMode =
      targetMode ?? (mediaType === 'video' ? 'v2v' : 'i2i');
    const preferredModel = modelPreferences[mode];
    set({
      mode,
      inputMedia: [mediaPath],
      inputMediaHasGridOverlay: [false],
      ...(preferredModel !== undefined ? { modelId: preferredModel } : {}),
    });
  },

  setParameters: (parameters) => set({ parameters }),

  setBatchSize: (batchSize) => set({ batchSize }),

  setShowAdvancedParams: (showAdvancedParams) => set({ showAdvancedParams }),

  setShowTemplateModal: (showTemplateModal) =>
    set(showTemplateModal ? { showTemplateModal, showHistoryDrawer: false } : { showTemplateModal }),

  setShowHistoryDrawer: (showHistoryDrawer) =>
    set(showHistoryDrawer ? { showHistoryDrawer, showTemplateModal: false } : { showHistoryDrawer }),

  // -- Generation lifecycle --------------------------------------------------

  startGeneration: (gen) => {
    const { activeGenerationIds, history } = get();
    set({
      activeGenerationIds: [...activeGenerationIds, gen.id],
      history: [gen, ...history],
      isGenerating: true,
    });
  },

  updateGeneration: (gen) => {
    const { history, activeGenerationIds } = get();
    const updatedHistory = history.map((h) => (h.id === gen.id ? gen : h));
    const isTerminal = gen.status === 'completed' || gen.status === 'failed';
    const updatedActive = isTerminal
      ? activeGenerationIds.filter((id) => id !== gen.id)
      : activeGenerationIds;

    set({
      history: updatedHistory,
      activeGenerationIds: updatedActive,
      isGenerating: updatedActive.length > 0,
    });
  },

  removeGeneration: (id) => {
    const { history, activeGenerationIds } = get();
    const updatedActive = activeGenerationIds.filter((gid) => gid !== id);
    set({
      history: history.filter((h) => h.id !== id),
      activeGenerationIds: updatedActive,
      isGenerating: updatedActive.length > 0,
    });
  },

  // -- History ---------------------------------------------------------------

  setHistory: (history) => set({ history }),

  appendToHistory: (gen) => set((s) => ({ history: [gen, ...s.history] })),

  // -- Templates -------------------------------------------------------------

  setTemplates: (templates) => set({ templates }),

  addTemplate: (template) =>
    set((s) => ({ templates: [...s.templates, template] })),

  updateTemplate: (template) =>
    set((s) => ({
      templates: s.templates.map((t) => (t.id === template.id ? template : t)),
    })),

  removeTemplate: (id) =>
    set((s) => ({ templates: s.templates.filter((t) => t.id !== id) })),

  applyTemplate: (template) => {
    const patch: Partial<PlaygroundState> = {
      prompt: template.prompt,
    };
    if (template.negative_prompt != null) {
      patch.negativePrompt = template.negative_prompt;
    }
    if (template.default_mode != null) {
      patch.mode = template.default_mode;
    }
    if (template.default_model_id != null) {
      patch.modelId = template.default_model_id;
    }
    if (
      template.default_parameters != null &&
      Object.keys(template.default_parameters).length > 0
    ) {
      patch.parameters = template.default_parameters;
    }
    set(patch);
  },

  // -- Reset -----------------------------------------------------------------

  resetInput: () =>
    set({
      prompt: DEFAULT_PROMPT,
      negativePrompt: '',
      inputMedia: [],
      inputMediaHasGridOverlay: [],
      appendGridOverlayNegative: false,
      parameters: {},
      batchSize: DEFAULT_BATCH_SIZE,
    }),
});

/**
 * Build an independent store instance.
 *
 * The playground used to own a single module-level store, which was fine while
 * it was the only surface composing a generation. The standalone AI-video page
 * is a second such surface, and one shared store would let the two pages
 * overwrite each other's mode / prompt / inputMedia. So the store became a
 * factory, and which instance a component talks to is decided by the provider
 * above it rather than by the import it happens to use.
 */
export function createPlaygroundStore() {
  return createStore<PlaygroundState>()(initPlaygroundState);
}

export type PlaygroundStoreApi = ReturnType<typeof createPlaygroundStore>;

/** The instance the创作台 uses. Kept as a module-level singleton so that page —
 *  and anything not wrapped in a provider — behaves exactly as it did before. */
export const playgroundStore = createPlaygroundStore();

const PlaygroundStoreContext = createContext<PlaygroundStoreApi | null>(null);

/** Bind a subtree to its own store. Only the AI-video page needs this; the
 *  playground renders without one and lands on the default instance. */
export function PlaygroundStoreProvider({
  store,
  children,
}: {
  store: PlaygroundStoreApi;
  children: ReactNode;
}) {
  return createElement(PlaygroundStoreContext.Provider, { value: store }, children);
}

/**
 * The store API for this subtree, unsubscribed.
 *
 * For imperative reads outside the render path — the queue pump needs a fresh
 * snapshot and must not re-render on every queue change. Reaching for
 * `playgroundStore.getState()` directly would work today and silently talk to
 * the wrong instance the moment a second page exists; this does not.
 */
export function usePlaygroundStoreApi(): PlaygroundStoreApi {
  return useContext(PlaygroundStoreContext) ?? playgroundStore;
}

export function usePlaygroundStore(): PlaygroundState;
export function usePlaygroundStore<T>(selector: (state: PlaygroundState) => T): T;
export function usePlaygroundStore<T>(selector?: (state: PlaygroundState) => T) {
  const store = usePlaygroundStoreApi();
  // Both call shapes were already in use — selector form in most components,
  // whole-store destructure in ResultGallery and PromptTemplateModal — so both
  // are supported rather than rewriting every call site in the same commit.
  return selector ? useStore(store, selector) : useStore(store);
}
