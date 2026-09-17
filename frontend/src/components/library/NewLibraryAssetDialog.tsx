"use client";

import { useState, useRef, useEffect, type FormEvent, type ChangeEvent } from "react";
import { useTranslations } from "next-intl";
import { X, Loader2, Plus, Upload, Image as ImageIcon } from "lucide-react";
import { api } from "@/lib/api";
import { getAssetUrl } from "@/lib/utils";
import { toast } from "@/store/toastStore";
import GridOverlayPicker, { gridChoiceToParams, type GridOverlayChoice } from "@/components/shared/GridOverlayPicker";

type AssetTab = "characters" | "scenes" | "props";

// 資產類型 → 後端單數 type（/library/assets 端點用）。
const SINGULAR: Record<AssetTab, string> = { characters: "character", scenes: "scene", props: "prop" };

interface NewLibraryAssetDialogProps {
  onClose: () => void;
  /** 創建成功後回調（父層刷新庫以顯示新資產）。 */
  onCreated: () => void;
}

/**
 * 資產庫「新建全局資產」輕量彈窗（T6-entries）。
 * 選類型(角色/場景/道具) + 名稱 + 描述 +（可選）圖片（上傳本地文件或填 URL）→ POST /library/assets。
 * 本地上傳走 POST /library/assets/upload（multipart 字段 "file" → { image_url }），結果寫入 imageUrl。
 */
export default function NewLibraryAssetDialog({ onClose, onCreated }: NewLibraryAssetDialogProps) {
  const t = useTranslations("library");
  const tc = useTranslations("common");
  const [assetType, setAssetType] = useState<AssetTab>("characters");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [imageHasGridOverlay, setImageHasGridOverlay] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [gridChoice, setGridChoice] = useState<GridOverlayChoice>('none');

  const nameRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  // a11y：打開時聚焦名稱、Escape 關閉、關閉後還原焦點。
  useEffect(() => {
    const prevFocused = document.activeElement as HTMLElement | null;
    nameRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      prevFocused?.focus?.();
    };
  }, []);

  const typeOptions: { id: AssetTab; label: string }[] = [
    { id: "characters", label: t("characterLabel") },
    { id: "scenes", label: t("sceneLabel") },
    { id: "props", label: t("propLabel") },
  ];

  // 上傳本地圖片 → 後端返回 image_url，寫入 imageUrl 作為創建用圖。
  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // reset so re-selecting the same file fires onChange again
    if (!file) return;
    setUploading(true);
    try {
      const { size: gridSize, color: gridColor } = gridChoiceToParams(gridChoice);
      const { image_url, has_grid_overlay } = await api.uploadLibraryImage(file, gridSize, gridColor);
      setImageUrl(image_url);
      setImageHasGridOverlay(has_grid_overlay);
      toast.success(t("uploadSuccess"));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      toast.error(t("uploadFailed"), msg ? { body: msg } : undefined);
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (submitting || uploading) return;
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error(t("nameRequired"));
      nameRef.current?.focus();
      return;
    }
    setSubmitting(true);
    try {
      await api.createLibraryAsset(SINGULAR[assetType], {
        name: trimmed,
        description: description.trim() || undefined,
        image_url: imageUrl.trim() || undefined,
        has_grid_overlay: imageUrl.trim() ? imageHasGridOverlay : undefined,
      });
      toast.success(t("createSuccess"), { body: trimmed });
      onCreated();
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("createFailed");
      toast.error(t("createFailed"), { body: msg });
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      {/* 點外關閉遮罩 */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("newAssetTitle")}
        className="relative z-[1] w-full max-w-[440px] glass-panel border border-glass-border rounded-2xl shadow-2xl atelier-reveal overflow-hidden"
      >
        {/* header */}
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-3 border-b border-glass-border">
          <div>
            <div className="font-display atelier-display text-lg font-semibold text-foreground tracking-tight">
              {t("newAssetTitle")}
            </div>
            <div className="text-[0.75rem] text-text-muted mt-0.5">{t("newAssetSubtitle")}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={tc("close")}
            className="w-8 h-8 rounded-full grid place-items-center text-text-muted hover:text-foreground hover:bg-surface-inset transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="px-5 py-4 flex flex-col gap-4">
          {/* 類型選擇 */}
          <div>
            <span className="font-mono text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-text-secondary">
              {t("assetTypeAria")}
            </span>
            <div
              className="mt-2 inline-flex p-[3px] rounded-full bg-surface-inset atelier-pill-tabs"
              role="group"
              aria-label={t("assetTypeAria")}
            >
              {typeOptions.map((opt) => {
                const on = assetType === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setAssetType(opt.id)}
                    className={`px-3.5 py-1.5 rounded-full text-[0.6875rem] font-semibold transition-colors ${
                      on
                        ? "text-foreground atelier-pill-tab-active bg-surface shadow-sm"
                        : "text-text-muted hover:text-foreground"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 名稱 */}
          <div>
            <label
              htmlFor="lib-asset-name"
              className="font-mono text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-text-secondary"
            >
              {t("nameLabel")}
            </label>
            <input
              id="lib-asset-name"
              ref={nameRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("namePlaceholder")}
              className="mt-2 w-full bg-surface-inset border border-glass-border rounded-lg px-3.5 py-2.5 text-[0.8125rem] text-foreground placeholder-text-muted focus:outline-none focus:border-primary/60"
            />
          </div>

          {/* 描述 */}
          <div>
            <label
              htmlFor="lib-asset-desc"
              className="font-mono text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-text-secondary"
            >
              {t("descLabel")}
            </label>
            <textarea
              id="lib-asset-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("descPlaceholder")}
              rows={3}
              className="mt-2 w-full bg-surface-inset border border-glass-border rounded-lg px-3.5 py-2.5 text-[0.8125rem] text-foreground placeholder-text-muted focus:outline-none focus:border-primary/60 resize-none"
            />
          </div>

          {/* 圖片（可選）— 上傳本地圖片，或填圖片 URL（備選） */}
          <div>
            <span className="font-mono text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-text-secondary">
              {t("imageLabel")}
            </span>

            {/* 上傳本地圖片 + 預覽縮略圖 */}
            <div className="mt-2 flex items-center gap-3">
              {imageUrl ? (
                <img
                  src={getAssetUrl(imageUrl)}
                  alt=""
                  className="w-12 h-12 rounded-lg object-cover border border-glass-border bg-surface-inset shrink-0"
                />
              ) : (
                <div className="w-12 h-12 rounded-lg grid place-items-center border border-glass-border bg-surface-inset text-text-muted shrink-0">
                  <ImageIcon size={16} aria-hidden="true" />
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-surface-inset border border-glass-border text-text-secondary text-[0.8125rem] font-medium hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                {uploading ? t("uploading") : t("uploadImageButton")}
              </button>
            </div>

            <GridOverlayPicker value={gridChoice} onChange={setGridChoice} className="mt-3" />

            {/* 備選：直接填圖片 URL */}
            <label
              htmlFor="lib-asset-image"
              className="block mt-3 font-mono text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-text-secondary"
            >
              {t("imageUrlLabel")}
            </label>
            <input
              id="lib-asset-image"
              type="url"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder={t("imageUrlPlaceholder")}
              className="mt-2 w-full bg-surface-inset border border-glass-border rounded-lg px-3.5 py-2.5 text-[0.8125rem] text-foreground placeholder-text-muted focus:outline-none focus:border-primary/60"
            />
            <div className="text-[0.6875rem] text-text-muted mt-1.5">{t("imageUrlHint")}</div>
          </div>

          {/* actions */}
          <div className="flex items-center justify-end gap-2.5 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-surface-inset border border-glass-border text-text-secondary text-sm font-medium hover:text-foreground transition-colors"
            >
              {tc("cancel")}
            </button>
            <button
              type="submit"
              disabled={submitting || uploading}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-accent text-sm font-semibold hover:bg-primary-hover transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {submitting ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              {submitting ? t("creating") : tc("create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
