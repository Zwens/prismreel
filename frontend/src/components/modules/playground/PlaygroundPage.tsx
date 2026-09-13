'use client';

import { useTranslations } from 'next-intl';
import { Sparkles } from 'lucide-react';
import ModeCardSelector from './ModeCardSelector';
import ModeSelector from './ModeSelector';
import ModelSelector from './ModelSelector';
import MediaInput from './MediaInput';
import PromptInput from './PromptInput';
import ParameterBar from './ParameterBar';
import ResultGallery from './ResultGallery';
import CostEstimate from './CostEstimate';
import { ArrowLeft } from 'lucide-react';
import { usePlaygroundStore, type PlaygroundMode } from './usePlaygroundStore';
import { getModelsForMode } from './playgroundModels';
import { useGenerationRunner } from './useGenerationRunner';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MODE_LABELS: Record<PlaygroundMode, string> = {
  t2i: 'T2I',
  i2i: 'I2I',
  t2v: 'T2V',
  i2v: 'I2V',
  r2v: 'R2V',
  v2v: 'V2V',
};

/** Modes that require media input (image or video source).
 *  t2i also shows optional media input — when provided, it auto-becomes i2i. */
const MODES_WITH_MEDIA: PlaygroundMode[] = ['i2i', 'i2v', 'r2v', 'v2v'];
const MODES_WITH_OPTIONAL_MEDIA: PlaygroundMode[] = ['t2i'];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PlaygroundPage() {
  const t = useTranslations('playground');

  // Compose state the header and controls render from. The queue, the POST and
  // the poller all live in useGenerationRunner, which the AI-video page shares.
  const mode = usePlaygroundStore((s) => s.mode);
  const prompt = usePlaygroundStore((s) => s.prompt);
  const history = usePlaygroundStore((s) => s.history);
  const batchSize = usePlaygroundStore((s) => s.batchSize);
  const playgroundStage = usePlaygroundStore((s) => s.playgroundStage);
  const setPlaygroundStage = usePlaygroundStore((s) => s.setPlaygroundStage);
  const { generate } = useGenerationRunner();

  // 三段式 UI 是 Playground 独有的：提交后要切到结果视图。AI 视频页没有
  // stage 概念，所以这一步留在页面里，而不是塞进共用的 runner。
  const handleGenerate = () => {
    if (!prompt.trim()) return;
    generate();
    setPlaygroundStage('results');
  };

  // ─── Derived values ────────────────────────────────────────────────────────

  const resultCount = history.reduce((n, g) => n + g.outputs.length, 0);
  const showMediaInput = MODES_WITH_MEDIA.includes(mode) || MODES_WITH_OPTIONAL_MEDIA.includes(mode);
  // A mode nothing can serve is not submittable. Without this the button stays
  // live and posts whatever model id the previous mode left behind.
  const hasModel = getModelsForMode(mode).length > 0;
  const canGenerate = hasModel && prompt.trim().length > 0;

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full flex-col overflow-hidden text-foreground">
      {/* ═══ PAGE HEADER ═══ */}
      <header className="flex shrink-0 items-center justify-between border-b border-border-subtle px-7 py-5">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[0.625rem] font-medium uppercase tracking-[0.2em] text-text-muted">
            FREEFORM STUDIO
            <span className="text-primary font-semibold"> · {t('header.eyebrowAccent')}</span>
          </span>
          <div className="flex items-baseline gap-[10px]">
            <h1 className="font-display text-[1.625rem] md:text-[2.125rem] font-semibold tracking-tight text-foreground atelier-display">
              {t('header.title')}
            </h1>
            <span className="font-mono text-[0.6875rem] uppercase tracking-[0.1em] text-text-muted">
              {t('header.resultsCount', { count: resultCount })}
            </span>
          </div>
          <p className="font-mono text-text-muted text-[0.6875rem] tracking-[0.06em]">
            {t('header.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {playgroundStage !== 'select' && (
            <button
              type="button"
              onClick={() => setPlaygroundStage('select')}
              className="flex items-center gap-1.5 rounded-full border border-glass-border bg-glass px-3 py-1.5 text-[0.6875rem] font-medium text-text-muted transition-colors hover:text-foreground hover:bg-hover-bg cursor-pointer"
            >
              <ArrowLeft size={13} aria-hidden="true" />
              {t('compose.switchMode')}
            </button>
          )}
          {playgroundStage !== 'select' && (
            <span className="atelier-badge rounded border border-glass-border bg-glass px-2 py-1 text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
              {MODE_LABELS[mode]}
            </span>
          )}
        </div>
      </header>

      {/* ═══ STAGE: SELECT ═══ */}
      {playgroundStage === 'select' && (
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <ModeCardSelector />
        </div>
      )}

      {/* ═══ STAGE: COMPOSE (full-width, no scroll) ═══ */}
      {playgroundStage === 'compose' && (
        <div className="flex flex-1 flex-col overflow-y-auto scrollbar-thin px-7 py-6">
          <div className="mx-auto grid w-full max-w-5xl flex-1 grid-cols-1 gap-5 md:grid-cols-2">
            <div className="flex flex-col gap-5">
              <section className="glass-panel atelier-card rounded-[20px] px-5 py-5">
                <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                  {t('compose.promptLabel')}
                </div>
                <PromptInput />
              </section>

              {showMediaInput && (
                <section className="glass-panel atelier-card rounded-[20px] px-5 py-5">
                  <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                    {t(
                      mode === 'v2v'
                        ? 'compose.mediaSourceVideo'
                        : mode === 'r2v'
                          ? 'compose.mediaRefMaterial'
                          : mode === 'i2v'
                            ? 'compose.mediaFrames'
                            : 'compose.mediaReference'
                    )}
                  </div>
                  <MediaInput />
                </section>
              )}
            </div>

            <div className="flex flex-col gap-5">
              <section className="glass-panel atelier-card rounded-[20px] px-5 py-5 relative z-30">
                <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                  {t('compose.modelLabel')}
                </div>
                <ModelSelector />
                {!hasModel && (
                  <p className="mt-2 text-[0.6875rem] leading-relaxed text-status-failed-fg">
                    {t('model.noModels')}
                  </p>
                )}
                <div className="my-4 h-px bg-border-subtle" />
                <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                  {t('compose.parametersLabel')}
                </div>
                <ParameterBar />
              </section>
            </div>
          </div>

          <div className="mx-auto mt-5 w-full max-w-5xl">
            <CostEstimate />
            <button
              type="button"
              onClick={handleGenerate}
              disabled={!canGenerate}
              className={[
                'inline-flex w-full items-center justify-center gap-[7px] rounded-full px-6 py-[13px]',
                "font-['Space_Grotesk',sans-serif] text-sm font-semibold",
                'bg-primary text-on-accent shadow-[var(--glow-primary)] transition-all duration-150 disabled:opacity-40 disabled:shadow-none',
                canGenerate
                  ? 'hover:bg-primary-hover hover:-translate-y-px cursor-pointer'
                  : 'cursor-not-allowed',
              ].join(' ')}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span>
                {batchSize > 1
                  ? t('compose.generateBatch', { count: batchSize })
                  : t('compose.generate')}
              </span>
            </button>
          </div>
        </div>
      )}

      {/* ═══ STAGE: RESULTS (split layout) ═══ */}
      {playgroundStage === 'results' && (
        <div className="flex flex-1 overflow-hidden min-h-0">
          {/* ─── LEFT: INPUT PANEL ─── */}
          <aside className="flex w-[420px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-glass-border px-4 py-4 scrollbar-thin">
            {/* Mode */}
            <section className="glass-panel atelier-card rounded-[20px] px-5 py-5">
              <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                {t('compose.modeLabel')}
              </div>
              <ModeSelector />
            </section>

            {/* Prompt — first, the primary input */}
            <section className="glass-panel atelier-card rounded-[20px] px-5 py-5">
              <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                {t('compose.promptLabel')}
              </div>
              <PromptInput />
            </section>

            {/* Media Input (conditional) */}
            {showMediaInput && (
              <section className="glass-panel atelier-card rounded-[20px] px-5 py-5">
                <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                  {t(
                    mode === 'v2v'
                      ? 'compose.mediaSourceVideo'
                      : mode === 'r2v'
                        ? 'compose.mediaRefMaterial'
                        : mode === 'i2v'
                          ? 'compose.mediaFrames'
                          : 'compose.mediaReference'
                  )}
                </div>
                <MediaInput />
              </section>
            )}

            {/* Model & Parameters — merged into one card (mockup) */}
            <section className="glass-panel atelier-card rounded-[20px] px-5 py-5 relative z-30">
              <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                {t('compose.modelLabel')}
              </div>
              <ModelSelector />
              {!hasModel && (
                <p className="mt-2 text-[0.6875rem] leading-relaxed text-status-failed-fg">
                  {t('model.noModels')}
                </p>
              )}
              <div className="my-4 h-px bg-border-subtle" />
              <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                {t('compose.parametersLabel')}
              </div>
              <ParameterBar />
            </section>

            {/* Spacer to push generate button to bottom */}
            <div className="flex-1" />

            {/* Generate CTA (sticky) */}
            <div className="sticky bottom-0 -mx-4 -mb-4 border-t border-glass-border bg-transparent backdrop-blur-md px-4 pb-4 pt-4">
              <CostEstimate />
              <button
                type="button"
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={[
                  'inline-flex w-full items-center justify-center gap-[7px] rounded-full px-6 py-[13px]',
                  "font-['Space_Grotesk',sans-serif] text-sm font-semibold",
                  'bg-primary text-on-accent shadow-[var(--glow-primary)] transition-all duration-150 disabled:opacity-40 disabled:shadow-none',
                  canGenerate
                    ? 'hover:bg-primary-hover hover:-translate-y-px cursor-pointer'
                    : 'cursor-not-allowed',
                ].join(' ')}
              >
                <Sparkles size={16} aria-hidden="true" />
                <span>
                  {batchSize > 1
                    ? t('compose.generateBatch', { count: batchSize })
                    : t('compose.generate')}
                </span>
              </button>
            </div>
          </aside>

          {/* ─── RIGHT: RESULT GALLERY ─── */}
          <main className="flex flex-1 flex-col overflow-hidden min-w-0">
            <ResultGallery />
          </main>
        </div>
      )}
    </div>
  );
}
