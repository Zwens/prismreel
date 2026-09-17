'use client';

import { useTranslations } from 'next-intl';
import { usePlaygroundStore } from './usePlaygroundStore';

/**
 * Checkbox below the prompt textarea, shown only when at least one current
 * input reference is known to carry a baked-in grid overlay (fresh upload
 * with gridSize>0, or a library pick whose selected variant has
 * has_grid_overlay). Appends GRID_OVERLAY_NEGATIVE_PROMPT to the negative
 * prompt on generate — see useGenerationRunner.
 */
export default function GridOverlayNegativeCheckbox() {
  const inputMediaHasGridOverlay = usePlaygroundStore((s) => s.inputMediaHasGridOverlay);
  const appendGridOverlayNegative = usePlaygroundStore((s) => s.appendGridOverlayNegative);
  const setAppendGridOverlayNegative = usePlaygroundStore((s) => s.setAppendGridOverlayNegative);
  const t = useTranslations('playground');

  if (!inputMediaHasGridOverlay.some(Boolean)) return null;

  return (
    <label className="flex items-center gap-[6px] py-[6px] text-[0.6875rem] text-text-muted cursor-pointer hover:text-foreground">
      <input
        type="checkbox"
        checked={appendGridOverlayNegative}
        onChange={(e) => setAppendGridOverlayNegative(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-border-subtle accent-primary"
      />
      <span>{t('prompt.excludeGridOverlay')}</span>
    </label>
  );
}
