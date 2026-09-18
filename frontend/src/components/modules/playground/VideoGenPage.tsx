'use client';

import { useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Sparkles } from 'lucide-react';
import DanceSwapWizard from './dance/DanceSwapWizard';
import ModelSelector from './ModelSelector';
import MediaInput from './MediaInput';
import PromptInput from './PromptInput';
import ParameterBar from './ParameterBar';
import ResultGallery from './ResultGallery';
import CostEstimate from './CostEstimate';
import {
  createPlaygroundStore,
  PlaygroundStoreProvider,
  usePlaygroundStore,
  countVisibleResults,
  type PlaygroundMode,
} from './usePlaygroundStore';
import type { PlaygroundStoreApi } from './usePlaygroundStore';
import { getModelsForMode } from './playgroundModels';
import { useGenerationRunner } from './useGenerationRunner';

// ---------------------------------------------------------------------------
// Video Generation — replaces the former standalone AI-video quick-start page
// and the video half of Playground's mode-card select stage (2026-09-18).
// All five video-producing modes sit behind one tab row and open straight
// into their compose panel — no intermediate card menu. Dance is the odd one
// out: it is a multi-step wizard, not a single-shot compose form, so picking
// its tab swaps the whole body for DanceSwapWizard instead of showing panels.
// ---------------------------------------------------------------------------

type VideoTab = 't2v' | 'i2v' | 'r2v' | 'v2v' | 'dance';

const VIDEO_TABS: VideoTab[] = ['t2v', 'i2v', 'r2v', 'v2v', 'dance'];

const MODES_WITH_MEDIA: PlaygroundMode[] = ['i2v', 'r2v', 'v2v'];

export default function VideoGenPage() {
  const storeRef = useRef<PlaygroundStoreApi | null>(null);
  if (storeRef.current === null) {
    const store = createPlaygroundStore();
    store.setState({ mode: 't2v', playgroundStage: 'compose' });
    storeRef.current = store;
  }

  return (
    <PlaygroundStoreProvider store={storeRef.current}>
      <VideoGenWorkspace />
    </PlaygroundStoreProvider>
  );
}

// Exported so tests can supply their own PlaygroundStoreProvider instance
// instead of the one VideoGenPage auto-creates.
export function VideoGenWorkspace() {
  const t = useTranslations('playground');
  const mode = usePlaygroundStore((s) => s.mode);
  const prompt = usePlaygroundStore((s) => s.prompt);
  const history = usePlaygroundStore((s) => s.history);
  const batchSize = usePlaygroundStore((s) => s.batchSize);
  const playgroundStage = usePlaygroundStore((s) => s.playgroundStage);
  const setMode = usePlaygroundStore((s) => s.setMode);
  const setPlaygroundStage = usePlaygroundStore((s) => s.setPlaygroundStage);
  const { generate } = useGenerationRunner();

  const activeTab: VideoTab = playgroundStage === 'dance' ? 'dance' : (mode as VideoTab);

  const selectTab = (tab: VideoTab) => {
    if (tab === 'dance') {
      setPlaygroundStage('dance');
      return;
    }
    setMode(tab);
    setPlaygroundStage('compose');
  };

  const handleGenerate = () => {
    if (!prompt.trim()) return;
    generate();
    setPlaygroundStage('results');
  };

  const resultCount = countVisibleResults(history);
  const showMediaInput = MODES_WITH_MEDIA.includes(mode);
  const hasModel = getModelsForMode(mode).length > 0;
  const canGenerate = hasModel && prompt.trim().length > 0;

  const mediaLabelKey =
    mode === 'v2v'
      ? 'compose.mediaSourceVideo'
      : mode === 'r2v'
        ? 'compose.mediaRefMaterial'
        : 'compose.mediaFrames';

  return (
    <div className="flex h-full flex-col overflow-hidden text-foreground">
      <header className="flex shrink-0 items-center justify-between border-b border-border-subtle px-7 py-5">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[0.625rem] font-medium uppercase tracking-[0.2em] text-text-muted">
            VIDEO STUDIO
            <span className="font-semibold text-primary"> · {t('header.eyebrowAccent')}</span>
          </span>
          <div className="flex items-baseline gap-[10px]">
            <h1 className="atelier-display font-display text-[1.625rem] font-semibold tracking-tight text-foreground md:text-[2.125rem]">
              {t('header.title')}
            </h1>
            <span className="font-mono text-[0.6875rem] uppercase tracking-[0.1em] text-text-muted">
              {t('header.resultsCount', { count: resultCount })}
            </span>
          </div>
        </div>
      </header>

      <div className="shrink-0 px-7 pt-[18px]">
        <div className="atelier-pill-tabs inline-flex gap-[2px] rounded-full bg-surface-inset p-[3px]">
          {VIDEO_TABS.map((tabKey) => {
            const active = activeTab === tabKey;
            return (
              <button
                key={tabKey}
                type="button"
                aria-pressed={active}
                onClick={() => selectTab(tabKey)}
                className={[
                  'cursor-pointer rounded-full px-4 py-2 text-center text-[0.8125rem] font-semibold transition-all',
                  active
                    ? 'atelier-pill-tab-active bg-surface text-foreground shadow-[0_2px_8px_rgba(0,0,0,0.4)]'
                    : 'text-text-muted hover:bg-hover-bg hover:text-foreground',
                ].join(' ')}
              >
                {tabKey === 'dance' ? t('dance.cardTitle') : t(`mode.${tabKey}`)}
              </button>
            );
          })}
        </div>
      </div>

      {activeTab === 'dance' ? (
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <DanceSwapWizard />
        </div>
      ) : playgroundStage === 'results' ? (
        <div className="flex flex-1 overflow-hidden min-h-0">
          <aside className="flex w-[420px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-glass-border px-4 py-4 scrollbar-thin">
            <ComposeFields
              t={t}
              showMediaInput={showMediaInput}
              mediaLabelKey={mediaLabelKey}
              hasModel={hasModel}
            />
            <div className="flex-1" />
            <div className="sticky bottom-0 -mx-4 -mb-4 border-t border-glass-border bg-transparent backdrop-blur-md px-4 pb-4 pt-4">
              <CostEstimate />
              <GenerateButton canGenerate={canGenerate} batchSize={batchSize} onClick={handleGenerate} t={t} />
            </div>
          </aside>
          <main className="flex flex-1 flex-col overflow-hidden min-w-0 min-h-0">
            <ResultGallery />
          </main>
        </div>
      ) : (
        <div className="flex flex-1 flex-col overflow-y-auto scrollbar-thin px-7 py-6">
          <div className="mx-auto grid w-full max-w-5xl flex-1 grid-cols-1 gap-5 md:grid-cols-2">
            <ComposeFields t={t} showMediaInput={showMediaInput} mediaLabelKey={mediaLabelKey} hasModel={hasModel} twoCol />
          </div>
          <div className="mx-auto mt-5 w-full max-w-5xl">
            <CostEstimate />
            <GenerateButton canGenerate={canGenerate} batchSize={batchSize} onClick={handleGenerate} t={t} />
          </div>
        </div>
      )}
    </div>
  );
}

function ComposeFields({
  t,
  showMediaInput,
  mediaLabelKey,
  hasModel,
  twoCol = false,
}: {
  t: ReturnType<typeof useTranslations>;
  showMediaInput: boolean;
  mediaLabelKey: string;
  hasModel: boolean;
  twoCol?: boolean;
}) {
  const promptCol = (
    <div className={twoCol ? 'flex flex-col gap-5' : 'contents'}>
      <section className="glass-panel atelier-card rounded-[20px] px-5 py-5">
        <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
          {t('compose.promptLabel')}
        </div>
        <PromptInput />
      </section>

      {showMediaInput && (
        <section className="glass-panel atelier-card rounded-[20px] px-5 py-5">
          <div className="mb-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
            {t(mediaLabelKey)}
          </div>
          <MediaInput />
          <div className="mt-3 flex items-start gap-2 rounded-[10px] border border-[color-mix(in_oklab,var(--color-accent)_20%,transparent)] bg-[color-mix(in_oklab,var(--color-accent)_8%,transparent)] px-3 py-2.5">
            <span className="mt-0.5 text-[0.75rem] leading-none text-accent">●</span>
            <span className="text-[0.75rem] leading-relaxed text-text-secondary">
              {t('videoGen.hint.useGrid')}
            </span>
          </div>
        </section>
      )}
    </div>
  );

  const modelCol = (
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
  );

  if (twoCol) {
    return (
      <>
        <div className="flex flex-col gap-5">{promptCol}</div>
        <div className="flex flex-col gap-5">{modelCol}</div>
      </>
    );
  }

  return (
    <>
      {promptCol}
      {modelCol}
    </>
  );
}

function GenerateButton({
  canGenerate,
  batchSize,
  onClick,
  t,
}: {
  canGenerate: boolean;
  batchSize: number;
  onClick: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!canGenerate}
      className={[
        'inline-flex w-full items-center justify-center gap-[7px] rounded-full px-6 py-[13px]',
        "font-['Space_Grotesk',sans-serif] text-sm font-semibold",
        'bg-primary text-on-accent shadow-[var(--glow-primary)] transition-all duration-150 disabled:opacity-40 disabled:shadow-none',
        canGenerate ? 'hover:bg-primary-hover hover:-translate-y-px cursor-pointer' : 'cursor-not-allowed',
      ].join(' ')}
    >
      <Sparkles size={16} aria-hidden="true" />
      <span>{batchSize > 1 ? t('compose.generateBatch', { count: batchSize }) : t('compose.generate')}</span>
    </button>
  );
}
