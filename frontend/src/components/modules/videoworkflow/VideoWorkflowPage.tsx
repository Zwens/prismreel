'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, Sparkles, Film } from 'lucide-react';
import { playgroundApi } from '@/lib/api';
import { mediaUrl } from '@/lib/mediaPath';
import { useShotSequenceStore, MAX_SHOTS } from './useShotSequenceStore';
import { useShotGeneration } from './useShotGeneration';
import ShotCard from './ShotCard';

export default function VideoWorkflowPage() {
  const t = useTranslations('playground.videoWorkflow');
  const shots = useShotSequenceStore((s) => s.shots);
  const addShot = useShotSequenceStore((s) => s.addShot);
  const removeShot = useShotSequenceStore((s) => s.removeShot);
  const { generateShot } = useShotGeneration();

  const [combining, setCombining] = useState(false);
  const [combineError, setCombineError] = useState<string | null>(null);
  const [finalVideoPath, setFinalVideoPath] = useState<string | null>(null);

  const allCompleted = shots.length > 0 && shots.every((s) => s.status === 'completed');
  const atMax = shots.length >= MAX_SHOTS;

  const handleGenerateAll = () => {
    shots.filter((s) => s.status !== 'completed').forEach((s) => generateShot(s));
  };

  const handleCombine = async () => {
    setCombining(true);
    setCombineError(null);
    try {
      const outputPaths = shots.map((s) => s.outputPath!).filter(Boolean);
      const result = await playgroundApi.concat(outputPaths);
      setFinalVideoPath(result.path);
    } catch (err) {
      setCombineError(err instanceof Error ? err.message : String(err));
    } finally {
      setCombining(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto scrollbar-thin px-7 py-6">
      <header className="mb-5">
        <h1 className="atelier-display font-display text-[1.625rem] font-semibold tracking-tight text-foreground">
          {t('pageTitle')}
        </h1>
        <p className="text-sm text-text-secondary mt-1">{t('pageSubtitle')}</p>
      </header>

      <div className="flex flex-col gap-4 max-w-3xl">
        {shots.map((shot, index) => (
          <ShotCard key={shot.id} shot={shot} index={index} onRemove={() => removeShot(shot.id)} />
        ))}

        <button
          type="button"
          onClick={() => addShot()}
          disabled={atMax}
          className="flex items-center justify-center gap-2 rounded-[16px] border border-dashed border-border-subtle py-3 text-sm text-text-secondary hover:text-foreground hover:border-foreground/30 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Plus className="w-4 h-4" />
          {atMax ? t('maxShotsReached', { max: MAX_SHOTS }) : t('addShot')}
        </button>
      </div>

      <div className="sticky bottom-0 mt-6 -mx-7 border-t border-glass-border bg-surface/80 backdrop-blur-md px-7 py-4 flex items-center gap-3 max-w-3xl">
        <button
          type="button"
          onClick={handleGenerateAll}
          className="inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold bg-elevated text-foreground hover:bg-hover-bg"
        >
          <Sparkles className="w-4 h-4" />
          {t('generateAll')}
        </button>

        <button
          type="button"
          onClick={handleCombine}
          disabled={!allCompleted || combining}
          title={!allCompleted ? t('combineRequiresAllCompleted') : undefined}
          className="inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold bg-primary text-on-accent disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary-hover"
        >
          <Film className="w-4 h-4" />
          {combining ? t('combining') : t('combineButton')}
        </button>

        {combineError && <span className="text-xs text-status-failed-fg">{t('combineFailed')}: {combineError}</span>}
      </div>

      {finalVideoPath && (
        <div className="mt-4 max-w-3xl">
          <video src={mediaUrl(finalVideoPath)} controls className="w-full rounded-[16px]" />
        </div>
      )}
    </div>
  );
}
