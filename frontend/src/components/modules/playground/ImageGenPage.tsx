'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Type, ImagePlus, Sparkles, ArrowLeft, Grid3x3 } from 'lucide-react';
import ModelSelector from './ModelSelector';
import MediaInput from './MediaInput';
import PromptInput from './PromptInput';
import ParameterBar from './ParameterBar';
import ResultGallery from './ResultGallery';
import CostEstimate from './CostEstimate';
import GridBurnCard from './GridBurnCard';
import {
  createPlaygroundStore,
  PlaygroundStoreProvider,
  usePlaygroundStore,
  countVisibleResults,
  type PlaygroundMode,
  type PlaygroundStoreApi,
} from './usePlaygroundStore';
import { getModelsForMode } from './playgroundModels';
import { useGenerationRunner } from './useGenerationRunner';

// ---------------------------------------------------------------------------
// Image Generation — the image half of the former single Playground entry
// (2026-09-18). Keeps the select -> compose -> results card flow since there
// are only three cards here; a tab row would be overkill at this count.
// gridBurn is not a PlaygroundMode — it is its own self-contained card that
// calls the library upload / apply-grid endpoints directly (see GridBurnCard).
//
// Owns its own store instance (like VideoGenPage) rather than the old shared
// module-level singleton — image and video generation are separate surfaces
// now and must not overwrite each other's mode/prompt/inputMedia.
// ---------------------------------------------------------------------------

type ImageStage = 'select' | 'compose' | 'results' | 'gridBurn';

const MODES_WITH_MEDIA: PlaygroundMode[] = ['i2i'];
const MODES_WITH_OPTIONAL_MEDIA: PlaygroundMode[] = ['t2i'];

export default function ImageGenPage() {
  const storeRef = useRef<PlaygroundStoreApi | null>(null);
  if (storeRef.current === null) {
    const store = createPlaygroundStore();
    store.setState({ mode: 't2i' });
    storeRef.current = store;
  }

  return (
    <PlaygroundStoreProvider store={storeRef.current}>
      <ImageGenWorkspace />
    </PlaygroundStoreProvider>
  );
}

// Exported so tests can supply their own PlaygroundStoreProvider instance
// instead of the one ImageGenPage auto-creates (mirrors storeWiring.isolation's
// pattern for a page with its own store, not the module-level singleton).
export function ImageGenWorkspace() {
  const t = useTranslations('playground');
  const tNav = useTranslations('nav');
  const mode = usePlaygroundStore((s) => s.mode);
  const prompt = usePlaygroundStore((s) => s.prompt);
  const history = usePlaygroundStore((s) => s.history);
  const batchSize = usePlaygroundStore((s) => s.batchSize);
  const setMode = usePlaygroundStore((s) => s.setMode);
  const { generate } = useGenerationRunner();

  // Local stage — image gen's gridBurn card doesn't belong in the shared
  // PlaygroundStage union (it never touches generate/results), so it stays
  // as component state rather than store state.
  const rawStage = usePlaygroundStore((s) => s.playgroundStage);
  const setRawStage = usePlaygroundStore((s) => s.setPlaygroundStage);
  const stage: ImageStage = rawStage === 'select' ? 'select' : rawStage === 'results' ? 'results' : 'compose';

  const goSelect = () => setRawStage('select');
  const goCompose = (m: PlaygroundMode) => {
    setMode(m);
    setRawStage('compose');
  };

  const handleGenerate = () => {
    if (!prompt.trim()) return;
    generate();
    setRawStage('results');
  };

  const resultCount = countVisibleResults(history);
  const showMediaInput = MODES_WITH_MEDIA.includes(mode) || MODES_WITH_OPTIONAL_MEDIA.includes(mode);
  const hasModel = getModelsForMode(mode).length > 0;
  const canGenerate = hasModel && prompt.trim().length > 0;

  const [showGridBurn, setShowGridBurn] = useState(false);

  return (
    <div className="flex h-full flex-col overflow-hidden text-foreground">
      <header className="flex shrink-0 items-center justify-between border-b border-border-subtle px-7 py-5">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[0.625rem] font-medium uppercase tracking-[0.2em] text-text-muted">
            IMAGE STUDIO
            <span className="font-semibold text-primary"> · {t('header.eyebrowAccent')}</span>
          </span>
          <div className="flex items-baseline gap-[10px]">
            <h1 className="atelier-display font-display text-[1.625rem] font-semibold tracking-tight text-foreground md:text-[2.125rem]">
              {tNav('imagegen')}
            </h1>
            <span className="font-mono text-[0.6875rem] uppercase tracking-[0.1em] text-text-muted">
              {t('header.resultsCount', { count: resultCount })}
            </span>
          </div>
        </div>
        {(stage !== 'select' || showGridBurn) && (
          <button
            type="button"
            onClick={() => {
              setShowGridBurn(false);
              goSelect();
            }}
            className="flex items-center gap-1.5 rounded-full border border-glass-border bg-glass px-3 py-1.5 text-[0.6875rem] font-medium text-text-muted transition-colors hover:bg-hover-bg hover:text-foreground cursor-pointer"
          >
            <ArrowLeft size={13} aria-hidden="true" />
            {t('compose.switchMode')}
          </button>
        )}
      </header>

      {showGridBurn ? (
        <div className="flex-1 overflow-y-auto scrollbar-thin px-7 py-6">
          <GridBurnCard onComplete={() => setShowGridBurn(false)} />
        </div>
      ) : stage === 'select' ? (
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-6 py-10">
            <div className="flex flex-col gap-1 text-center">
              <h2 className="font-display text-[1.5rem] font-semibold tracking-tight text-foreground">
                {t('modeCard.heading')}
              </h2>
              <p className="font-mono text-[0.75rem] text-text-muted">{t('modeCard.subheading')}</p>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <ImageModeCard
                icon={Type}
                title={t('modeCard.t2i.title')}
                description={t('modeCard.t2i.description')}
                onClick={() => goCompose('t2i')}
              />
              <ImageModeCard
                icon={ImagePlus}
                title={t('modeCard.i2i.title')}
                description={t('modeCard.i2i.description')}
                onClick={() => goCompose('i2i')}
              />
              <ImageModeCard
                icon={Grid3x3}
                title={t('imageGen.gridBurn.title')}
                description={t('imageGen.gridBurn.description')}
                accent
                badge="新功能"
                onClick={() => setShowGridBurn(true)}
              />
            </div>
          </div>
        </div>
      ) : stage === 'compose' ? (
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
                    {t('compose.mediaReference')}
                  </div>
                  <MediaInput />
                </section>
              )}
            </div>
            <div className="flex flex-col gap-5">
              <section className="glass-panel atelier-card relative z-30 rounded-[20px] px-5 py-5">
                <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
                  {t('compose.modelLabel')}
                </div>
                <ModelSelector />
                {!hasModel && (
                  <p className="mt-2 text-[0.6875rem] leading-relaxed text-status-failed-fg">{t('model.noModels')}</p>
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
                canGenerate ? 'hover:bg-primary-hover hover:-translate-y-px cursor-pointer' : 'cursor-not-allowed',
              ].join(' ')}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span>
                {batchSize > 1 ? t('compose.generateBatch', { count: batchSize }) : t('compose.generate')}
              </span>
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden min-h-0">
          <main className="flex flex-1 flex-col overflow-hidden min-w-0 min-h-0">
            <ResultGallery />
          </main>
        </div>
      )}
    </div>
  );
}

function ImageModeCard({
  icon: Icon,
  title,
  description,
  onClick,
  accent = false,
  badge,
}: {
  icon: typeof Type;
  title: string;
  description: string;
  onClick: () => void;
  accent?: boolean;
  badge?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="glass-panel atelier-card group flex flex-col items-start gap-3 rounded-[20px] px-6 py-6 text-left transition-all hover:-translate-y-0.5 hover:shadow-[var(--glow-primary)] cursor-pointer"
    >
      <span
        className={[
          'flex h-11 w-11 items-center justify-center rounded-full transition-colors',
          accent
            ? 'bg-[color-mix(in_oklab,var(--color-accent)_14%,transparent)] text-accent'
            : 'bg-surface-inset text-primary group-hover:bg-primary group-hover:text-on-accent',
        ].join(' ')}
      >
        <Icon size={20} aria-hidden="true" />
      </span>
      <span className="font-display text-[1.0625rem] font-semibold tracking-tight text-foreground">{title}</span>
      <span className="font-mono text-[0.75rem] leading-relaxed text-text-muted">{description}</span>
      {badge && (
        <span className="mt-1 inline-block rounded-full bg-[color-mix(in_oklab,var(--color-accent)_18%,transparent)] px-2 py-0.5 font-mono text-[0.5625rem] uppercase tracking-[0.08em] text-accent">
          {badge}
        </span>
      )}
    </button>
  );
}
