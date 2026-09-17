"use client";
/**
 * PolishPanel — Storyboard R2V workbench 的 AI 提示詞潤色面板。
 *
 * 重構 (#114) 後的核心約定：
 *   - 後端 fallback 不再靜默 (#117)：失敗拋 HTTP 502 + {reason, message_zh/en, prompt_cn?, prompt_en?}
 *   - 雙語錨點迭代 (#119)：feedback 時傳 prev_cn 讓模型用 CN 錨點定位反饋意圖
 *   - UX (#118)：
 *     · 每欄獨立 [📋 Copy] [↩ Apply]（頂部不再有總 Apply）
 *     · Loading 立即上 skeleton + spinner（不是僅按鈕 spinner）
 *     · 錯誤態：複用容器槽位，紅色 inline banner + 重試 + 複製原文
 *     · model_echo：黃色 warning + 保留雙語原文，引導用戶在 feedback 框追加要求
 *     · Copy 反饋：圖標 swap ✓ Copied 1.5s 自動恢復（不依賴 toast 基礎設施）
 *
 * 視覺寄存於 Studio 現有 chrome-sm / display-sm / status colors token 體系。
 */
import { useCallback, useState } from "react";
import { Loader2, Sparkles, Check, X, RefreshCw, Copy, CornerDownLeft, AlertCircle, AlertTriangle } from "lucide-react";
import clsx from "clsx";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { debugLog } from "@/lib/debugLog";
import BorderGlow from "@/components/shared/BorderGlow/BorderGlow";
import WorkflowActionButton from "@/components/shared/WorkflowActionButton";

interface PolishedPrompt {
    cn: string;
    en: string;
}

type PolishErrorReason =
    | "is_configured_false"
    | "api_error"
    | "json_parse_error"
    | "missing_keys"
    | "model_echo";

interface PolishErrorState {
    reason: PolishErrorReason;
    messageZh: string;
    messageEn: string;
    /** model_echo 時攜帶的原文雙語，用於 warning UI 展示。 */
    prompt_cn?: string;
    prompt_en?: string;
}

interface PolishPanelProps {
    prompt: string;
    tabMode: "t2i_i2v" | "direct_r2v";
    scriptId: string;
    slots?: { description: string }[];
    /** Image URLs to ground the polish (Issue 13). i2v: active first frame
     *  (T2I or storyboard render); r2v: reference image URLs. Empty/omit =
     *  pure text-only polish (back-compat for shots with no frame). */
    imageUrls?: string[];
    onApply: (text: string) => void;
}

/** 把後端 reason 映射到 i18n key（錯誤碼列表與 llm.py PolishError 對齊）。 */
function reasonToI18nKey(reason: PolishErrorReason): string {
    switch (reason) {
        case "is_configured_false": return "polishErrorIsConfiguredFalse";
        case "api_error": return "polishErrorApi";
        case "json_parse_error": return "polishErrorJsonParse";
        case "missing_keys": return "polishErrorMissingKeys";
        case "model_echo": return "polishWarningModelEcho";
    }
}

/** 解析 axios error 成 PolishErrorState；非 502 / 無 detail 時歸類為 api_error。 */
function parsePolishError(err: any, t: (key: string) => string): PolishErrorState {
    const detail = err?.response?.data?.detail;
    if (detail && typeof detail === "object" && typeof detail.reason === "string") {
        return {
            reason: detail.reason as PolishErrorReason,
            messageZh: detail.message_zh || "",
            messageEn: detail.message_en || "",
            prompt_cn: detail.prompt_cn,
            prompt_en: detail.prompt_en,
        };
    }
    return {
        reason: "api_error",
        messageZh: t("polishErrorApi"),
        messageEn: "Model call failed. Please retry or check your network.",
    };
}

export default function PolishPanel({
    prompt,
    tabMode,
    scriptId,
    slots = [],
    imageUrls = [],
    onApply,
}: PolishPanelProps) {
    const t = useTranslations("storyboardR2V");
    const [polished, setPolished] = useState<PolishedPrompt | null>(null);
    const [error, setError] = useState<PolishErrorState | null>(null);
    const [isPolishing, setIsPolishing] = useState(false);
    const [feedback, setFeedback] = useState("");
    /** 跟蹤兩欄的 "已複製" 閃爍狀態。 */
    const [copiedCol, setCopiedCol] = useState<"cn" | "en" | "original" | null>(null);

    const runPolish = useCallback(async (feedbackText: string = "") => {
        // 迭代時：draft=上一版 EN，prev_cn=上一版 CN，讓後端雙語錨點。
        // 首次：draft=用戶原文，prev_cn 留空。
        const isIteration = !!feedbackText;
        const draft = isIteration ? (polished?.en ?? prompt) : prompt;
        const prevCn = isIteration ? (polished?.cn ?? "") : "";
        if (!draft.trim()) return;

        setIsPolishing(true);
        setError(null);
        // 不立即清 polished：若失敗可保留上次結果繼續 refine；
        // 成功後再 setPolished 覆蓋。

        try {
            const res = tabMode === "direct_r2v"
                ? await api.polishR2VPrompt(draft, slots, feedbackText, scriptId, prevCn, imageUrls)
                : await api.polishVideoPrompt(draft, feedbackText, scriptId, prevCn, imageUrls);
            if (res?.prompt_cn && res?.prompt_en) {
                setPolished({ cn: res.prompt_cn, en: res.prompt_en });
                setFeedback("");
            } else {
                // 200 但缺 key 走錯誤態
                setError({
                    reason: "missing_keys",
                    messageZh: t("polishErrorMissingKeys"),
                    messageEn: "Model returned incomplete bilingual result. Please retry.",
                });
            }
        } catch (err: any) {
            debugLog.error("Studio", "Polish failed:", err);
            const parsed = parsePolishError(err, t);
            setError(parsed);
            // model_echo 是 warning：仍把後端附帶的雙語 echo 展示給用戶
            // （這樣他們能在 feedback 框裏參照原文追加要求）
            if (parsed.reason === "model_echo" && parsed.prompt_cn && parsed.prompt_en) {
                setPolished({ cn: parsed.prompt_cn, en: parsed.prompt_en });
            }
        } finally {
            setIsPolishing(false);
        }
    }, [tabMode, prompt, slots, scriptId, polished?.en, polished?.cn, imageUrls]);

    const handleApply = useCallback((text: string) => {
        onApply(text);
        setPolished(null);
        setError(null);
        setFeedback("");
    }, [onApply]);

    const handleDiscard = useCallback(() => {
        setPolished(null);
        setError(null);
        setFeedback("");
    }, []);

    const handleCopy = useCallback(async (text: string, col: "cn" | "en" | "original") => {
        try {
            await navigator.clipboard.writeText(text);
            setCopiedCol(col);
            // 1.5s 自動恢復 — 與其他 Studio 按鈕 swap 模式一致
            window.setTimeout(() => {
                setCopiedCol(prev => (prev === col ? null : prev));
            }, 1500);
        } catch (e) {
            debugLog.warn("Studio", "Copy to clipboard failed:", e);
        }
    }, []);

    const disabled = !prompt.trim() || isPolishing;
    const isEchoWarning = error?.reason === "model_echo";
    const isHardError = !!error && !isEchoWarning;

    // ────────────────────────────────────────────────────────────────────
    // Trigger 按鈕 — 當沒有結果、沒有錯誤、不在 loading 時顯示
    // ────────────────────────────────────────────────────────────────────
    if (!polished && !error && !isPolishing) {
        return (
            <div className="flex items-center justify-end">
                <WorkflowActionButton
                    variant="secondary"
                    size="sm"
                    leftIcon={<Sparkles />}
                    onClick={() => runPolish("")}
                    disabled={disabled}
                    title={t("polish")}
                >
                    {t("polish")}
                </WorkflowActionButton>
            </div>
        );
    }

    // ────────────────────────────────────────────────────────────────────
    // Container shell — loading / success / error / warning 共用
    //
    // Success / loading 態用 BorderGlow（紫粉品牌色 mesh-gradient 邊框 + hover
    // edge-light），首次結果出現時 sweep 一下做"AI 完成"儀式感。Hard error
    // 和 echo warning 仍用素色 inline banner，不能讓 brand glow 軟化警示意圖。
    // ────────────────────────────────────────────────────────────────────
    const useGlow = !isHardError && !isEchoWarning;
    const containerInner = (
        <>
            {/* Header — label + close button */}
            <div className="flex items-center justify-between gap-2">
                <span
                    className={clsx(
                        "inline-flex items-center gap-1.5 font-mono text-chrome-sm font-medium uppercase",
                        isHardError ? "text-status-failed-fg" : isEchoWarning ? "text-accent" : "text-primary",
                    )}
                >
                    {isHardError ? (
                        <AlertCircle size={11} aria-hidden="true" />
                    ) : isEchoWarning ? (
                        <AlertTriangle size={11} aria-hidden="true" />
                    ) : isPolishing ? (
                        <Loader2 size={11} className="animate-spin" aria-hidden="true" />
                    ) : (
                        <Sparkles size={11} aria-hidden="true" />
                    )}
                    {isPolishing && !polished ? t("polishing") : t("polish")}
                </span>
                <button
                    type="button"
                    onClick={handleDiscard}
                    aria-label={t("polishDiscard")}
                    className="-m-1 grid h-7 w-7 place-items-center rounded text-text-muted transition-colors duration-fast ease-out-quart hover:bg-hover-bg hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55"
                >
                    <X size={12} aria-hidden="true" />
                </button>
            </div>

            {/* Error banner — hard errors only（echo warning 走下面的雙語 + 黃色容器，不重複出 banner 行） */}
            {isHardError && error ? (
                <div className="space-y-2">
                    <p className="font-sans text-body-sm leading-relaxed text-status-failed-fg">
                        {t(reasonToI18nKey(error.reason) as any)}
                    </p>
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            onClick={() => runPolish("")}
                            disabled={isPolishing}
                            className="inline-flex items-center gap-1 rounded border border-status-failed-border bg-status-failed-bg px-2.5 py-1 font-mono text-chrome font-medium text-status-failed-fg transition-colors duration-fast ease-out-quart hover:bg-status-failed-bg/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed-border/55 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            <RefreshCw size={11} aria-hidden="true" />
                            {t("polishRetry")}
                        </button>
                        <button
                            type="button"
                            onClick={() => handleCopy(prompt, "original")}
                            className="inline-flex items-center gap-1 rounded border border-glass-border bg-black/20 px-2.5 py-1 font-mono text-chrome font-medium text-text-secondary transition-colors duration-fast ease-out-quart hover:bg-hover-bg hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55"
                        >
                            {copiedCol === "original" ? (
                                <><Check size={11} aria-hidden="true" />{t("polishCopied")}</>
                            ) : (
                                <><Copy size={11} aria-hidden="true" />{t("polishCopyOriginal")}</>
                            )}
                        </button>
                    </div>
                </div>
            ) : null}

            {/* Echo warning banner — 單行，緊湊展示，用戶主要靠下方 feedback 框迭代 */}
            {isEchoWarning && error ? (
                <p className="font-sans text-body-sm leading-relaxed text-accent">
                    {t(reasonToI18nKey(error.reason) as any)}
                </p>
            ) : null}

            {/* CN 欄 — skeleton（loading 時）/ 文本 + 按鈕 */}
            <BilingualColumn
                label={t("polishCnLabel")}
                text={polished?.cn}
                isLoading={isPolishing && !polished}
                isMono={false}
                copied={copiedCol === "cn"}
                copyLabel={t("polishCopy")}
                copiedLabel={t("polishCopied")}
                applyLabel={t("polishApply")}
                applyHint={t("polishApplyHint")}
                onCopy={() => polished && handleCopy(polished.cn, "cn")}
                onApply={() => polished && handleApply(polished.cn)}
            />

            {/* EN 欄 */}
            <BilingualColumn
                label={t("polishEnLabel")}
                text={polished?.en}
                isLoading={isPolishing && !polished}
                isMono={true}
                copied={copiedCol === "en"}
                copyLabel={t("polishCopy")}
                copiedLabel={t("polishCopied")}
                applyLabel={t("polishApply")}
                applyHint={t("polishApplyHint")}
                onCopy={() => polished && handleCopy(polished.en, "en")}
                onApply={() => polished && handleApply(polished.en)}
            />

            {/* Feedback iteration — 僅在有結果時（錯誤態下隱藏，避免基於無效結果迭代） */}
            {polished ? (
                <div className="flex items-center gap-2 pt-1">
                    <input
                        type="text"
                        value={feedback}
                        onChange={(e) => setFeedback(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && feedback.trim() && !isPolishing) {
                                e.preventDefault();
                                void runPolish(feedback);
                            }
                        }}
                        placeholder={t("polishFeedbackPlaceholder")}
                        disabled={isPolishing}
                        className="flex-1 rounded border border-glass-border bg-black/30 px-2.5 py-1.5 font-sans text-body-sm text-foreground placeholder:text-text-muted outline-none transition-colors duration-fast ease-out-quart focus:border-primary/55 focus-visible:ring-2 focus-visible:ring-primary/45 disabled:cursor-not-allowed disabled:opacity-50"
                    />
                    <button
                        type="button"
                        onClick={() => void runPolish(feedback)}
                        disabled={!feedback.trim() || isPolishing}
                        className="inline-flex items-center gap-1.5 rounded-md border border-glass-border bg-black/20 px-2.5 py-1.5 font-mono text-chrome font-medium text-text-secondary transition-colors duration-fast ease-out-quart hover:border-primary/45 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        {isPolishing ? (
                            <Loader2 size={11} className="animate-spin" aria-hidden="true" />
                        ) : (
                            <RefreshCw size={11} aria-hidden="true" />
                        )}
                        {t("polishRefineAgain")}
                    </button>
                </div>
            ) : null}
        </>
    );

    if (useGlow) {
        // animated 僅在首次結果產生那一幀 sweep —— mount 時間點 = polished 由
        // null 變為 truthy 那一刻，符合"AI 生成完成"瞬間的強調意圖。
        return (
            <BorderGlow
                animated={!!polished}
                glowColor="262 80 70"
                colors={["#646cff", "#a855f7", "#ec4899"]}
                backgroundColor="rgba(20, 17, 31, 0.92)"
                borderRadius={8}
                glowRadius={28}
                glowIntensity={0.85}
                fillOpacity={0.3}
                edgeSensitivity={35}
                className="motion-safe:animate-[shotPanelIn_220ms_cubic-bezier(0.22,1,0.36,1)_both]"
            >
                <div className="space-y-2.5 p-3">
                    {containerInner}
                </div>
            </BorderGlow>
        );
    }

    return (
        <div
            className={clsx(
                "rounded-md border p-3 space-y-2.5 motion-safe:animate-[shotPanelIn_220ms_cubic-bezier(0.22,1,0.36,1)_both]",
                isHardError
                    ? "border-status-failed-border bg-status-failed-bg/[0.06]"
                    : "border-accent/40 bg-accent/[0.06]",
            )}
        >
            {containerInner}
        </div>
    );
}

// ────────────────────────────────────────────────────────────────────
// 子組件：單欄（CN 或 EN）
//   - loading: 骨架圖（不是 spinner-only），確保用戶立即看到"結果即將到達"的契約
//   - 有文字: 顯示文字 + [📋 Copy] [↩ Apply] 兩按鈕
// ────────────────────────────────────────────────────────────────────
interface BilingualColumnProps {
    label: string;
    text?: string;
    isLoading: boolean;
    isMono: boolean;
    copied: boolean;
    copyLabel: string;
    copiedLabel: string;
    applyLabel: string;
    applyHint: string;
    onCopy: () => void;
    onApply: () => void;
}

function BilingualColumn({
    label,
    text,
    isLoading,
    isMono,
    copied,
    copyLabel,
    copiedLabel,
    applyLabel,
    applyHint,
    onCopy,
    onApply,
}: BilingualColumnProps) {
    return (
        <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
                <div className="font-mono text-chrome-sm font-medium uppercase text-text-muted">
                    {label}
                </div>
                {/* 按鈕行：loading 時隱藏，避免 skeleton 旁還有可點按鈕造成空操作 */}
                {!isLoading && text ? (
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            onClick={onCopy}
                            title={copyLabel}
                            className="btn-tip inline-flex items-center gap-1 rounded border border-glass-border bg-black/20 px-2 py-0.5 font-mono text-chrome font-medium text-text-secondary transition-colors duration-fast ease-out-quart hover:border-primary/45 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55"
                        >
                            {copied ? (
                                <><Check size={10} aria-hidden="true" />{copiedLabel}</>
                            ) : (
                                <><Copy size={10} aria-hidden="true" />{copyLabel}</>
                            )}
                        </button>
                        <button
                            type="button"
                            onClick={onApply}
                            title={applyHint}
                            className="btn-tip inline-flex items-center gap-1 rounded bg-primary/90 px-2 py-0.5 font-mono text-chrome font-semibold text-white transition-colors duration-fast ease-out-quart hover:bg-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55"
                        >
                            <CornerDownLeft size={10} aria-hidden="true" />
                            {applyLabel}
                        </button>
                    </div>
                ) : null}
            </div>
            {isLoading ? (
                <div className="space-y-1 rounded bg-black/30 px-2.5 py-2">
                    <div className="h-3 w-full animate-pulse rounded bg-elevated" />
                    <div className="h-3 w-[88%] animate-pulse rounded bg-elevated" />
                    <div className="h-3 w-[72%] animate-pulse rounded bg-elevated" />
                </div>
            ) : (
                <p
                    className={clsx(
                        "rounded bg-black/30 px-2.5 py-2 text-body-sm leading-relaxed text-foreground whitespace-pre-wrap",
                        isMono ? "font-mono" : "font-sans",
                    )}
                >
                    {text}
                </p>
            )}
        </div>
    );
}
