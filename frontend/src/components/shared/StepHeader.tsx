"use client";
/**
 * StepHeader — 統一 R2V workflow 4 個 step 的 page header（Charcoal v3）。
 *
 * 設計原則：
 *   - **字體分軌**：英文 chrome（eyebrow / ghost number）走 mono；
 *     中文標題 + 副標題走 sans (Inter→PingFang fallback)。
 *     Space Grotesk 在這一層不出現 —— 它的中文 fallback 偏粗，
 *     16px 中文已經足夠"工具焦點"，不需要營銷 hero 尺度。
 *   - **對齊 PrismReel type scale**：標題 16px = display token 上限；
 *     副標題 12px = body-sm；eyebrow 9.5px mono uppercase 0.20em。
 *   - **剋制 progress**：1px hairline + 節點，單色紫，無 glow / 無 pink halo。
 *     僅 current node 有微 ring（紫 10%），是全 panel 唯一的"有色信號"。
 *   - **Trailing slot 由 host 決定**：StepHeader 不知道每個 step 該放什麼操作。
 *     ScriptProcessor 自己塞 [Save / Reparse]；ArtDirection 塞 [Apply]；
 *     VideoAssembly 塞 [Export] —— 各 host 的 business chrome。
 *
 * 用法見 docs/design-mocks/r2v-step-header-atelier-glow.html。
 */
import type { ReactNode } from "react";
import clsx from "clsx";
import { useLocale } from "next-intl";

export interface StepHeaderProps {
    /** 1-based 當前步驟號；驅動 ghost number / eyebrow / progress current 位置。 */
    stepNumber: number;
    /** 總步驟數。R2V workflow 默認 4。 */
    totalSteps?: number;
    /** 左側圓形 chip 裏的 icon —— 調用方傳 lucide icon，size + stroke 由 chip
     *  樣式約束（14px / stroke-1.5），所以 host 直接傳 `<Palette />` 即可。 */
    icon: ReactNode;
    /** 已本地化的 eyebrow 名稱（如 "劇本" / "風格定調" / "分鏡"）。 */
    sectionName: string;
    /** 中文標題（如 "腳本編輯器" / "風格定調" / "故事板" / "時間線組裝"）。 */
    title: string;
    /** 中文副標題（一行點睛說明該 step 在做什麼）。 */
    subtitle: string;
    /** 右側操作 / 統計槽 —— host 自決。空時顯示空白（不要 placeholder）。 */
    trailing?: ReactNode;
    /** 額外 className 注入到外層 panel（僅在特殊 layout 下使用）。 */
    className?: string;
}

export default function StepHeader({
    stepNumber,
    totalSteps = 4,
    icon,
    sectionName,
    title,
    subtitle,
    trailing,
    className,
}: StepHeaderProps) {
    const stepStr = String(stepNumber).padStart(2, "0");
    const isCJK = useLocale() !== "en";

    // Progress bar fill 計算：當前 step 之前的所有 segments 完整填滿，
    // 當前 step 用 current node。totalSteps=4 時，stepNumber=2 → fill 1/3 段。
    // 計算公式：完成段數 = stepNumber - 1，總段數 = totalSteps - 1。
    const progressPercent = totalSteps > 1
        ? Math.max(0, Math.min(1, (stepNumber - 1) / (totalSteps - 1))) * 100
        : 0;

    const nodes = Array.from({ length: totalSteps }, (_, i) => {
        const idx = i + 1;
        if (idx < stepNumber) return "done" as const;
        if (idx === stepNumber) return "current" as const;
        return "future" as const;
    });

    return (
        <div
            className={clsx(
                "relative h-28 w-full overflow-hidden border-b border-glass-border bg-surface",
                "transition-colors duration-base ease-out-quart",
                className,
            )}
        >
            {/* Main row — 留出底部 18px 給 progress rail */}
            <div className="relative z-[1] flex h-[calc(100%-18px)] items-center gap-4 px-6">
                {/* Icon chip — 32×32 圓形，flat dark + 紫 1px border + 內頂部 1px 高光 */}
                <div
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-primary"
                    style={{
                        background: "rgba(100, 108, 255, 0.06)",
                        border: "1px solid rgba(100, 108, 255, 0.32)",
                        boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.05)",
                    }}
                >
                    {/* host 傳的 lucide icon —— size/stroke 由全局 className 約束 */}
                    <span className="grid h-3.5 w-3.5 place-items-center [&>svg]:h-3.5 [&>svg]:w-3.5 [&>svg]:stroke-[1.5]">
                        {icon}
                    </span>
                </div>

                {/* Title block */}
                <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
                    {/* Eyebrow — 01 — 劇本 / 01 — SCRIPT。中文收緊字距並取消
                        uppercase：0.2em 字距會把中文詞拆散。 */}
                    <span className={clsx(
                        "mb-[1px] inline-flex items-center gap-2 font-mono text-[0.59375rem] font-normal leading-tight text-text-muted",
                        isCJK ? "tracking-[0.08em]" : "uppercase tracking-[0.2em]",
                    )}>
                        <span className="font-medium text-primary">{stepStr}</span>
                        <span aria-hidden="true" className="h-px w-3 bg-glass-border" />
                        <span>{sectionName}</span>
                    </span>
                    {/* 中文標題 — Inter Medium 16px (PrismReel display token 上限) */}
                    <span
                        className="text-[1rem] font-medium leading-[1.3] text-foreground"
                        style={{ letterSpacing: 0 }}
                    >
                        {title}
                    </span>
                    {/* 中文副標題 — body-sm 12px text-secondary */}
                    <span
                        className="text-[0.75rem] font-normal leading-[1.4] text-text-secondary"
                        style={{ letterSpacing: 0 }}
                    >
                        {subtitle}
                    </span>
                </div>

                {/* Ghost number — 現在作為 trailing 的視覺前導（inline，不再 absolute
                   背景層），永遠不與 trailing button 重疊。`-my-8` 讓 80px 字號
                   不撐爆 row，pointer-events-none + select-none 保持裝飾性。 */}
                <span
                    aria-hidden="true"
                    className="ml-auto shrink-0 -my-8 select-none pointer-events-none font-mono leading-[0.85] tracking-[-0.05em]"
                    style={{
                        fontSize: "80px",
                        fontWeight: 300,
                        color: "rgba(255, 255, 255, 0.06)",
                    }}
                >
                    {stepStr}
                </span>

                {/* Trailing slot — host 自決，緊貼 ghost number 右側 */}
                {trailing ? <div className="ml-4 z-[2] flex shrink-0 items-center gap-2">{trailing}</div> : null}
            </div>

            {/* Progress rail — 1px hairline + 節點（無 glow / 無 pink） */}
            <div className="absolute bottom-3 left-6 right-6 z-[1] h-1.5">
                <div
                    aria-hidden="true"
                    className="absolute left-1.5 right-1.5 top-1/2 h-px -translate-y-1/2"
                    style={{ background: "rgba(255, 255, 255, 0.06)" }}
                />
                <div
                    aria-hidden="true"
                    className="absolute left-1.5 top-1/2 h-px -translate-y-1/2 bg-primary opacity-55 transition-[width] duration-slow ease-out-quart"
                    style={{ width: `calc((100% - 12px) * ${progressPercent / 100})` }}
                />
                <div className="relative flex h-full items-center justify-between">
                    {nodes.map((kind, i) => (
                        <span
                            key={i}
                            aria-hidden="true"
                            className={clsx(
                                "shrink-0 rounded-full transition-all duration-base ease-out-quart",
                                kind === "done"
                                    ? "h-[5px] w-[5px] border border-primary bg-primary opacity-70"
                                    : kind === "current"
                                        ? "h-[7px] w-[7px] border border-primary bg-primary"
                                        : "h-[5px] w-[5px] border border-foreground/[0.18] bg-transparent opacity-50",
                            )}
                            style={
                                kind === "current"
                                    ? { boxShadow: "0 0 0 3px rgba(100, 108, 255, 0.10)" }
                                    : undefined
                            }
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}
