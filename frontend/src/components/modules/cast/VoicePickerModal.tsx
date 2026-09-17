"use client";
/**
 * VoicePickerModal — PR-3g Stage B #5
 *
 * Voice catalog picker for Cast character binding. Tabbed layout
 * (Q15.5 B + Q3 C):
 *   Tab 1 系統音色 — recommended (L1.5 gender-curated 4) + grouped
 *                   (CosyVoice / Qwen3 標準 / 方言 / 國際)
 *   Tab 2 我的復刻 — placeholder (PR-3h ships voice clone)
 *   Tab 3 我的設計 — placeholder (PR-3i ships voice design)
 *
 * Each voice card:
 *   - name + gender + dialect/lang tag
 *   - inline ▶ preview (calls api.previewVoice + plays audio)
 *   - selected state: primary border + ✓ corner
 *
 * Preview cache: backend memcache (md5 keyed) — first ▶ ~1-2s, repeats
 * instant. Only one audio plays at a time (selecting another voice
 * stops prior preview).
 *
 * Spec: r2v-workflow-v3-unified.md §4.2 + Q2-Q5 + Q15
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X, Play, Pause, Check, Sparkles, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { api, type VoiceMeta } from "@/lib/api";
import { getAssetUrl } from "@/lib/utils";

// L1.5 推薦: gender-based curated 4 voices (Q4 推薦)
// "通用最不會出錯"組合。CosyVoice 下線後改為 Gemini 預置音色，性別依據是
// 對 30 個音色的人工試聽（Google 官方只給特徵詞，不標性別）。
const RECOMMENDED_BY_GENDER: Record<string, string[]> = {
    Male: ["Achird", "Sadaltager", "Puck", "Algenib"],
    Female: ["Kore", "Vindemiatrix", "Sulafat", "Erinome"],
};

interface VoicePickerModalProps {
    isOpen: boolean;
    onClose: () => void;
    characterName: string;
    characterGender?: string;
    /** Sample text override — pass character's actual dialogue when available
     *  (Q5 A3 preferred). When null/undefined, uses character-name template. */
    previewText?: string;
    currentVoiceId?: string;
    onApply: (voiceId: string, voiceName: string) => void;
    /** PR-3h · Series id enables the 我的復刻 / 我的設計 tabs. When null,
     *  those tabs show "請先關聯到系列" message (orphan projects). */
    seriesId?: string | null;
    /** PR-3i · Character description for 一鍵轉 voice_prompt LLM helper. */
    characterDescription?: string;
}

export default function VoicePickerModal({
    isOpen,
    onClose,
    characterName,
    characterGender,
    previewText,
    currentVoiceId,
    onApply,
    seriesId,
    characterDescription,
}: VoicePickerModalProps) {
    const t = useTranslations("voicePicker");
    const [voices, setVoices] = useState<VoiceMeta[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedId, setSelectedId] = useState<string | undefined>(currentVoiceId);
    const [playingId, setPlayingId] = useState<string | null>(null);
    const [previewingId, setPreviewingId] = useState<string | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    // Sync selected when current changes / modal opens
    useEffect(() => {
        if (isOpen) setSelectedId(currentVoiceId);
    }, [isOpen, currentVoiceId]);


    // Load voices once when modal opens
    useEffect(() => {
        if (!isOpen) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        api.getVoices()
            .then((vs) => { if (!cancelled) setVoices(vs); })
            .catch((e) => { if (!cancelled) setError(e?.message || "Failed to load voices"); })
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, [isOpen]);


    useEffect(() => {
        if (!isOpen && audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
            setPlayingId(null);
        }
    }, [isOpen]);

    // Preview sample text — Q5 A2 fallback when character has no dialogue yet.
    // Prefer explicit previewText (Q5 A3); otherwise build from character name.
    const sampleText =
        previewText ||
        (characterName
            ? t("previewTextNamed", { name: characterName })
            : t("previewTextDefault"));

    // Unified preview-by-id.
    const handlePreviewById = async (voiceId: string) => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
            if (playingId === voiceId) {
                setPlayingId(null);
                return;  // toggle off
            }
            setPlayingId(null);
        }
        setPreviewingId(voiceId);
        try {
            const { url } = await api.previewVoice({
                voice_id: voiceId,
                text: sampleText,
            });
            const audio = new Audio(getAssetUrl(url));
            audio.onended = () => {
                setPlayingId(null);
                if (audioRef.current === audio) audioRef.current = null;
            };
            audio.onerror = () => {
                setPlayingId(null);
                setError(t("playFailed"));
            };
            audioRef.current = audio;
            setPlayingId(voiceId);
            await audio.play();
        } catch (e: any) {
            setError(e?.message || "Preview failed");
        } finally {
            setPreviewingId(null);
        }
    };

    const handlePreview = (voice: VoiceMeta) => handlePreviewById(voice.id);

    // L1.5 recommended subset based on character gender
    const recommended = useMemo<VoiceMeta[]>(() => {
        if (!voices.length) return [];
        const genderKey = characterGender === "Female" || characterGender === "女" || characterGender === "female"
            ? "Female"
            : characterGender === "Male" || characterGender === "男" || characterGender === "male"
                ? "Male"
                : null;
        if (!genderKey) {
            // No gender → show 4 curated male + 4 curated female mixed
            const ids = [...(RECOMMENDED_BY_GENDER.Male ?? []), ...(RECOMMENDED_BY_GENDER.Female ?? [])];
            return ids
                .map((id) => voices.find((v) => v.id === id))
                .filter((v): v is VoiceMeta => !!v);
        }
        return (RECOMMENDED_BY_GENDER[genderKey] ?? [])
            .map((id) => voices.find((v) => v.id === id))
            .filter((v): v is VoiceMeta => !!v);
    }, [voices, characterGender]);

    // Group system voices by sub-category for the catalog area
    // Gemini 的 30 個音色同屬一個家族、一個模型，按 cosyvoice/qwen3 分組已無
    // 意義。改按性別分組 —— 綁定角色時第一件事就是篩性別。
    const groups = useMemo(() => ({
        female: voices.filter((v) => v.gender === "Female"),
        male: voices.filter((v) => v.gender === "Male"),
        other: voices.filter((v) => v.gender !== "Female" && v.gender !== "Male"),
    }), [voices]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-overlay backdrop-blur-sm" onClick={onClose}>
            <div
                className="w-full max-w-4xl max-h-[85vh] flex flex-col rounded-2xl border border-glass-border bg-elevated shadow-[0_24px_64px_-12px_rgba(0,0,0,0.7)]"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-glass-border">
                    <div className="flex items-center gap-3 min-w-0">
                        <h2 className="text-display font-medium text-foreground truncate">
                            {t("title")}
                            <span className="ml-2 text-text-muted">— {characterName}</span>
                        </h2>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label={t("close")}
                        className="p-2 rounded-lg hover:bg-hover-bg text-text-muted hover:text-foreground transition-colors"
                    >
                        <X size={16} />
                    </button>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
                    {loading && (
                        <div className="grid place-items-center py-12 text-text-muted">
                            <Loader2 className="animate-spin" size={20} />
                        </div>
                    )}
                    {error && (
                        <div className="rounded-md border border-status-failed-border bg-status-failed-bg p-3 text-body-sm text-status-failed-fg" role="alert">
                            {error}
                        </div>
                    )}

                    {!loading && !error && (
                        <div className="space-y-6">
                            {/* Recommended row */}
                            {recommended.length > 0 && (
                                <section>
                                    <h3 className="mb-2 flex items-center gap-2 font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
                                        <Sparkles size={11} className="text-primary" />
                                        {t("recommended")}
                                        <span className="text-text-muted/60">· {t("basedOnCharacter", { gender: characterGender || "?" })}</span>
                                    </h3>
                                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                                        {recommended.map((v) => (
                                            <VoiceCard
                                                key={v.id}
                                                voice={v}
                                                selected={selectedId === v.id}
                                                playing={playingId === v.id}
                                                previewing={previewingId === v.id}
                                                onSelect={() => setSelectedId(v.id)}
                                                onPreview={() => handlePreview(v)}
                                            />
                                        ))}
                                    </div>
                                </section>
                            )}

                            {/* Grouped catalog */}
                            <VoiceGroup label={t("groupFemale")} voices={groups.female} selectedId={selectedId} playingId={playingId} previewingId={previewingId} onSelect={setSelectedId} onPreview={handlePreview} />
                            <VoiceGroup label={t("groupMale")} voices={groups.male} selectedId={selectedId} playingId={playingId} previewingId={previewingId} onSelect={setSelectedId} onPreview={handlePreview} />
                            <VoiceGroup label={t("groupOther")} voices={groups.other} selectedId={selectedId} playingId={playingId} previewingId={previewingId} onSelect={setSelectedId} onPreview={handlePreview} />
                        </div>
                    )}

                </div>

                {/* Footer */}
                <div className="flex items-center justify-between gap-3 px-6 py-3 border-t border-glass-border">
                    <span className="font-mono text-[0.625rem] uppercase tracking-[0.14em] text-text-muted">
                        {selectedId
                            ? voices.find(v => v.id === selectedId)?.name || selectedId
                            : t("noSelection")}
                    </span>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={onClose}
                            className="inline-flex items-center px-4 py-2 rounded-md bg-glass border border-glass-border text-text-secondary hover:text-foreground hover:bg-hover-bg transition-colors text-[0.75rem]"
                        >
                            {t("cancel")}
                        </button>
                        <button
                            onClick={() => {
                                if (!selectedId) return;
                                const name = voices.find(v => v.id === selectedId)?.name || selectedId;
                                onApply(selectedId, name);
                                onClose();
                            }}
                            disabled={!selectedId || selectedId === currentVoiceId}
                            className="inline-flex items-center px-4 py-2 rounded-md bg-primary text-white border border-[rgba(100,108,255,0.65)] shadow-[inset_0_1.5px_0_rgba(255,255,255,0.14)] hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-[0.75rem] font-semibold"
                        >
                            {t("apply")}
                        </button>
                    </div>
                </div>
            </div>

        </div>
    );
}

// ──────────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────────

function VoiceGroup({
    label,
    voices,
    selectedId,
    playingId,
    previewingId,
    onSelect,
    onPreview,
}: {
    label: string;
    voices: VoiceMeta[];
    selectedId?: string;
    playingId: string | null;
    previewingId: string | null;
    onSelect: (id: string) => void;
    onPreview: (voice: VoiceMeta) => void;
}) {
    if (!voices.length) return null;
    return (
        <section>
            <h3 className="mb-2 flex items-center gap-2 font-mono text-[0.625rem] uppercase tracking-[0.18em] text-text-muted">
                {label} <span className="text-text-muted/60">({voices.length})</span>
            </h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                {voices.map((v) => (
                    <VoiceCard
                        key={v.id}
                        voice={v}
                        selected={selectedId === v.id}
                        playing={playingId === v.id}
                        previewing={previewingId === v.id}
                        onSelect={() => onSelect(v.id)}
                        onPreview={() => onPreview(v)}
                    />
                ))}
            </div>
        </section>
    );
}

function VoiceCard({
    voice,
    selected,
    playing,
    previewing,
    onSelect,
    onPreview,
}: {
    voice: VoiceMeta;
    selected: boolean;
    playing: boolean;
    previewing: boolean;
    onSelect: () => void;
    onPreview: () => void;
}) {
    return (
        <div
            onClick={onSelect}
            className={`relative cursor-pointer rounded-lg border p-3 transition-colors ${
                selected
                    ? "border-primary bg-[rgba(100,108,255,0.10)]"
                    : "border-glass-border bg-glass hover:border-foreground/30"
            }`}
        >
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                    <p className="truncate text-[0.8125rem] font-medium text-foreground" title={voice.name}>
                        {voice.name}
                    </p>
                    <p className="mt-0.5 font-mono text-[0.59375rem] uppercase tracking-[0.14em] text-text-muted">
                        {voice.gender}
                        {voice.dialect ? ` · ${voice.dialect}` : ""}
                        {voice.lang_primary ? ` · ${voice.lang_primary}` : ""}
                        {voice.supports_instruction ? " · instr" : ""}
                    </p>
                </div>
                <button
                    onClick={(e) => { e.stopPropagation(); onPreview(); }}
                    aria-label={playing ? "Stop preview" : "Play preview"}
                    className={`shrink-0 inline-flex h-7 w-7 items-center justify-center rounded-md border transition-colors ${
                        playing
                            ? "border-primary bg-primary/15 text-primary"
                            : "border-glass-border bg-black/30 text-text-secondary hover:border-foreground/30 hover:text-foreground"
                    }`}
                >
                    {previewing ? (
                        <Loader2 size={12} className="animate-spin" />
                    ) : playing ? (
                        <Pause size={12} />
                    ) : (
                        <Play size={12} />
                    )}
                </button>
            </div>
            {selected && (
                <div className="absolute top-1.5 right-1.5 grid h-5 w-5 place-items-center rounded-full bg-primary text-white">
                    <Check size={11} strokeWidth={2.5} />
                </div>
            )}
        </div>
    );
}

