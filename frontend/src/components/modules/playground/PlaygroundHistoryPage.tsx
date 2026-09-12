'use client';

import { useEffect, useState } from 'react';
import { playgroundApi } from '@/lib/api';
import { usePlaygroundStore } from './usePlaygroundStore';
import { toGeneration } from './PlaygroundPage';
import ResultGallery from './ResultGallery';

/**
 * 独立的「生成历史」页面 — 直接重用创作台（Playground）results 阶段的
 * ResultGallery（含网格/走廊双检视、筛选、详情面板），跳过 select/compose
 * 两个阶段，避免使用者进入创作台后卡在选模式画面看不到既有历史。
 *
 * 若使用者从未进过创作台，store 里的 history 会是空的，这里独立补一次 fetch。
 */
export default function PlaygroundHistoryPage() {
  const history = usePlaygroundStore((s) => s.history);
  const setHistory = usePlaygroundStore((s) => s.setHistory);
  const [loading, setLoading] = useState(history.length === 0);

  useEffect(() => {
    if (history.length > 0) return;
    playgroundApi.getHistory().then((items) => {
      setHistory(items.map(toGeneration));
    }).catch((err) => {
      console.error('[PlaygroundHistory] Failed to fetch history:', err);
    }).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-text-secondary text-[0.8125rem]">…</div>
      </div>
    );
  }

  return <ResultGallery />;
}
