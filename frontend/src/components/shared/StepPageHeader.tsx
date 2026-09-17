"use client";
/**
 * StepPageHeader — unified mock-aligned page header for every R2V workflow
 * step. Replaces the old Charcoal StepHeader with the Atelier "wb-head"
 * pattern: mono eyebrow (STEP 0N · NAME) + Fraunces display title +
 * optional info pills + subtitle + trailing actions slot.
 *
 * Used by ScriptProcessor / ArtDirection / Cast / StoryboardR2V /
 * VideoAssembly so the whole pipeline reads as one coherent surface.
 *
 * Mock ref: docs/design/tasty-sam/storyboard-r2v-unified.html `.wb-head`.
 */
import type { ReactNode } from "react";
import { useTranslations, useLocale } from "next-intl";
import clsx from "clsx";

export interface StepPageHeaderProps {
    /** 1-based step number; rendered as the primary-colored eyebrow numeral. */
    stepNumber: number;
    /** 已本地化的步驟名（如 "劇本" / "分鏡"）。調用方傳 t(...) 結果。 */
    sectionName: string;
    /** Localized title (Fraunces display). */
    title: string;
    /** Localized subtitle one-liner. */
    subtitle: string;
    /** Info pills row, sits inline with the title (畫風 / 模型 / 計數 …).
     *  Each pill should use the shared capsule style; caller composes them. */
    pills?: ReactNode;
    /** Right-aligned actions (queue button, generate CTA, counters …). */
    trailing?: ReactNode;
}

export default function StepPageHeader({
    stepNumber,
    sectionName,
    title,
    subtitle,
    pills,
    trailing,
}: StepPageHeaderProps) {
    const tp = useTranslations("pipeline");
    const isCJK = useLocale() !== "en";
    return (
        <header className="shrink-0 border-b border-border-subtle px-7 pt-[22px] pb-4">
            <div className="flex items-start gap-5">
                <div className="flex-1 min-w-0">
                    {/* Eyebrow：英文走 mono uppercase + 寬 tracking；中文收緊字距
                        並取消 uppercase —— 0.22em 字距會把中文拆散。 */}
                    <div className={clsx(
                        "font-mono text-[0.59375rem] font-normal text-text-muted",
                        isCJK ? "tracking-[0.08em]" : "uppercase tracking-[0.22em]",
                    )}>
                        <span className="font-medium text-primary">{tp("stepIndex", { number: stepNumber })}</span>
                        <span className="mx-1.5">·</span>
                        <span>{sectionName}</span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-baseline gap-3.5">
                        <h1 className="font-display text-[2.125rem] font-semibold leading-[1.05] tracking-[-0.02em] text-foreground">
                            {title}
                        </h1>
                        {pills ? <div className="flex items-center gap-2">{pills}</div> : null}
                    </div>
                    <p className="mt-1.5 text-[0.8125rem] text-text-secondary">{subtitle}</p>
                </div>
                {trailing ? (
                    <div className="flex items-center gap-2 shrink-0 pt-1">{trailing}</div>
                ) : null}
            </div>
        </header>
    );
}

/** Shared pill capsule — callers compose <Pill key="…" value="…" /> for each
 *  info chip so all steps share one visual. */
export function StepPill({ label, value }: { label: string; value: ReactNode }) {
    return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-glass-border bg-surface-inset px-2.5 py-1 font-mono text-[0.59375rem] text-text-secondary">
            <span className="text-text-muted">{label}</span>
            <span className="text-primary">{value}</span>
        </span>
    );
}
