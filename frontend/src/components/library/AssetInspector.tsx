"use client";

import { useState, useEffect, useRef } from "react";
import { useTranslations } from "next-intl";
import { X, Star, Download, Sparkles, Loader2, Globe, Trash2 } from "lucide-react";
import type { Character, Scene, Prop, ImageAsset, ImageVariant } from "@/store/projectStore";
import { characterImageAsset } from "@/lib/characterImage";
import { mediaUrl } from "@/lib/mediaPath";
import { api } from "@/lib/api";
import { toast } from "@/store/toastStore";
import { coverGradient, GRAIN_URL } from "@/lib/atelierCover";

type AssetTab = "characters" | "scenes" | "props";

// 資產類型 → 後端單數 type（生成端點用）。
const SINGULAR_TYPE: Record<AssetTab, string> = {
  characters: "character",
  scenes: "scene",
  props: "prop",
};

// 「生成更多變體」一次追加的張數 + 任務輪詢參數（~5 分鐘上限）。
const VARIANT_BATCH = 3;
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 150;

interface AssetInspectorProps {
  asset: Character | Scene | Prop;
  type: AssetTab;
  sourceName: string;
  /** 裸 series/project id（調生成/刷新 API 用）。 */
  sourceId: string;
  /** 資產歸屬：series/global 無生成端點 → 變體生成置灰。 */
  sourceKind: "series" | "project" | "global";
  starred: boolean;
  onClose: () => void;
  onToggleStar: () => void;
  /** 提升到全局成功後回調（父層刷新庫以顯示新入池資產）。可選。 */
  onPromoted?: () => void;
  /** 刪除成功後回調（父層刷新庫並關閉 inspector）。僅 global 來源顯示刪除按鈕，故僅該情境需要。 */
  onDeleted?: () => void;
}

/** Character 走 characterImageAsset（reference_sheet→full_body，歸一化成 ImageAsset 形狀）；scene/prop 用 image_asset。 */
function primaryImageAsset(asset: Character | Scene | Prop, type: AssetTab): ImageAsset | undefined {
  if (type === "characters") return characterImageAsset(asset as Character);
  return (asset as Scene | Prop).image_asset;
}

function fallbackUrl(asset: Character | Scene | Prop, type: AssetTab): string | undefined {
  if (type === "characters") {
    const c = asset as Character;
    return c.image_url || c.full_body_image_url;
  }
  return (asset as Scene | Prop).image_url;
}

const MIME_EXT: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
  "image/gif": "gif",
  "image/avif": "avif",
  "image/svg+xml": "svg",
};

/** 下載文件名擴展名：優先取 URL 路徑後綴（剝掉 query/簽名），否則回退到 blob content-type，默認 png。 */
function downloadExt(url: string, contentType?: string): string {
  try {
    const path = new URL(url, window.location.origin).pathname;
    const m = path.match(/\.([a-z0-9]+)$/i);
    if (m) return m[1].toLowerCase();
  } catch {
    // URL 解析失敗時退回 content-type / 默認
  }
  const fromType = contentType?.split(";")[0].trim().toLowerCase();
  if (fromType && MIME_EXT[fromType]) return MIME_EXT[fromType];
  return "png";
}

/**
 * 資產庫右側詳情抽屜（Line B "Luminous Atelier"）。
 * 庫專用，不復用共享 AssetCard。展示選中資產的 hero + 變體條 + 元數據 + prompt + 動作。
 * 元數據數據驅動（metaRows）：SEED/MODEL/SIZE 當前數據模型未存（變體僅
 * id/url/created_at/prompt_used），故讀為 undefined → 不渲染；後端補字段後 UI 零改自動出現。
 * 動作區：「下載」實做；「生成更多變體」對 project 資產實做（series 置灰，無生成端點）。
 */
export default function AssetInspector({
  asset,
  type,
  sourceName,
  sourceId,
  sourceKind,
  starred,
  onClose,
  onToggleStar,
  onPromoted,
  onDeleted,
}: AssetInspectorProps) {
  const t = useTranslations("library");
  const TYPE_LABEL: Record<AssetTab, string> = {
    characters: t("characterLabel"),
    scenes: t("sceneLabel"),
    props: t("propLabel"),
  };
  // created_at 來自 time.time()（秒）；容錯已是毫秒的情況。相對時間標籤走 i18n。
  const timeAgo = (ts?: number): string => {
    if (!ts) return "—";
    const tsMs = ts > 1e12 ? ts : ts * 1000;
    const days = Math.floor((Date.now() - tsMs) / 86_400_000);
    if (days <= 0) return t("timeToday");
    if (days === 1) return t("timeYesterday");
    if (days < 30) return t("timeDaysAgo", { days });
    return t("timeMonthsAgo", { months: Math.floor(days / 30) });
  };
  const imageAsset = primaryImageAsset(asset, type);
  const baseVariants = imageAsset?.variants ?? [];
  // 本地新生成的變體（來自「生成更多變體」）。父層 library 自己持有 `sources` 且只在整頁
  // reload 時刷新，所以新變體在此併入以即時反饋；按 id 與 prop 集去重，父層後續 reload
  // （屆時新變體會隨 `baseVariants` 帶回）也不會重複。
  const [extraVariants, setExtraVariants] = useState<ImageVariant[]>([]);
  const baseIds = new Set(baseVariants.map((v) => v.id));
  const variants = [...baseVariants, ...extraVariants.filter((v) => !baseIds.has(v.id))];
  const defaultId = imageAsset?.selected_id ?? baseVariants[0]?.id ?? null;
  const [activeVariantId, setActiveVariantId] = useState<string | null>(defaultId);
  const [generating, setGenerating] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // 切換選中資產時重置本地高亮的變體 + 丟棄上一個資產本地追加的變體。
  useEffect(() => {
    setActiveVariantId(defaultId);
    setExtraVariants([]);
  }, [asset.id, defaultId]);

  // 卸載/切換資產後避免異步輪詢回寫已失效的狀態。
  const aliveRef = useRef(true);
  const currentAssetIdRef = useRef(asset.id);
  useEffect(() => {
    currentAssetIdRef.current = asset.id;
  }, [asset.id]);
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // a11y：抽屜打開時把焦點移入面板、Escape 關閉、關閉後還原焦點（非模態，不做 focus trap）。
  const asideRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    asideRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, []);

  const activeVariant = variants.find((v) => v.id === activeVariantId) ?? variants[0];
  const rawHeroUrl = activeVariant?.url ?? fallbackUrl(asset, type);
  const heroUrl = rawHeroUrl ? mediaUrl(rawHeroUrl) : undefined;
  // prop 素材若來自視頻輸出（如真人換裝合成），無 image_url/variant 時退回 video_url，
  // 與 AssetLibraryPage 卡片列表的 getVideoUrl 邏輯一致。
  const rawHeroVideoUrl = !heroUrl && type === "props" ? (asset as Prop).video_url : undefined;
  const heroVideoUrl = rawHeroVideoUrl ? mediaUrl(rawHeroVideoUrl) : undefined;
  const prompt = activeVariant?.prompt_used ?? "";

  // 元數據行（數據驅動）：先放現有四項，再在字段存在時追加 SEED/MODEL/SIZE。
  // 後端 TODO：當前 ImageVariant 僅 id/url/created_at/prompt_used，資產無 seed/model/size，
  // 故 assetMeta.* 讀為 undefined → 不 push → 不渲染。後端補字段後此處零改自動出現。
  const assetMeta = asset as Partial<{ seed: number | string; model: string; size: string }>;
  const metaRows: { label: string; value: string }[] = [
    { label: t("metaType"), value: TYPE_LABEL[type] },
    { label: t("metaSource"), value: sourceName },
    { label: t("metaVariant"), value: `${variants.length}` },
    { label: t("metaCreated"), value: timeAgo(activeVariant?.created_at) },
  ];
  if (assetMeta.seed != null) metaRows.push({ label: "SEED", value: String(assetMeta.seed) });
  if (assetMeta.model) metaRows.push({ label: "MODEL", value: assetMeta.model });
  if (assetMeta.size) metaRows.push({ label: "SIZE", value: assetMeta.size });

  const handleDownload = async () => {
    if (!heroUrl) return;
    const fileBase = asset.name || "asset";
    try {
      const res = await fetch(heroUrl);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const ext = downloadExt(heroUrl, blob.type);
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `${fileBase}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      // 跨域(CORS)/網絡失敗：download 屬性對跨域 URL 無效，退回到新標籤打開。
      window.open(heroUrl, "_blank", "noopener,noreferrer");
    }
  };

  // 輪詢生成任務直到完成（mirror ConsistencyVault 的 task 輪詢）；失敗/超時拋錯。
  const pollUntilDone = async (taskId: string): Promise<boolean> => {
    for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      if (!aliveRef.current) return false;
      let status: { status?: string; error?: string } | undefined;
      try {
        status = await api.getTaskStatus(taskId);
      } catch {
        continue; // 瞬時網絡錯誤：繼續輪詢
      }
      if (status?.status === "completed") return true;
      if (status?.status === "failed") throw new Error(status.error || t("genFailed"));
    }
    throw new Error(t("genTimeout"));
  };

  // 生成更多變體：僅 project 資產可用（series 無生成端點）。複用按項目 batch 生成管線，
  // 完成後 re-fetch 該項目，把新變體併入本地展示並高亮最新一張。
  const handleGenerateVariants = async () => {
    if (sourceKind !== "project" || generating) return;
    const assetId = asset.id;
    // 父層傳入的是列表 key（`project-<id>`）；生成/刷新 API 需要裸 project id。
    const projectId = sourceId.replace(/^project-/, "");
    setGenerating(true);
    const tid = toast.progress(t("generatingVariants"), {
      body: t("generatingVariantsBody", { name: asset.name, count: VARIANT_BATCH }),
    });
    try {
      const resp = await api.generateAsset(
        projectId,
        assetId,
        SINGULAR_TYPE[type],
        "",
        undefined,
        "all",
        "",
        true,
        "",
        VARIANT_BATCH
      );
      const taskId = (resp as { _task_id?: string } | undefined)?._task_id;
      if (taskId) {
        const done = await pollUntilDone(taskId);
        if (!done) return; // 已卸載
      }
      if (!aliveRef.current || currentAssetIdRef.current !== assetId) return;
      const proj = await api.getProject(projectId);
      const list: (Character | Scene | Prop)[] =
        (type === "characters" ? proj?.characters : type === "scenes" ? proj?.scenes : proj?.props) ?? [];
      const updated = list.find((a) => a.id === assetId);
      const freshVariants = (updated ? primaryImageAsset(updated, type)?.variants : undefined) ?? [];
      if (!aliveRef.current || currentAssetIdRef.current !== assetId) return;
      const added = freshVariants.filter((v) => !baseIds.has(v.id));
      setExtraVariants(freshVariants);
      if (added[0]) setActiveVariantId(added[0].id);
      toast.update(tid, {
        kind: "success",
        title: t("variantsGenerated"),
        body: added.length ? t("variantsAddedBody", { count: added.length }) : t("variantsRefreshed"),
        autoCloseMs: 5000,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("genFailed");
      if (aliveRef.current) toast.update(tid, { kind: "error", title: t("variantsGenFailed"), body: msg, autoCloseMs: 0 });
    } finally {
      if (aliveRef.current) setGenerating(false);
    }
  };

  // 提升到全局：把 project/series 來源資產 deep-copy 進全局共享池（global 來源不顯示該按鈕）。
  // 成功後 toast 並回調父層刷新（新入池資產即出現在「全局 / 共享」分組）。
  const handlePromote = async () => {
    if (sourceKind === "global" || promoting) return;
    // 父層傳入的是列表 key（`project-<id>` / `series-<id>`）；promote API 需要裸 id。
    const rawSourceId = sourceId.replace(/^(project|series)-/, "");
    setPromoting(true);
    try {
      await api.promoteAssetToLibrary(sourceKind, rawSourceId, SINGULAR_TYPE[type], asset.id);
      toast.success(t("promoteSuccess"), { body: t("promoteSuccessBody", { name: asset.name }) });
      onPromoted?.();
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("promoteFailed");
      toast.error(t("promoteFailed"), { body: msg });
    } finally {
      setPromoting(false);
    }
  };

  // 從全局共享池刪除：僅 global 來源顯示按鈕。後端若偵測到仍被任一項目/系列分鏡引用會回
  // 409（LibraryAssetInUseError），此時二次確認是否 force=true 強制刪除並留下懸空引用。
  const handleDelete = async () => {
    if (sourceKind !== "global" || deleting) return;
    setDeleting(true);
    try {
      await api.deleteLibraryAsset(SINGULAR_TYPE[type], asset.id);
      toast.success(t("deleteSuccess"), { body: t("deleteSuccessBody", { name: asset.name }) });
      onDeleted?.();
    } catch (e) {
      const detail = e as { error?: string; references?: Array<{ owner_title?: string | null; owner_kind?: string }> } | Error;
      if (typeof detail === "object" && detail !== null && "error" in detail && detail.error === "library_asset_in_use") {
        const refNames = (detail.references ?? [])
          .map((r) => r.owner_title || r.owner_kind)
          .filter(Boolean)
          .join(", ");
        const confirmed = window.confirm(t("deleteInUseConfirm", { name: asset.name, refs: refNames || "—" }));
        if (confirmed) {
          try {
            await api.deleteLibraryAsset(SINGULAR_TYPE[type], asset.id, true);
            toast.success(t("deleteSuccess"), { body: t("deleteSuccessBody", { name: asset.name }) });
            onDeleted?.();
          } catch (e2) {
            const msg = e2 instanceof Error ? e2.message : t("deleteFailed");
            toast.error(t("deleteFailed"), { body: msg });
          }
        }
      } else {
        const msg = detail instanceof Error ? detail.message : t("deleteFailed");
        toast.error(t("deleteFailed"), { body: msg });
      }
    } finally {
      setDeleting(false);
    }
  };

  return (
    <aside
      ref={asideRef}
      tabIndex={-1}
      className="fixed inset-0 z-50 w-full md:static md:inset-auto md:z-auto md:w-[340px] flex-shrink-0 h-full flex flex-col overflow-y-auto bg-surface border-l border-glass-border shadow-2xl atelier-reveal focus:outline-none"
      aria-label={t("inspectorAria")}
    >
      {/* Hero — 磨砂鋪底 + object-contain：三視圖/橫豎混雜的資產完整展示不裁切（避免裁頭）。 */}
      <div className="relative aspect-[3/4] bg-surface-inset overflow-hidden flex-shrink-0">
        {heroUrl ? (
          <>
            <img
              src={heroUrl}
              alt=""
              aria-hidden="true"
              className="absolute inset-0 w-full h-full object-cover blur-xl scale-110 opacity-40"
            />
            <img src={heroUrl} alt={asset.name} className="relative w-full h-full object-contain" />
          </>
        ) : heroVideoUrl ? (
          <video src={heroVideoUrl} muted loop playsInline autoPlay controls className="relative w-full h-full object-contain" />
        ) : (
          // 無圖像：確定性漸變封面 + 顆粒，替代發灰佔位圖標。
          <>
            <div className="absolute inset-0" style={{ background: coverGradient(asset.id) }} aria-hidden="true" />
            <div
              className="absolute inset-0 mix-blend-overlay opacity-60"
              style={{ backgroundImage: GRAIN_URL }}
              aria-hidden="true"
            />
            <div className="relative w-full h-full grid place-items-center p-6 text-center">
              <span className="font-display atelier-display text-2xl font-semibold text-foreground tracking-tight">
                {asset.name}
              </span>
            </div>
          </>
        )}
        {/* amber halation overlay — only on starred (atelier signature; amber = starred). */}
        {starred && (
          <div
            className="pointer-events-none absolute inset-0 shadow-[inset_0_0_60px_-10px_var(--color-status-starred-bg)]"
            aria-hidden="true"
          />
        )}
        <button
          type="button"
          onClick={onToggleStar}
          aria-pressed={starred}
          aria-label={starred ? t("unstar") : t("star")}
          className={`absolute top-3 left-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full font-mono text-[0.625rem] font-bold uppercase tracking-[0.1em] backdrop-blur-md border transition-colors ${
            starred
              ? "text-status-starred-fg bg-status-starred-bg border-status-starred-border"
              : "text-text-secondary bg-black/40 border-transparent hover:text-foreground"
          }`}
        >
          <Star size={12} className={starred ? "fill-current" : ""} />
          {starred ? t("starred") : t("star")}
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("closeInspector")}
          className="absolute top-3 right-3 w-8 h-8 rounded-full grid place-items-center bg-black/50 backdrop-blur-md text-foreground hover:bg-black/70 transition-colors"
        >
          <X size={15} />
        </button>
      </div>

      <div className="p-5 flex flex-col gap-5">
        <div>
          <div className="font-display atelier-display text-xl font-semibold text-foreground tracking-tight">
            {asset.name}
          </div>
          <div className="font-mono text-[0.59375rem] text-text-muted tracking-[0.06em] uppercase mt-1.5">
            {TYPE_LABEL[type]} · {sourceName} · {t("variantCount", { count: variants.length })}
          </div>
        </div>

        {/* Variant strip */}
        {variants.length > 1 && (
          <div>
            <div className="font-mono text-[0.5625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary mb-2.5">
              {t("variantsSection")}
            </div>
            <div className="grid grid-cols-4 gap-2">
              {variants.map((v) => {
                const on = v.id === activeVariant?.id;
                return (
                  <button
                    key={v.id}
                    type="button"
                    onClick={() => setActiveVariantId(v.id)}
                    aria-current={on ? "true" : undefined}
                    className={`relative aspect-square rounded-md overflow-hidden transition-transform hover:-translate-y-0.5 ${
                      on ? "ring-2 ring-primary" : "ring-1 ring-glass-border"
                    }`}
                  >
                    <img src={mediaUrl(v.url)} alt={t("variantAlt")} className="w-full h-full object-cover" />
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Metadata */}
        <div>
          <div className="font-mono text-[0.5625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary mb-2.5">
            {t("metadataSection")}
          </div>
          <div className="flex flex-col">
            {metaRows.map((row) => (
              <div
                key={row.label}
                className="flex justify-between items-center py-2 border-b border-glass-border last:border-b-0 text-[0.8125rem]"
              >
                <span className="font-mono text-[0.625rem] text-text-muted tracking-[0.04em]">{row.label}</span>
                <span className="text-foreground font-medium">{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Prompt */}
        {prompt && (
          <div>
            <div className="font-mono text-[0.5625rem] font-semibold uppercase tracking-[0.16em] text-text-secondary mb-2.5">
              {t("promptSection")}
            </div>
            <div className="bg-surface-inset rounded-lg p-3.5 text-[0.8125rem] leading-relaxed text-text-secondary border-l-2 border-status-starred-border">
              {prompt}
            </div>
          </div>
        )}

        {/* Actions */}
        {/*
          生成更多變體：project 資產複用「按項目 batch 生成」管線，對當前 asset append 新變體
          （不替換），完成後併入本地展示並高亮最新一張；series 資產無生成端點（生成需在具體
          項目內進行），故置灰並提示在劇集內生成。「用於分鏡」按鈕已移除（佔位、無落地路徑）。
        */}
        <div className="flex flex-col gap-2">
          {sourceKind === "project" ? (
            <button
              type="button"
              onClick={handleGenerateVariants}
              disabled={generating}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-on-accent text-sm font-semibold hover:bg-primary-hover transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
              {generating ? t("generating") : t("generateMoreVariants")}
            </button>
          ) : (
            <button
              type="button"
              disabled
              title={t("genInEpisodeTooltip")}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-surface-inset border border-glass-border text-text-muted text-sm font-medium cursor-not-allowed disabled:opacity-60"
            >
              <Sparkles size={15} />
              {t("generateMoreVariants")}
              <span className="inline-flex items-center rounded-full px-1.5 py-0.5 font-mono text-[0.53125rem] font-semibold tracking-[0.06em] text-status-pending-fg bg-status-pending-bg border border-status-pending-border">
                {t("genInEpisodeBadge")}
              </span>
            </button>
          )}
          {/* 提升到全局：project/series 來源可用；global 來源隱藏（無需自我提升）。 */}
          {sourceKind !== "global" && (
            <button
              type="button"
              onClick={handlePromote}
              disabled={promoting}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-surface-inset border border-glass-border text-foreground text-sm font-medium hover:bg-hover-bg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {promoting ? <Loader2 size={15} className="animate-spin" /> : <Globe size={15} />}
              {promoting ? t("promoting") : t("promoteToGlobal")}
            </button>
          )}
          {/* 下載：v1 實做 */}
          <button
            type="button"
            onClick={handleDownload}
            disabled={!heroUrl}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-surface-inset border border-glass-border text-foreground text-sm font-medium hover:bg-hover-bg transition-colors disabled:opacity-40"
          >
            <Download size={15} />
            {t("download")}
          </button>
          {/* 刪除：僅全局共享池資產可從此處刪除（project/series 資產走各自的刪除流程）。 */}
          {sourceKind === "global" && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-surface-inset border border-status-failed-border text-status-failed-fg text-sm font-medium hover:bg-status-failed-bg transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {deleting ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
              {deleting ? t("deleting") : t("deleteAsset")}
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
