"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { getMyUsage, type UsageSummary } from "@/lib/api";

function UsageTable({ summary, kind, title, showCost }: { summary: UsageSummary; kind: string; title: string; showCost: boolean }) {
    const t = useTranslations("usage");
    const providers = summary[kind] || {};
    const rows: { provider: string; model: string; count: number; total_tokens: number | null; cost_usd: number | null }[] = [];
    for (const [provider, models] of Object.entries(providers)) {
        for (const [model, bucket] of Object.entries(models)) {
            rows.push({ provider, model, ...bucket });
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
                        <th className="pb-2">{t("columnCount")}</th>
                        <th className="pb-2">{t("columnTokens")}</th>
                        {showCost && <th className="pb-2">{t("columnCost")}</th>}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r) => (
                        <tr key={`${r.provider}-${r.model}`} className="border-b border-glass-border last:border-0">
                            <td className="py-2">{r.provider}</td>
                            <td className="py-2">{r.model}</td>
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

export default function UsagePage() {
    const t = useTranslations("usage");
    const router = useRouter();
    const [summary, setSummary] = useState<UsageSummary | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getMyUsage()
            .then((data) => setSummary(data.summary))
            .catch(() => router.push("/"))
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
                {summary && (
                    <>
                        <UsageTable summary={summary} kind="llm" title={t("llmSection")} showCost={true} />
                        <UsageTable summary={summary} kind="video" title={t("videoSection")} showCost={true} />
                        <UsageTable summary={summary} kind="image" title={t("otherSection")} showCost={false} />
                    </>
                )}
            </div>
        </div>
    );
}
