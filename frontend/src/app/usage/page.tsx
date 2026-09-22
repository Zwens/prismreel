"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { getMyUsage, getDeeVidCredits, type UsageSummary, type DeeVidCredits } from "@/lib/api";

function UsageTable({ summary, kind, title, showCost, showSpec }: { summary: UsageSummary; kind: string; title: string; showCost: boolean; showSpec: boolean }) {
    const t = useTranslations("usage");
    const providers = summary[kind] || {};
    const rows: { provider: string; bucketKey: string; model: string; resolution: string | null; input_has_video: boolean | null; duration: number | null; count: number; total_tokens: number | null; cost_usd: number | null }[] = [];
    for (const [provider, models] of Object.entries(providers)) {
        for (const [bucketKey, bucket] of Object.entries(models)) {
            rows.push({ provider, bucketKey, ...bucket });
        }
    }
    if (rows.length === 0) return null;

    return (
        <div className="glass-panel atelier-card p-6 mb-6">
            <h2 className="text-lg font-display mb-3">{title}</h2>
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left border-b border-glass-border">
                        <th className="pb-2">{t("columnProvider")}</th>
                        <th className="pb-2">{t("columnModel")}</th>
                        {showSpec && <th className="pb-2">{t("columnResolution")}</th>}
                        {showSpec && <th className="pb-2">{t("columnMode")}</th>}
                        {showSpec && <th className="pb-2">{t("columnDuration")}</th>}
                        <th className="pb-2">{t("columnCount")}</th>
                        <th className="pb-2">{t("columnTokens")}</th>
                        {showCost && <th className="pb-2">{t("columnCost")}</th>}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r) => (
                        <tr key={`${r.provider}-${r.bucketKey}`} className="border-b border-glass-border last:border-0">
                            <td className="py-2">{r.provider}</td>
                            <td className="py-2">{r.model}</td>
                            {showSpec && <td className="py-2">{r.resolution ?? t("noCostAvailable")}</td>}
                            {showSpec && <td className="py-2">{r.input_has_video == null ? t("noCostAvailable") : r.input_has_video ? t("modeR2v") : t("modeI2v")}</td>}
                            {showSpec && <td className="py-2">{r.duration != null ? t("durationSeconds", { seconds: r.duration }) : t("noCostAvailable")}</td>}
                            <td className="py-2">{r.count}</td>
                            <td className="py-2">{r.total_tokens ?? t("noCostAvailable")}</td>
                            {showCost && (
                                <td className="py-2">
                                    {r.cost_usd != null ? `$${r.cost_usd.toFixed(4)}` : t("noCostAvailable")}
                                </td>
                            )}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function DeeVidCreditsCard({ credits }: { credits: DeeVidCredits }) {
    const t = useTranslations("usage");
    const pct = credits.total > 0 ? Math.min(100, (credits.used / credits.total) * 100) : 0;

    return (
        <div className="glass-panel atelier-card p-6 mb-6">
            <h2 className="text-lg font-display mb-3">{t("deevidCreditsTitle")}</h2>
            <div className="w-full h-2 rounded-full bg-surface-inset overflow-hidden mb-2">
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-sm text-text-secondary">
                {t("deevidCreditsUsed", { used: credits.used, total: credits.total })}
            </p>
            <p className="text-sm text-text-secondary">
                {t("deevidCreditsRemaining", { remaining: credits.remaining })}
            </p>
            <p className="text-xs text-text-muted mt-1">
                {t("deevidCreditsPeriod", { start: credits.period_start, end: credits.period_end })}
            </p>
        </div>
    );
}

export default function UsagePage() {
    const t = useTranslations("usage");
    const router = useRouter();
    const [summary, setSummary] = useState<UsageSummary | null>(null);
    const [deevidCredits, setDeevidCredits] = useState<DeeVidCredits | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.allSettled([getMyUsage(), getDeeVidCredits()])
            .then(([usageResult, creditsResult]) => {
                if (usageResult.status === "fulfilled") {
                    setSummary(usageResult.value.summary);
                } else {
                    router.push("/");
                }
                if (creditsResult.status === "fulfilled") {
                    setDeevidCredits(creditsResult.value);
                }
            })
            .finally(() => setLoading(false));
    }, [router]);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <p className="text-text-secondary">{t("loading")}</p>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-background p-8">
            <div className="max-w-3xl mx-auto space-y-4">
                <div className="flex items-center justify-between">
                    <h1 className="text-2xl font-display">{t("myUsageTitle")}</h1>
                    <button onClick={() => router.push("/")} className="text-primary hover:underline text-sm">
                        {t("backToSettings")}
                    </button>
                </div>
                <p className="text-xs text-text-muted">{t("costEstimateNote")}</p>
                {deevidCredits && <DeeVidCreditsCard credits={deevidCredits} />}
                {summary && (
                    <>
                        <UsageTable summary={summary} kind="llm" title={t("llmSection")} showCost={true} showSpec={false} />
                        <UsageTable summary={summary} kind="video" title={t("videoSection")} showCost={true} showSpec={true} />
                        <UsageTable summary={summary} kind="image" title={t("otherSection")} showCost={false} showSpec={false} />
                    </>
                )}
            </div>
        </div>
    );
}
