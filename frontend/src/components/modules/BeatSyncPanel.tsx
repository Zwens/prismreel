"use client";

import React, { useState } from "react";
import { Activity, Loader2, Minus, Plus, RotateCcw } from "lucide-react";

import { api, BeatAnalysis, BeatShot } from "@/lib/api";

interface BeatSyncPanelProps {
    scriptId: string | null;
    hasBgm: boolean;
    onTrimsChanged?: () => void;
}

/** 一個鏡頭當前佔了幾拍。未裁剪時按原始時長折算。 */
function beatsOf(shot: BeatShot, interval: number): number {
    if (interval <= 0) return 0;
    return Math.max(1, Math.round((shot.trim_end_s ?? shot.source_duration_s) / interval));
}

/**
 * 卡點面板：偵測 BPM、一鍵把所有鏡頭對齊到整數拍、逐鏡微調拍數。
 *
 * BPM 做成可編輯的輸入框而不是唯讀結果，是因為測速存在倍頻歧義
 * （實測 128 BPM 的點擊軌會被讀成 63.8）。×2 / ÷2 是針對這個失敗模式的
 * 直接補救，比讓使用者手敲數字快。
 */
const BeatSyncPanel: React.FC<BeatSyncPanelProps> = ({ scriptId, hasBgm, onTrimsChanged }) => {
    const [analysis, setAnalysis] = useState<BeatAnalysis | null>(null);
    const [bpm, setBpm] = useState<number | null>(null);
    const [shots, setShots] = useState<BeatShot[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const interval = bpm && bpm > 0 ? 60 / bpm : 0;

    const detect = async () => {
        if (!scriptId) return;
        setBusy(true);
        setError(null);
        try {
            const result = await api.analyzeBeats(scriptId);
            setAnalysis(result);
            setBpm(result.bpm);
            setShots(result.shots);
        } catch (e) {
            setError(e instanceof Error ? e.message : "節拍偵測失敗");
        } finally {
            setBusy(false);
        }
    };

    const refreshShots = async () => {
        if (!scriptId) return;
        const result = await api.analyzeBeats(scriptId);
        setShots(result.shots);
        onTrimsChanged?.();
    };

    const alignAll = async () => {
        if (!scriptId || !bpm) return;
        setBusy(true);
        setError(null);
        try {
            await api.alignBeats(scriptId, bpm);
            await refreshShots();
        } catch (e) {
            setError(e instanceof Error ? e.message : "按節拍對齊失敗");
        } finally {
            setBusy(false);
        }
    };

    const nudge = async (shot: BeatShot, delta: number) => {
        if (!scriptId || interval <= 0) return;
        const next = beatsOf(shot, interval) + delta;
        if (next < 1) return;
        const seconds = next * interval;
        // 只能剪短——渲染沒有補幀的能力，超過原片長的目標會被後端忽略，
        // 與其發一個註定被丟棄的請求，不如在這裡就攔住。
        if (seconds > shot.source_duration_s + 1e-6) return;

        setBusy(true);
        setError(null);
        try {
            await api.updateFrameTrims(scriptId, { [shot.frame_id]: seconds });
            await refreshShots();
        } catch (e) {
            setError(e instanceof Error ? e.message : "保存失敗");
        } finally {
            setBusy(false);
        }
    };

    const clearAll = async () => {
        if (!scriptId || shots.length === 0) return;
        setBusy(true);
        setError(null);
        try {
            const cleared: Record<string, number | null> = {};
            shots.forEach(s => { cleared[s.frame_id] = null; });
            await api.updateFrameTrims(scriptId, cleared);
            await refreshShots();
        } catch (e) {
            setError(e instanceof Error ? e.message : "清除失敗");
        } finally {
            setBusy(false);
        }
    };

    const trimmedCount = shots.filter(s => s.trim_end_s != null).length;
    const totalS = shots.reduce((sum, s) => sum + (s.trim_end_s ?? s.source_duration_s), 0);

    return (
        <section>
            <h3 className="mb-3 flex items-center gap-2 font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-text-muted">
                <Activity size={12} className="text-primary" />
                卡點 · 按節拍對齊
                {busy && <Loader2 size={12} className="animate-spin text-primary" />}
            </h3>

            {!hasBgm ? (
                <p className="text-xs text-text-muted">
                    先在上方選擇或上傳 BGM，才能偵測節拍。
                </p>
            ) : !analysis ? (
                <button
                    onClick={detect}
                    disabled={busy || !scriptId}
                    className="text-xs px-3 py-1.5 rounded-lg border border-glass-border bg-glass text-text-secondary hover:text-foreground hover:border-foreground/30 transition-colors disabled:opacity-50"
                >
                    偵測 BGM 節拍
                </button>
            ) : (
                <div className="space-y-4">
                    <div className="flex items-center gap-2 flex-wrap">
                        <label className="text-xs text-text-secondary">BPM</label>
                        <input
                            type="number"
                            value={bpm ?? ""}
                            min={20}
                            max={400}
                            step={0.01}
                            onChange={(e) => {
                                const v = parseFloat(e.target.value);
                                setBpm(Number.isFinite(v) && v > 0 ? v : null);
                            }}
                            className="glass-input w-24 px-2 py-1 text-xs bg-transparent border border-glass-border rounded"
                        />
                        <button
                            onClick={() => bpm && setBpm(Number((bpm / 2).toFixed(2)))}
                            className="text-xs px-2 py-1 rounded border border-glass-border text-text-secondary hover:text-foreground transition-colors"
                            title="測速常見的倍頻誤判：如果畫面切得太密，試試減半"
                        >
                            ÷2
                        </button>
                        <button
                            onClick={() => bpm && setBpm(Number((bpm * 2).toFixed(2)))}
                            className="text-xs px-2 py-1 rounded border border-glass-border text-text-secondary hover:text-foreground transition-colors"
                            title="如果畫面切得太慢，試試加倍"
                        >
                            ×2
                        </button>
                        <span className="text-[0.6875rem] text-text-muted">
                            偵測值 {analysis.bpm} · 一拍 {interval > 0 ? interval.toFixed(3) : "—"}s
                        </span>
                    </div>

                    <div className="flex items-center gap-2">
                        <button
                            onClick={alignAll}
                            disabled={busy || !bpm}
                            className="text-xs px-3 py-1.5 rounded-lg bg-primary/15 border border-primary/40 text-primary hover:bg-primary/25 transition-colors disabled:opacity-50"
                        >
                            按節拍對齊全部鏡頭
                        </button>
                        <button
                            onClick={clearAll}
                            disabled={busy || trimmedCount === 0}
                            className="text-xs px-3 py-1.5 rounded-lg border border-glass-border text-text-secondary hover:text-foreground transition-colors disabled:opacity-50 flex items-center gap-1"
                        >
                            <RotateCcw size={11} /> 還原
                        </button>
                        <span className="text-[0.6875rem] text-text-muted">
                            {trimmedCount}/{shots.length} 鏡已裁剪 · 合計 {totalS.toFixed(2)}s
                        </span>
                    </div>

                    {error && (
                        <p className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2">
                            {error}
                        </p>
                    )}

                    <div className="space-y-1 max-h-64 overflow-y-auto custom-scrollbar">
                        {shots.map((shot, i) => {
                            const beats = beatsOf(shot, interval);
                            const effective = shot.trim_end_s ?? shot.source_duration_s;
                            const canGrow = (beats + 1) * interval <= shot.source_duration_s + 1e-6;
                            return (
                                <div
                                    key={shot.frame_id}
                                    className="flex items-center gap-2 text-xs px-2 py-1.5 rounded border border-glass-border/60"
                                >
                                    <span className="w-8 text-text-muted">#{i + 1}</span>
                                    <span className="flex-1 text-text-secondary">
                                        {effective.toFixed(2)}s
                                        {shot.trim_end_s != null && (
                                            <span className="text-text-muted">
                                                {" "}/ 原 {shot.source_duration_s.toFixed(2)}s
                                            </span>
                                        )}
                                    </span>
                                    <button
                                        onClick={() => nudge(shot, -1)}
                                        disabled={busy || beats <= 1}
                                        className="p-1 rounded hover:bg-glass text-text-secondary disabled:opacity-30"
                                        title="減一拍"
                                    >
                                        <Minus size={11} />
                                    </button>
                                    <span className="w-12 text-center text-primary">×{beats} 拍</span>
                                    <button
                                        onClick={() => nudge(shot, +1)}
                                        disabled={busy || !canGrow}
                                        className="p-1 rounded hover:bg-glass text-text-secondary disabled:opacity-30"
                                        title={canGrow ? "加一拍" : "再加就超過原片長了——渲染只能剪短，不能補幀"}
                                    >
                                        <Plus size={11} />
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </section>
    );
};

export default BeatSyncPanel;
