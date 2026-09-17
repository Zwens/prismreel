'use client';

import { useEffect, useState } from 'react';
import { playgroundApi } from '@/lib/api';
import { usePlaygroundStore } from './usePlaygroundStore';
import { toGeneration } from './useGenerationRunner';
import ResultGallery from './ResultGallery';

/**
 * 獨立的「生成歷史」頁面 — 直接重用創作臺（Playground）results 階段的
 * ResultGallery（含網格/走廊雙檢視、篩選、詳情面板），跳過 select/compose
 * 兩個階段，避免使用者進入創作臺後卡在選模式畫面看不到既有歷史。
 *
 * 若使用者從未進過創作臺，store 裏的 history 會是空的，這裏獨立補一次 fetch。
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
