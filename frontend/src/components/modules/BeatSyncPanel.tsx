"use client";

import React, { useState } from "react";
import { Activity, Loader2, Minus, Plus, RotateCcw } from "lucide-react";

import { api, BeatAnalysis, BeatShot } from "@/lib/api";

interface BeatSyncPanelProps {
    scriptId: string | null;
    hasBgm: boolean;
    onTrimsChanged?: () => void;
}

/** 一个镜头当前占了几拍。未裁剪时按原始时长折算。 */
function beatsOf(shot: BeatShot, interval: number): number {
    if (interval <= 0) return 0;
    return Math.max(1, Math.round((shot.trim_end_s ?? shot.source_duration_s) / interval));
}

/**
 * 卡点面板：检测 BPM、一键把所有镜头对齐到整数拍、逐镜微调拍数。
 *
 * BPM 做成可编辑的输入框而不是只读结果，是因为测速存在倍频歧义
 * （实测 128 BPM 的点击轨会被读成 63.8）。×2 / ÷2 是针对这个失败模式的
 * 直接补救，比让用户手敲数字快。
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
            setError(e instanceof Error ? e.message : "节拍检测失败");
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
            setError(e instanceof Error ? e.message : "按节拍对齐失败");
        } finally {
            setBusy(false);
        }
    };

    const nudge = async (shot: BeatShot, delta: number) => {
        if (!scriptId || interval <= 0) return;
        const next = beatsOf(shot, interval) + delta;
        if (next < 1) return;
        const seconds = next * interval;
        // 只能剪短——渲染没有补帧的能力，超过原片长的目标会被后端忽略，
        // 与其发一个注定被丢弃的请求，不如在这里就拦住。
        if (seconds > shot.source_duration_s + 1e-6) return;

        setBusy(true);
        setError(null);
        try {
            await api.updateFrameTrims(scriptId, { [shot.frame_id]: seconds });
            await refreshShots();
        } catch (e) {
            setError(e instanceof Error ? e.message : "保存失败");
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
            setError(e instanceof Error ? e.message : "清除失败");
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
                卡点 · 按节拍对齐
                {busy && <Loader2 size={12} className="animate-spin text-primary" />}
            </h3>

            {!hasBgm ? (
                <p className="text-xs text-text-muted">
                    先在上方选择或上传 BGM，才能检测节拍。
                </p>
            ) : !analysis ? (
                <button
                    onClick={detect}
                    disabled={busy || !scriptId}
                    className="text-xs px-3 py-1.5 rounded-lg border border-glass-border bg-glass text-text-secondary hover:text-foreground hover:border-foreground/30 transition-colors disabled:opacity-50"
                >
                    检测 BGM 节拍
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
                            title="测速常见的倍频误判：如果画面切得太密，试试减半"
                        >
                            ÷2
                        </button>
                        <button
                            onClick={() => bpm && setBpm(Number((bpm * 2).toFixed(2)))}
                            className="text-xs px-2 py-1 rounded border border-glass-border text-text-secondary hover:text-foreground transition-colors"
                            title="如果画面切得太慢，试试加倍"
                        >
                            ×2
                        </button>
                        <span className="text-[0.6875rem] text-text-muted">
                            检测值 {analysis.bpm} · 一拍 {interval > 0 ? interval.toFixed(3) : "—"}s
                        </span>
                    </div>

                    <div className="flex items-center gap-2">
                        <button
                            onClick={alignAll}
                            disabled={busy || !bpm}
                            className="text-xs px-3 py-1.5 rounded-lg bg-primary/15 border border-primary/40 text-primary hover:bg-primary/25 transition-colors disabled:opacity-50"
                        >
                            按节拍对齐全部镜头
                        </button>
                        <button
                            onClick={clearAll}
                            disabled={busy || trimmedCount === 0}
                            className="text-xs px-3 py-1.5 rounded-lg border border-glass-border text-text-secondary hover:text-foreground transition-colors disabled:opacity-50 flex items-center gap-1"
                        >
                            <RotateCcw size={11} /> 还原
                        </button>
                        <span className="text-[0.6875rem] text-text-muted">
                            {trimmedCount}/{shots.length} 镜已裁剪 · 合计 {totalS.toFixed(2)}s
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
                                        title="减一拍"
                                    >
                                        <Minus size={11} />
                                    </button>
                                    <span className="w-12 text-center text-primary">×{beats} 拍</span>
                                    <button
                                        onClick={() => nudge(shot, +1)}
                                        disabled={busy || !canGrow}
                                        className="p-1 rounded hover:bg-glass text-text-secondary disabled:opacity-30"
                                        title={canGrow ? "加一拍" : "再加就超过原片长了——渲染只能剪短，不能补帧"}
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
