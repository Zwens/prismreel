'use client';

import { useTranslations } from 'next-intl';
import { usePlaygroundStore, type PlaygroundMode } from './usePlaygroundStore';

const IMAGE_MODES: PlaygroundMode[] = ['t2i', 'i2i'];
const VIDEO_MODES: PlaygroundMode[] = ['t2v', 'i2v', 'r2v', 'v2v'];

/** Pill row for one mode group. Each pill calls setMode; active = store mode. */
function ModeGroup({ groupLabel, modes }: { groupLabel: string; modes: PlaygroundMode[] }) {
  const t = useTranslations('playground');
  const mode = usePlaygroundStore((s) => s.mode);
  const setMode = usePlaygroundStore((s) => s.setMode);

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-mono text-[0.5625rem] uppercase tracking-[0.18em] text-text-muted">
          {groupLabel}
        </span>
        <span className="h-px flex-1 bg-border-subtle atelier-group-line" />
      </div>
      <div className="flex gap-[2px] bg-surface-inset rounded-full p-[3px] atelier-pill-tabs">
        {modes.map((key) => {
          const active = mode === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setMode(key)}
              className={[
                'flex-1 rounded-full px-3 py-1.5 text-[0.6875rem] font-semibold text-center transition-all cursor-pointer',
                active
                  ? 'bg-surface text-foreground shadow-[0_2px_8px_rgba(0,0,0,0.4)] atelier-pill-tab-active'
                  : 'text-text-muted hover:text-foreground hover:bg-hover-bg',
              ].join(' ')}
            >
              {t(`mode.${key}`)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Full image+video picker (both groups). Used where a page still spans all
 *  six modes. `groups` narrows it to just one group's modes for a page that
 *  now owns only one media type (VideoGenPage / ImageGenPage, 2026-09-18). */
export default function ModeSelector({ groups = ['image', 'video'] }: { groups?: Array<'image' | 'video'> }) {
  const t = useTranslations('playground');
  return (
    <div className="space-y-3">
      {groups.includes('image') && <ModeGroup groupLabel={t('mode.groupImage')} modes={IMAGE_MODES} />}
      {groups.includes('video') && <ModeGroup groupLabel={t('mode.groupVideo')} modes={VIDEO_MODES} />}
    </div>
  );
}
