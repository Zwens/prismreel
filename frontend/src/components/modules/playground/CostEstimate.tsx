'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Coins } from 'lucide-react';
import { usePlaygroundStore } from './usePlaygroundStore';
import { playgroundApi } from '@/lib/api';

const DEBOUNCE_MS = 400;

/** Pre-generation cost estimate, shown above the generate button.
 *
 * Only Seedance (BytePlus) has a confirmed price table today -- every other
 * provider silently returns priced=false, so this renders nothing for them
 * rather than showing a misleading "no cost" line. */
export default function CostEstimate() {
  const t = useTranslations('playground');
  const mode = usePlaygroundStore((s) => s.mode);
  const modelId = usePlaygroundStore((s) => s.modelId);
  const parameters = usePlaygroundStore((s) => s.parameters);
  const batchSize = usePlaygroundStore((s) => s.batchSize);

  const [estimate, setEstimate] = useState<{ cost_usd?: number; priced: boolean } | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    if (!modelId) {
      setEstimate(null);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const seq = ++requestSeq.current;
    debounceRef.current = setTimeout(() => {
      playgroundApi
        .estimateCost({ mode, model_id: modelId, parameters, batch_size: batchSize })
        .then((resp) => {
          // Drop stale responses from a superseded request.
          if (seq === requestSeq.current) setEstimate(resp);
        })
        .catch(() => {
          if (seq === requestSeq.current) setEstimate(null);
        });
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [mode, modelId, parameters, batchSize]);

  if (!estimate?.priced || typeof estimate.cost_usd !== 'number') return null;

  return (
    <div className="flex items-center justify-center gap-1.5 pb-2 font-mono text-[0.6875rem] text-text-muted">
      <Coins size={12} aria-hidden="true" />
      <span>{t('compose.estimatedCost', { amount: estimate.cost_usd.toFixed(3) })}</span>
    </div>
  );
}
