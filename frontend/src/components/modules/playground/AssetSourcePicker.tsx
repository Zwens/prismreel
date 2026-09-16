'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Check, Image as ImageIcon, Film, Loader2, Layers, LayoutGrid, Clapperboard, History } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { api, playgroundApi } from '@/lib/api';
import { mediaUrl } from '@/lib/mediaPath';
import { resolveAssetMedia } from '@/lib/assetImageResolver';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** The four places a user's existing media can come from. Replaces the
 *  history-only AssetPickerModal, which could not reach anything the user had
 *  built in the library, a series or a storyboard. */
export type AssetSource = 'library' | 'series' | 'project' | 'history';

interface AssetSourcePickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  accept: 'image' | 'video' | 'all';
}

interface PickerItem {
  key: string;
  path: string;
  type: 'image' | 'video';
  label: string;
}

/** A series or project the user drills into before seeing its assets. */
interface Container {
  id: string;
  title: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fileName(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}

/** Display URL. Mirrors lib/utils getAssetUrl — OSS records are already
 *  absolute, locally produced ones are output-relative. */
function toDisplayUrl(path: string): string {
  return mediaUrl(path);
}

/** Characters / scenes / props of one container, in a stable display order. */
function itemsFromAssetBag(
  bag: { characters?: any[]; scenes?: any[]; props?: any[] } | null | undefined,
  keyPrefix: string,
): PickerItem[] {
  if (!bag) return [];
  const groups = [
    { kind: 'character' as const, list: bag.characters ?? [] },
    { kind: 'scene' as const, list: bag.scenes ?? [] },
    { kind: 'prop' as const, list: bag.props ?? [] },
  ];

  const items: PickerItem[] = [];
  for (const { kind, list } of groups) {
    for (const asset of list) {
      const resolved = resolveAssetMedia(asset, kind);
      // An asset whose image has not been generated yet is dropped rather than
      // rendered as a tile that would resolve to an empty src.
      if (!resolved) continue;
      items.push({
        key: `${keyPrefix}-${kind}-${asset.id}`,
        path: resolved.path,
        type: resolved.type,
        label: asset.name || asset.id,
      });
    }
  }
  return items;
}

// ---------------------------------------------------------------------------
// Animation
// ---------------------------------------------------------------------------

const overlayVariants = { hidden: { opacity: 0 }, visible: { opacity: 1 } };
const modalVariants = {
  hidden: { opacity: 0, scale: 0.95, y: 16 },
  visible: { opacity: 1, scale: 1, y: 0 },
};
const springModal = { type: 'spring' as const, stiffness: 400, damping: 30 };

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AssetSourcePicker({
  isOpen,
  onClose,
  onSelect,
  accept,
}: AssetSourcePickerProps) {
  const t = useTranslations('playground.assetSourcePicker');

  // Character / scene / prop / storyboard sources only ever hold stills, so a
  // video-only slot is left with history as its single meaningful source.
  const sources: AssetSource[] = useMemo(
    () => (accept === 'video' ? ['history'] : ['library', 'series', 'project', 'history']),
    [accept],
  );

  const [activeSource, setActiveSource] = useState<AssetSource>(sources[0]);
  const [items, setItems] = useState<PickerItem[]>([]);
  const [containers, setContainers] = useState<Container[]>([]);
  const [pickedContainerId, setPickedContainerId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  /** listSeries() embeds each series' assets; kept so drilling in is instant. */
  const [seriesCache, setSeriesCache] = useState<any[]>([]);

  useEffect(() => {
    setActiveSource(sources[0]);
  }, [sources]);

  // -------------------------------------------------------------------------
  // Loading — per source, on demand.
  //
  // Deliberately lazy: opening the picker for a first frame should not pull the
  // generation history, and drilling into one series should not fetch them all.
  // -------------------------------------------------------------------------

  const loadSource = useCallback(async (source: AssetSource) => {
    setLoading(true);
    setFailed(false);
    setItems([]);
    setContainers([]);
    setPickedContainerId(null);
    try {
      if (source === 'library') {
        const pool = await api.listLibraryAssets();
        setItems(itemsFromAssetBag(pool, 'global'));
      } else if (source === 'series') {
        // listSeries already embeds each series' assets, so drilling in costs
        // no extra request.
        const list = await api.listSeries();
        setContainers((list ?? []).map((s: any) => ({ id: s.id, title: s.title })));
        setSeriesCache(list ?? []);
      } else if (source === 'project') {
        const list = await api.getProjects();
        setContainers((list ?? []).map((p: any) => ({ id: p.id, title: p.title })));
      } else {
        const history = await playgroundApi.getHistory(100, 0);
        const seen = new Set<string>();
        const collected: PickerItem[] = [];
        for (const gen of history ?? []) {
          if (gen.status !== 'completed') continue;
          for (const output of gen.outputs ?? []) {
            const resolved = resolveAssetMedia(output, 'generation');
            if (!resolved || seen.has(resolved.path)) continue;
            seen.add(resolved.path);
            collected.push({
              key: `out-${output.id}`,
              path: resolved.path,
              type: resolved.type,
              label: fileName(resolved.path),
            });
          }
          for (const inputPath of gen.input_media ?? []) {
            const resolved = resolveAssetMedia({ media_path: inputPath }, 'generation');
            if (!resolved || seen.has(resolved.path)) continue;
            seen.add(resolved.path);
            collected.push({
              key: `in-${resolved.path}`,
              path: resolved.path,
              type: resolved.type,
              label: fileName(resolved.path),
            });
          }
        }
        setItems(collected);
      }
    } catch (err) {
      console.error('[AssetSourcePicker] load failed:', source, err);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    setSelected(null);
    loadSource(activeSource);
  }, [isOpen, activeSource, loadSource]);

  // Escape closes, matching every other modal in the app.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  // -------------------------------------------------------------------------
  // Drill-in
  // -------------------------------------------------------------------------

  const pickContainer = useCallback(
    async (id: string) => {
      setPickedContainerId(id);
      setSelected(null);
      if (activeSource === 'series') {
        const series = seriesCache.find((s: any) => s.id === id);
        setItems(itemsFromAssetBag(series, `series-${id}`));
        return;
      }
      setLoading(true);
      setFailed(false);
      try {
        const project = await api.getProject(id);
        const frames = project?.frames ?? [];
        const collected: PickerItem[] = [];
        frames.forEach((frame: any, index: number) => {
          const resolved = resolveAssetMedia(frame, 'frame');
          if (!resolved) return;
          collected.push({
            key: `frame-${frame.id}`,
            path: resolved.path,
            type: resolved.type,
            label: `${t('shotLabel', { index: index + 1 })} · ${frame.id}`,
          });
        });
        setItems(collected);
      } catch (err) {
        console.error('[AssetSourcePicker] project load failed:', id, err);
        setFailed(true);
      } finally {
        setLoading(false);
      }
    },
    [activeSource, seriesCache, t],
  );

  // -------------------------------------------------------------------------
  // Filtering
  // -------------------------------------------------------------------------

  const visibleItems = useMemo(
    () => (accept === 'all' ? items : items.filter((i) => i.type === accept)),
    [items, accept],
  );

  const needsContainer = activeSource === 'series' || activeSource === 'project';
  const showGrid = !needsContainer || pickedContainerId !== null;

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  const handleConfirm = () => {
    if (!selected) return;
    onSelect(selected);
    onClose();
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const SOURCE_ICON: Record<AssetSource, typeof Layers> = {
    library: Layers,
    series: LayoutGrid,
    project: Clapperboard,
    history: History,
  };
  const SOURCE_LABEL: Record<AssetSource, string> = {
    library: t('tabLibrary'),
    series: t('tabSeries'),
    project: t('tabProject'),
    history: t('tabHistory'),
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          variants={overlayVariants}
          initial="hidden"
          animate="visible"
          exit="hidden"
          transition={{ duration: 0.2 }}
          onClick={handleBackdropClick}
        >
          <motion.div
            className="w-[min(1120px,92vw)] h-[min(760px,86vh)] bg-elevated border border-glass-border rounded-2xl shadow-2xl flex flex-col overflow-hidden"
            variants={modalVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={springModal}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-6 py-5 border-b border-glass-border flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center">
                  <ImageIcon size={16} className="text-primary" />
                </div>
                <h2 className="text-[0.9375rem] font-semibold text-foreground">{t('title')}</h2>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label={t('close')}
                className="grid h-8 w-8 place-items-center rounded-lg text-text-muted transition-colors hover:bg-hover-bg hover:text-foreground"
              >
                <X size={16} />
              </button>
            </div>

            {/* Source tabs */}
            <div role="tablist" className="flex items-center gap-1.5 px-6 pt-4 pb-2 shrink-0">
              {sources.map((source) => {
                const Icon = SOURCE_ICON[source];
                const active = activeSource === source;
                return (
                  <button
                    key={source}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setActiveSource(source)}
                    className={[
                      'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[0.6875rem] font-medium transition-all border',
                      active
                        ? 'text-primary bg-primary/15 border-primary/30'
                        : 'text-text-muted hover:text-foreground hover:bg-hover-bg border-transparent',
                    ].join(' ')}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {SOURCE_LABEL[source]}
                  </button>
                );
              })}
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-6 pb-2 min-h-0">
              {/* Container chooser for series / project */}
              {needsContainer && !loading && !failed && (
                <div className="flex flex-wrap gap-1.5 pb-3">
                  {containers.length === 0 && (
                    <span className="text-xs text-text-muted py-2">
                      {activeSource === 'series' ? t('noSeries') : t('noProject')}
                    </span>
                  )}
                  {containers.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => pickContainer(c.id)}
                      className={[
                        'px-3 py-1.5 rounded-full text-[0.6875rem] font-medium transition-all border',
                        pickedContainerId === c.id
                          ? 'text-primary bg-primary/15 border-primary/30'
                          : 'text-text-secondary hover:text-foreground hover:bg-hover-bg border-border-subtle',
                      ].join(' ')}
                    >
                      {c.title}
                    </button>
                  ))}
                </div>
              )}

              {loading && (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <Loader2 className="w-6 h-6 text-text-muted animate-spin" />
                  <span className="text-xs text-text-muted">{t('loading')}</span>
                </div>
              )}

              {failed && !loading && (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <span className="text-xs text-status-failed-fg">{t('loadFailed')}</span>
                  <button
                    type="button"
                    onClick={() => loadSource(activeSource)}
                    className="text-xs text-primary hover:underline"
                  >
                    {t('retry')}
                  </button>
                </div>
              )}

              {!loading && !failed && needsContainer && !showGrid && containers.length > 0 && (
                <div className="flex items-center justify-center py-16">
                  <span className="text-xs text-text-muted">
                    {activeSource === 'series' ? t('pickSeries') : t('pickProject')}
                  </span>
                </div>
              )}

              {!loading && !failed && showGrid && visibleItems.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 gap-2">
                  <ImageIcon className="w-8 h-8 text-text-muted" />
                  <span className="text-xs text-text-muted">{t('empty')}</span>
                </div>
              )}

              {!loading && !failed && showGrid && visibleItems.length > 0 && (
                <div role="listbox" className="grid grid-cols-5 gap-3 2xl:grid-cols-6">
                  {visibleItems.map((item) => {
                    const isSelected = selected === item.path;
                    const url = toDisplayUrl(item.path);
                    return (
                      <button
                        key={item.key}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        aria-label={item.label}
                        onClick={() => setSelected(isSelected ? null : item.path)}
                        className={[
                          'relative aspect-square rounded-lg overflow-hidden bg-glass cursor-pointer transition-all duration-150',
                          isSelected
                            ? 'border-2 border-primary ring-2 ring-primary/30'
                            : 'border border-border-subtle hover:border-primary/50',
                        ].join(' ')}
                      >
                        {item.type === 'video' ? (
                          <video src={url} className="w-full h-full object-cover" muted preload="metadata" />
                        ) : (
                          <img src={url} alt="" className="w-full h-full object-cover" loading="lazy" />
                        )}

                        {item.type === 'video' && (
                          <div className="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded bg-black/60 backdrop-blur-sm">
                            <Film className="w-3 h-3 text-foreground/80" />
                          </div>
                        )}

                        {isSelected && (
                          <div className="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                            <Check className="w-3 h-3 text-on-accent" />
                          </div>
                        )}

                        <div className="absolute bottom-0 left-0 right-0 px-1.5 py-1 bg-gradient-to-t from-black/70 to-transparent">
                          <span className="text-[0.625rem] text-foreground/80 truncate block">
                            {item.label}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-glass-border">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-xs text-text-secondary hover:text-foreground hover:bg-hover-bg transition-colors"
              >
                {t('cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                disabled={!selected}
                className={[
                  'inline-flex items-center gap-[7px] px-4 py-2 rounded-full text-xs font-medium transition-all',
                  selected
                    ? 'bg-primary text-on-accent shadow-[var(--glow-primary)] hover:bg-primary-hover hover:-translate-y-px'
                    : 'bg-elevated text-text-muted cursor-not-allowed',
                ].join(' ')}
              >
                <Check className="w-3.5 h-3.5" />
                {t('select')}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
