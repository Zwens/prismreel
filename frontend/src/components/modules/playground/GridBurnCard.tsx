"use client";

import { useState, useRef, type ChangeEvent } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Upload, Image as ImageIcon, Library, Check } from "lucide-react";
import { api } from "@/lib/api";
import { getAssetUrl } from "@/lib/utils";
import { toast } from "@/store/toastStore";
import GridOverlayPicker, { gridChoiceToParams, type GridOverlayChoice } from "@/components/shared/GridOverlayPicker";
import AssetSourcePicker from "@/components/modules/playground/AssetSourcePicker";

type LibraryAssetType = "characters" | "scenes" | "props";

const SINGULAR: Record<LibraryAssetType, string> = { characters: "character", scenes: "scene", props: "prop" };

interface GridBurnCardProps {
  /** 燒完網格並存回資產庫成功後的可選回調（例如導回資產庫頁）。 */
  onComplete?: () => void;
}

/**
 * 「燒入網格」卡片 — 圖片生成頁的第三張卡片。
 * 本機上傳或從資產庫選圖 → 燒入網格（後端 apply_grid_overlay，不可逆）→ 存成資產庫新項目。
 * 自包含：不依賴外部 stage machine，對外僅暴露 onComplete。
 */
export default function GridBurnCard({ onComplete }: GridBurnCardProps) {
  const t = useTranslations("playground.imageGen.gridBurn");

  const [sourcePath, setSourcePath] = useState("");
  const [sourceAlreadyGridded, setSourceAlreadyGridded] = useState(false);
  const [assetType, setAssetType] = useState<LibraryAssetType>("props");
  const [name, setName] = useState("");
  const [gridChoice, setGridChoice] = useState<GridOverlayChoice>("black");
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const { size: gridSize, color: gridColor } = gridChoiceToParams(gridChoice);
      const { image_url, has_grid_overlay } = await api.uploadLibraryImage(file, gridSize, gridColor);
      setSourcePath(image_url);
      setSourceAlreadyGridded(has_grid_overlay);
      setSavedOnce(false);
      toast.success(t("uploadSuccess"));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      toast.error(t("uploadFailed"), msg ? { body: msg } : undefined);
    } finally {
      setUploading(false);
    }
  };

  const handleLibrarySelect = (path: string, hasGridOverlay?: boolean) => {
    setSourcePath(path);
    setSourceAlreadyGridded(!!hasGridOverlay);
    setSavedOnce(false);
    setPickerOpen(false);
  };

  const handleSave = async () => {
    if (saving || uploading || !sourcePath) return;
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error(t("nameRequired"));
      return;
    }
    setSaving(true);
    try {
      await api.createLibraryAsset(SINGULAR[assetType], {
        name: trimmed,
        image_url: sourcePath,
        has_grid_overlay: sourceAlreadyGridded,
      });
      toast.success(t("saveSuccess"), { body: trimmed });
      setSavedOnce(true);
      onComplete?.();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("saveFailed");
      toast.error(t("saveFailed"), { body: msg });
    } finally {
      setSaving(false);
    }
  };

  const typeOptions: { id: LibraryAssetType; label: string }[] = [
    { id: "characters", label: t("typeCharacter") },
    { id: "scenes", label: t("typeScene") },
    { id: "props", label: t("typeProp") },
  ];

  return (
    <div className="glass-panel border border-glass-border rounded-2xl p-5 flex flex-col gap-4">
      <div>
        <div className="font-display atelier-display text-base font-semibold text-foreground tracking-tight">
          {t("title")}
        </div>
        <div className="text-[0.75rem] text-text-muted mt-1">{t("description")}</div>
      </div>

      {/* 上傳前先選網格樣式：本機上傳會用當下選定樣式一次性燒入，事後無法改套（OSS 圖片無法回頭補燒） */}
      <GridOverlayPicker value={gridChoice} onChange={setGridChoice} />

      {/* 來源圖片：本機上傳 或 從資產庫選 */}
      <div className="flex items-center gap-3">
        {sourcePath ? (
          <img
            src={getAssetUrl(sourcePath)}
            alt=""
            className="w-14 h-14 rounded-lg object-cover border border-glass-border bg-surface-inset shrink-0"
          />
        ) : (
          <div className="w-14 h-14 rounded-lg grid place-items-center border border-glass-border bg-surface-inset text-text-muted shrink-0">
            <ImageIcon size={18} aria-hidden="true" />
          </div>
        )}
        <div className="flex flex-col gap-2">
          <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} className="hidden" />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || saving}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-surface-inset border border-glass-border text-text-secondary text-[0.8125rem] font-medium hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {uploading ? t("uploading") : t("uploadButton")}
          </button>
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            disabled={uploading || saving}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-surface-inset border border-glass-border text-text-secondary text-[0.8125rem] font-medium hover:text-foreground transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <Library size={14} />
            {t("pickFromLibraryButton")}
          </button>
        </div>
      </div>

      {sourcePath && (
        <div className="flex items-center gap-1.5 text-[0.75rem] text-primary">
          <Check size={13} />
          {sourceAlreadyGridded ? t("alreadyGridded") : t("sourceIsOriginal")}
        </div>
      )}

      {/* 存成資產庫項目 */}
      <div>
        <span className="font-mono text-[0.625rem] font-semibold uppercase tracking-[0.1em] text-text-secondary">
          {t("saveAsLabel")}
        </span>
        <div
          className="mt-2 inline-flex p-[3px] rounded-full bg-surface-inset atelier-pill-tabs"
          role="group"
          aria-label={t("saveAsLabel")}
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
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("namePlaceholder")}
          className="mt-2 w-full bg-surface-inset border border-glass-border rounded-lg px-3.5 py-2.5 text-[0.8125rem] text-foreground placeholder-text-muted focus:outline-none focus:border-primary/60"
        />
      </div>

      <button
        type="button"
        onClick={handleSave}
        disabled={saving || uploading || !sourcePath}
        className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-on-accent text-sm font-semibold hover:bg-primary-hover transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
        {saving ? t("saving") : savedOnce ? t("saveAgain") : t("saveButton")}
      </button>

      <AssetSourcePicker
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={handleLibrarySelect}
        accept="image"
      />
    </div>
  );
}
