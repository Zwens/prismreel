'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { ImagePlus, Film, X, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { mediaUrl } from '@/lib/mediaPath';
import AssetSourcePicker from '../playground/AssetSourcePicker';
import { useShotSequenceStore, type Shot } from './useShotSequenceStore';
import { useShotGeneration } from './useShotGeneration';

function isVideoPath(path: string): boolean {
  return /\.(mp4|mov|webm|avi|mkv)$/i.test(path);
}

function resolveMediaSrc(path: string): string {
  if (/^(https?:|blob:|data:|\/)/i.test(path)) return path;
  return mediaUrl(path);
}

const MAX_IMAGES = 9;

export default function ShotCard({
  shot,
  index,
  onRemove,
}: {
  shot: Shot;
  index: number;
  onRemove: () => void;
}) {
  const t = useTranslations('playground.videoWorkflow');
  const updateShotPrompt = useShotSequenceStore((s) => s.updateShotPrompt);
  const setShotMedia = useShotSequenceStore((s) => s.setShotMedia);
  const { generateShot } = useShotGeneration();
  const [showPicker, setShowPicker] = useState(false);

  const canAddMoreImages = shot.mediaType !== 'video' && shot.media.length < MAX_IMAGES;
  const canGenerate = shot.prompt.trim().length > 0 && shot.status !== 'queued' && shot.status !== 'processing';

  const handleAssetSelect = (path: string) => {
    const asVideo = isVideoPath(path);
    if (asVideo) {
      setShotMedia(shot.id, [path], 'video');
    } else {
      const nextMedia = shot.mediaType === 'image' ? [...shot.media, path] : [path];
      setShotMedia(shot.id, nextMedia, 'image');
    }
    setShowPicker(false);
  };

  const handleRemoveMedia = (mediaIndex: number) => {
    const nextMedia = shot.media.filter((_, i) => i !== mediaIndex);
    setShotMedia(shot.id, nextMedia, nextMedia.length > 0 ? shot.mediaType : null);
  };

  const handlePromptChange = (value: string) => {
    updateShotPrompt(shot.id, value);
    if (value.endsWith('@')) {
      setShowPicker(true);
    }
  };

  return (
    <div className="glass-panel atelier-card rounded-[20px] px-5 py-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[0.6875rem] font-semibold uppercase tracking-[0.16em] text-text-secondary">
          {t('shotLabel', { index: index + 1 })}
        </span>
        <button type="button" aria-label={t('removeShot')} onClick={onRemove} className="text-text-muted hover:text-foreground">
          <X className="w-4 h-4" />
        </button>
      </div>

      <textarea
        value={shot.prompt}
        onChange={(e) => handlePromptChange(e.target.value)}
        placeholder={t('promptPlaceholder')}
        rows={3}
        className="w-full rounded-[12px] border border-border-subtle bg-input-bg px-3 py-2 text-sm text-foreground placeholder:text-text-muted focus:outline-none focus:border-primary"
      />

      <div className="flex flex-wrap gap-2">
        {shot.media.map((path, i) => (
          <div key={path + i} className="group relative w-20 h-20 rounded-[12px] overflow-hidden bg-elevated border border-border-subtle">
            {isVideoPath(path) ? (
              <video src={resolveMediaSrc(path)} className="w-full h-full object-cover" muted />
            ) : (
              <img src={resolveMediaSrc(path)} alt="" className="w-full h-full object-cover" />
            )}
            <button
              type="button"
              onClick={() => handleRemoveMedia(i)}
              className="absolute top-1 right-1 w-4 h-4 rounded-full bg-black/70 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}

        {canAddMoreImages && (
          <button
            type="button"
            onClick={() => setShowPicker(true)}
            className="w-20 h-20 rounded-[12px] bg-input-bg border border-dashed border-border-subtle flex items-center justify-center text-text-muted hover:text-foreground hover:border-foreground/30 hover:bg-hover-bg transition-colors"
          >
            {shot.mediaType === 'video' ? <Film className="w-5 h-5" /> : <ImagePlus className="w-5 h-5" />}
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={() => setShowPicker(true)}
        className="self-start text-xs text-text-secondary hover:text-foreground underline"
      >
        {t('pickFromLibrary')}
      </button>

      <AssetSourcePicker isOpen={showPicker} onClose={() => setShowPicker(false)} onSelect={handleAssetSelect} accept="all" />

      <div className="flex items-center justify-between mt-1">
        <StatusBadge status={shot.status} error={shot.error} t={t} />
        <button
          type="button"
          onClick={() => generateShot(shot)}
          disabled={!canGenerate}
          className="rounded-full px-4 py-2 text-xs font-semibold bg-primary text-on-accent disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary-hover"
        >
          {t('generateShot')}
        </button>
      </div>
    </div>
  );
}

function StatusBadge({
  status,
  error,
  t,
}: {
  status: Shot['status'];
  error?: string;
  t: ReturnType<typeof useTranslations>;
}) {
  if (status === 'processing' || status === 'queued') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-text-secondary">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> {t('statusProcessing')}
      </span>
    );
  }
  if (status === 'completed') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-status-completed-fg">
        <CheckCircle2 className="w-3.5 h-3.5" /> {t('statusCompleted')}
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-status-failed-fg" title={error}>
        <AlertCircle className="w-3.5 h-3.5" /> {t('statusFailed')}
      </span>
    );
  }
  return <span className="text-xs text-text-muted">{t('statusIdle')}</span>;
}
