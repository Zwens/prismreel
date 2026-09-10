'use client';

import { useTranslations } from 'next-intl';
import { Type, ImagePlus, Clapperboard, Film, Layers, Scissors, type LucideIcon } from 'lucide-react';
import { usePlaygroundStore, type PlaygroundMode } from './usePlaygroundStore';

const MODE_ICONS: Record<PlaygroundMode, LucideIcon> = {
  t2i: Type,
  i2i: ImagePlus,
  t2v: Clapperboard,
  i2v: Film,
  r2v: Layers,
  v2v: Scissors,
};

const IMAGE_MODES: PlaygroundMode[] = ['t2i', 'i2i'];
const VIDEO_MODES: PlaygroundMode[] = ['t2v', 'i2v', 'r2v', 'v2v'];

export default function ModeCardSelector() {
  const t = useTranslations('playground');
  const setMode = usePlaygroundStore((s) => s.setMode);
  const setPlaygroundStage = usePlaygroundStore((s) => s.setPlaygroundStage);

  const selectMode = (key: PlaygroundMode) => {
    setMode(key);
    setPlaygroundStage('compose');
  };

  const renderCard = (key: PlaygroundMode) => {
    const Icon = MODE_ICONS[key];
    return (
      <button
        key={key}
        type="button"
        onClick={() => selectMode(key)}
        className="glass-panel atelier-card group flex flex-col items-start gap-3 rounded-[20px] px-6 py-6 text-left transition-all hover:-translate-y-0.5 hover:shadow-[var(--glow-primary)] cursor-pointer"
      >
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-surface-inset text-primary transition-colors group-hover:bg-primary group-hover:text-on-accent">
          <Icon size={20} aria-hidden="true" />
        </span>
        <span className="font-display text-[1.0625rem] font-semibold tracking-tight text-foreground">
          {t(`modeCard.${key}.title`)}
        </span>
        <span className="font-mono text-[0.75rem] leading-relaxed text-text-muted">
          {t(`modeCard.${key}.description`)}
        </span>
      </button>
    );
  };

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-6 py-10">
      <div className="flex flex-col gap-1 text-center">
        <h2 className="font-display text-[1.5rem] font-semibold tracking-tight text-foreground">
          {t('modeCard.heading')}
        </h2>
        <p className="font-mono text-[0.75rem] text-text-muted">{t('modeCard.subheading')}</p>
      </div>

      <div className="flex flex-col gap-6">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
              {t('mode.groupImage')}
            </span>
            <span className="h-px flex-1 bg-border-subtle atelier-group-line" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{IMAGE_MODES.map(renderCard)}</div>
        </div>

        <div>
          <div className="mb-3 flex items-center gap-2">
            <span className="font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
              {t('mode.groupVideo')}
            </span>
            <span className="h-px flex-1 bg-border-subtle atelier-group-line" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{VIDEO_MODES.map(renderCard)}</div>
        </div>
      </div>
    </div>
  );
}
