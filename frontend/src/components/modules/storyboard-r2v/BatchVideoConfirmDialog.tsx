"use client";
/**
 * Confirm gate for「一键生成全部」on the storyboard.
 *
 * Video is the expensive step — a 13-shot run is a real bill — so the plan is
 * shown before a single provider call goes out: how many shots will run, on
 * which model, and exactly which shots were left out and why. Naming the
 * excluded shots here is the point; discovering "07 had no reference images"
 * after the queue drains is too late to be useful.
 */
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Wand2, X } from "lucide-react";
import { useTranslations } from "next-intl";
import type { BatchVideoSkipReason } from "@/lib/batchGeneration";

export interface BatchVideoConfirmShot {
    id: string;
    index: number;
}

export interface BatchVideoConfirmProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: () => void;
    readyCount: number;
    skipped: Array<{ index: number; reason: BatchVideoSkipReason }>;
    modelLabel: string;
    durationSeconds: number;
    concurrency: number;
}

/** Shot numbers read 01, 02 … to match the card headers. */
const pad = (n: number) => String(n + 1).padStart(2, "0");

export default function BatchVideoConfirmDialog({
    isOpen,
    onClose,
    onConfirm,
    readyCount,
    skipped,
    modelLabel,
    durationSeconds,
    concurrency,
}: BatchVideoConfirmProps) {
    const t = useTranslations("storyboardR2V");

    if (typeof document === "undefined") return null;

    // Blockers (the user can act on these) sort above the merely-redundant
    // skips, so a short list stays scannable.
    const blocked = skipped.filter(
        (s) => s.reason === "missing-refs" || s.reason === "missing-first-frame",
    );
    const redundant = skipped.filter(
        (s) => s.reason === "already-generated" || s.reason === "in-flight",
    );

    const reasonLabel = (reason: BatchVideoSkipReason) => t(`batchVideoSkip_${reason}`);

    return createPortal(
        <AnimatePresence>
            {isOpen && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 z-[200] grid place-items-center bg-black/60 backdrop-blur-sm p-6"
                    onClick={onClose}
                >
                    <motion.div
                        initial={{ opacity: 0, scale: 0.97, y: 8 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.97, y: 8 }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-full max-w-lg rounded-xl border border-glass-border bg-surface shadow-2xl"
                    >
                        <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-5 py-4">
                            <div>
                                <h2 className="font-display text-lg font-semibold text-foreground">
                                    {t("batchVideoTitle", { count: readyCount })}
                                </h2>
                                <p className="mt-1 font-mono text-[0.6875rem] uppercase tracking-[0.08em] text-text-muted">
                                    {modelLabel} · {durationSeconds}s · {t("batchVideoPerShot")}
                                </p>
                            </div>
                            <button
                                onClick={onClose}
                                aria-label={t("batchVideoCancel")}
                                className="rounded p-1 text-text-muted transition-colors hover:bg-hover-bg hover:text-foreground"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <div className="space-y-3 px-5 py-4 text-[0.8125rem]">
                            <div className="flex items-center justify-between text-text-secondary">
                                <span>{t("batchVideoConcurrency")}</span>
                                <span className="font-mono text-foreground">{concurrency}</span>
                            </div>

                            {blocked.length > 0 && (
                                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                                    <div className="mb-1.5 flex items-center gap-1.5 text-amber-400">
                                        <AlertTriangle size={13} />
                                        <span className="text-xs font-medium">
                                            {t("batchVideoBlocked", { count: blocked.length })}
                                        </span>
                                    </div>
                                    <ul className="space-y-0.5 text-xs text-text-secondary">
                                        {blocked.map((s) => (
                                            <li key={s.index}>
                                                {t("batchVideoShotNo", { no: pad(s.index) })} — {reasonLabel(s.reason)}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            {redundant.length > 0 && (
                                <p className="text-xs text-text-muted">
                                    {t("batchVideoAlsoSkipped", {
                                        count: redundant.length,
                                        shots: redundant.map((s) => pad(s.index)).join("、"),
                                    })}
                                </p>
                            )}

                            {readyCount === 0 && (
                                <p className="text-xs text-amber-400">{t("batchVideoNothingToRun")}</p>
                            )}
                        </div>

                        <div className="flex items-center justify-end gap-2 border-t border-border-subtle px-5 py-3.5">
                            <button
                                onClick={onClose}
                                className="rounded-md px-3.5 py-2 text-[0.8125rem] text-text-secondary transition-colors hover:bg-hover-bg hover:text-foreground"
                            >
                                {t("batchVideoCancel")}
                            </button>
                            <button
                                onClick={onConfirm}
                                disabled={readyCount === 0}
                                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-[0.8125rem] font-medium text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                <Wand2 size={13} />
                                {t("batchVideoStart")}
                            </button>
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>,
        document.body,
    );
}
