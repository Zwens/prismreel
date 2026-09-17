'use client';

import { useMemo, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Clapperboard, Sparkles, AlertCircle } from 'lucide-react';
import ModelSelector from '@/components/modules/playground/ModelSelector';
import MediaInput from '@/components/modules/playground/MediaInput';
import PromptInput from '@/components/modules/playground/PromptInput';
import ParameterBar from '@/components/modules/playground/ParameterBar';
import ResultGallery from '@/components/modules/playground/ResultGallery';
import QueuePanel from '@/components/modules/playground/QueuePanel';
import { getModelsForMode } from '@/components/modules/playground/playgroundModels';
import { useGenerationRunner } from '@/components/modules/playground/useGenerationRunner';
import {
  createPlaygroundStore,
  PlaygroundStoreProvider,
  usePlaygroundStore,
  type PlaygroundMode,
  type PlaygroundStoreApi,
} from '@/components/modules/playground/usePlaygroundStore';

// ---------------------------------------------------------------------------
// Scope
//
// Single-shot video generation, drawing on assets that already exist elsewhere
// in the app. Deliberately narrower than the创作台: no image modes, and no r2v —
// reference-driven shots belong to a series' storyboard, not to a one-off.
//
// v2v covers editing and extension; which of the two a request means is decided
// by Ark's omni_reference_task_type rather than by a mode of its own, so it does
// not get a pill here. That subtype selector is the next piece of work.
// ---------------------------------------------------------------------------

const VIDEO_MODES: PlaygroundMode[] = ['t2v', 'i2v', 'v2v'];

/** The sub-types of Ark's omni-reference task, in the order they are offered.
 *  'auto' is the vendor default and is expressed by sending nothing. */
const TASK_TYPES = ['auto', 'edit', 'extend'] as const;
type TaskType = (typeof TASK_TYPES)[number];

/** Only Seedance 2.5 accepts omni_reference_task_type; the 2.0 series can still
 *  edit and extend, but only by letting the model guess from the prompt.
 *  Mirrors ARK_OMNI_TASK_TYPE_MODELS in src/models/byteplus.py — kept as a
 *  prefix here because the catalog carries no field for the capability. */
const SUPPORTS_TASK_TYPE = /^seedance-2\.5-/;

/** Modes that cannot be submitted without a source image or video. */
const MODES_NEEDING_MEDIA: PlaygroundMode[] = ['i2v', 'v2v'];

export default function AiVideoPage() {
  // One store per mounted page, created once. Sharing the创作台's instance would
  // let the two pages overwrite each other's mode / prompt / input media.
  const storeRef = useRef<PlaygroundStoreApi | null>(null);
  if (storeRef.current === null) {
    const store = createPlaygroundStore();
    store.setState({ mode: 't2v' });
    storeRef.current = store;
  }

  return (
    <PlaygroundStoreProvider store={storeRef.current}>
      <AiVideoWorkspace />
    </PlaygroundStoreProvider>
  );
}

function AiVideoWorkspace() {
  const t = useTranslations('aivideo');
  const mode = usePlaygroundStore((s) => s.mode);
  const prompt = usePlaygroundStore((s) => s.prompt);
  const batchSize = usePlaygroundStore((s) => s.batchSize);
  const history = usePlaygroundStore((s) => s.history);
  const setMode = usePlaygroundStore((s) => s.setMode);
  const modelId = usePlaygroundStore((s) => s.modelId);
  const parameters = usePlaygroundStore((s) => s.parameters);
  const setParameters = usePlaygroundStore((s) => s.setParameters);
  const { generate } = useGenerationRunner();

  const availableModels = useMemo(() => getModelsForMode(mode), [mode]);

  // A mode with nothing behind it is a dead end, and the创作台 handles it badly:
  // ModelSelector only auto-adopts when the list is non-empty, so the previous
  // mode's model id survives and gets submitted against a mode it cannot serve.
  // Here the mode is simply not submittable, and says why.
  const hasModel = availableModels.length > 0;
  const canGenerate = hasModel && prompt.trim().length > 0;

  const resultCount = history.reduce((n, g) => n + g.outputs.length, 0);
  const showMediaInput = MODES_NEEDING_MEDIA.includes(mode);

  const showTaskType = mode === 'v2v' && hasModel;
  const taskTypeSupported = SUPPORTS_TASK_TYPE.test(modelId);
  const taskType: TaskType = (parameters.task_type as TaskType) ?? 'auto';

  // Ark rejects an edit whose ratio is not adaptive or whose duration is not -1.
  // Pinning both here beats letting the user assemble a request that can only
  // come back as a vendor error naming a field they never set.
  const pickTaskType = (next: TaskType) => {
    const rest = { ...parameters };
    delete rest.task_type;
    if (next === 'auto') {
      setParameters(rest);
      return;
    }
    setParameters(
      next === 'edit'
        ? { ...rest, task_type: 'edit', aspect_ratio: 'adaptive', duration: -1 }
        : { ...rest, task_type: next },
    );
  };

  return (
    <div className="flex h-full flex-col overflow-hidden text-foreground">
      {/* ═══ HEADER ═══ */}
      <header className="flex shrink-0 items-center justify-between border-b border-border-subtle px-7 py-5">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[0.625rem] font-medium uppercase tracking-[0.2em] text-text-muted">
            AI VIDEO
            <span className="font-semibold text-primary"> · {t('eyebrow')}</span>
          </span>
          <div className="flex items-baseline gap-[10px]">
            <h1 className="atelier-display font-display text-[1.625rem] font-semibold tracking-tight text-foreground md:text-[2.125rem]">
              {t('title')}
            </h1>
            <span className="font-mono text-[0.6875rem] uppercase tracking-[0.1em] text-text-muted">
              {t('resultsCount', { count: resultCount })}
            </span>
          </div>
          <p className="font-mono text-[0.6875rem] tracking-[0.06em] text-text-muted">
            {t('subtitle')}
          </p>
        </div>
        <QueuePanel />
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* ═══ COMPOSE COLUMN ═══ */}
        <div className="flex w-[380px] shrink-0 flex-col gap-5 overflow-y-auto border-r border-border-subtle p-6">
          {/* Mode pills */}
          <div>
            <div className="mb-1.5 flex items-center gap-2">
              <span className="font-mono text-[0.5625rem] uppercase tracking-[0.18em] text-text-muted">
                {t('groupVideo')}
              </span>
              <span className="atelier-group-line h-px flex-1 bg-border-subtle" />
            </div>
            <div className="atelier-pill-tabs flex gap-[2px] rounded-full bg-surface-inset p-[3px]">
              {VIDEO_MODES.map((key) => {
                const active = mode === key;
                return (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setMode(key)}
                    className={[
                      'flex-1 cursor-pointer rounded-full px-3 py-1.5 text-center text-[0.6875rem] font-semibold transition-all',
                      active
                        ? 'atelier-pill-tab-active bg-surface text-foreground shadow-[0_2px_8px_rgba(0,0,0,0.4)]'
                        : 'text-text-muted hover:bg-hover-bg hover:text-foreground',
                    ].join(' ')}
                  >
                    {t(`mode.${key}`)}
                  </button>
                );
              })}
            </div>
          </div>

          {hasModel ? (
            <ModelSelector />
          ) : (
            <div className="flex flex-col gap-1.5 rounded-[14px] border border-border-subtle bg-surface-inset p-4">
              <span className="flex items-center gap-2 text-[0.8125rem] font-medium text-foreground">
                <AlertCircle className="h-4 w-4 text-status-failed-fg" />
                {t('noModels')}
              </span>
              <span className="text-[0.6875rem] leading-relaxed text-text-muted">
                {t('noModelsHint')}
              </span>
            </div>
          )}

          {showTaskType && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[0.5625rem] uppercase tracking-[0.18em] text-text-muted">
                  {t('taskType.label')}
                </span>
                <span className="atelier-group-line h-px flex-1 bg-border-subtle" />
              </div>
              {taskTypeSupported ? (
                <>
                  <div className="atelier-pill-tabs flex gap-[2px] rounded-full bg-surface-inset p-[3px]">
                    {TASK_TYPES.map((key) => {
                      const active = taskType === key;
                      return (
                        <button
                          key={key}
                          type="button"
                          aria-pressed={active}
                          onClick={() => pickTaskType(key)}
                          className={[
                            'flex-1 cursor-pointer rounded-full px-3 py-1.5 text-center text-[0.6875rem] font-semibold transition-all',
                            active
                              ? 'atelier-pill-tab-active bg-surface text-foreground shadow-[0_2px_8px_rgba(0,0,0,0.4)]'
                              : 'text-text-muted hover:bg-hover-bg hover:text-foreground',
                          ].join(' ')}
                        >
                          {t(`taskType.${key}`)}
                        </button>
                      );
                    })}
                  </div>
                  {taskType === 'edit' && (
                    <span className="text-[0.6875rem] leading-relaxed text-text-muted">
                      {t('taskType.hint')}
                    </span>
                  )}
                </>
              ) : (
                <span className="text-[0.6875rem] leading-relaxed text-text-muted">
                  {t('taskType.unsupported')}
                </span>
              )}
            </div>
          )}

          {showMediaInput && <MediaInput />}

          <div className="rounded-[14px] border border-border-subtle bg-surface-inset p-4">
            <PromptInput />
          </div>

          {hasModel && <ParameterBar />}

          <button
            type="button"
            onClick={generate}
            disabled={!canGenerate}
            className={[
              'inline-flex items-center justify-center gap-2 rounded-full px-5 py-3 text-[0.8125rem] font-medium transition-all',
              canGenerate
                ? 'bg-primary text-on-accent shadow-[var(--glow-primary)] hover:-translate-y-px hover:bg-primary-hover'
                : 'cursor-not-allowed bg-elevated text-text-muted',
            ].join(' ')}
          >
            <Sparkles size={16} aria-hidden="true" />
            <span>
              {batchSize > 1 ? t('generateBatch', { count: batchSize }) : t('generate')}
            </span>
          </button>
        </div>

        {/* ═══ RESULTS ═══ */}
        <div className="min-w-0 min-h-0 flex-1 overflow-hidden">
          <ResultGallery />
        </div>
      </div>
    </div>
  );
}

export { Clapperboard as AiVideoIcon };
