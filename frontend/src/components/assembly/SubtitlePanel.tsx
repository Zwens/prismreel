"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Download, Loader2, Subtitles } from "lucide-react";

import { api, SubtitleCue, SubtitleTemplate } from "@/lib/api";
import { toast } from "@/store/toastStore";
import { extractErrorDetail } from "@/lib/utils";

interface Props {
  projectId: string;
  initialEnabled?: boolean;
  initialTemplateId?: string;
  /** Called with the updated Script after a successful save, so the caller can
   *  push it into the project store. Without this the store keeps the stale
   *  settings and the next mount re-reads outdated initial* props. */
  onSaved?: (updated: unknown) => void;
}

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
}

export function SubtitlePanel({
  projectId,
  initialEnabled = true,
  initialTemplateId = "douyin",
  onSaved,
}: Props) {
  const t = useTranslations("subtitle");

  const [templates, setTemplates] = useState<SubtitleTemplate[]>([]);
  const [cues, setCues] = useState<SubtitleCue[]>([]);
  const [enabled, setEnabled] = useState(initialEnabled);
  const [templateId, setTemplateId] = useState(initialTemplateId);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // A failed load must not be indistinguishable from "this project has no
  // dialogue" — that tells the user to add lines they may already have.
  const [loadError, setLoadError] = useState<string | null>(null);
  // What the server last accepted. Reverting to the mount-time props instead
  // would resurrect a setting the user already changed successfully.
  const [persisted, setPersisted] = useState({
    enabled: initialEnabled,
    template_id: initialTemplateId,
  });
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    Promise.all([api.listSubtitleTemplates(), api.previewSubtitles(projectId)])
      .then(([tpl, cs]) => {
        if (cancelled) return;
        setTemplates(tpl);
        setCues(cs);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = extractErrorDetail(e, t("loadFailed"));
        setLoadError(msg);
        toast.error(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, t, reloadTick]);

  const save = async (next: { enabled: boolean; template_id: string }) => {
    const prev = persisted;
    setSaving(true);
    try {
      const updated = await api.updateSubtitleSettings(projectId, next);
      setPersisted(next);
      onSaved?.(updated);
      toast.success(t("saved"));
    } catch (e) {
      toast.error(extractErrorDetail(e, t("saveFailed")));
      setEnabled(prev.enabled);
      setTemplateId(prev.template_id);
    } finally {
      setSaving(false);
    }
  };

  const labelFor = (id: string) =>
    id === "douyin" ? t("templateDouyin") : id === "cinematic" ? t("templateCinematic") : id;

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-text-secondary">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center gap-3 p-12 text-center">
        <p className="text-sm text-text-secondary">{loadError}</p>
        <button
          type="button"
          className="glass-button rounded-lg px-4 py-2 text-sm"
          onClick={() => setReloadTick((n) => n + 1)}
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex items-start gap-3">
        <Subtitles className="mt-1 h-5 w-5 text-text-secondary" />
        <div>
          <h3 className="text-lg font-medium text-foreground">{t("title")}</h3>
          <p className="text-sm text-text-secondary">{t("description")}</p>
        </div>
      </header>

      <label className="glass-panel flex items-center justify-between rounded-lg p-4">
        <span className="text-sm text-foreground">{t("enabled")}</span>
        <input
          type="checkbox"
          checked={enabled}
          disabled={saving}
          onChange={(e) => {
            setEnabled(e.target.checked);
            void save({ enabled: e.target.checked, template_id: templateId });
          }}
        />
      </label>

      <section className="flex flex-col gap-2">
        <span className="text-sm text-text-secondary">{t("template")}</span>
        <div className="grid grid-cols-2 gap-3">
          {templates.map((tpl) => (
            <button
              key={tpl.id}
              type="button"
              disabled={saving}
              onClick={() => {
                setTemplateId(tpl.id);
                void save({ enabled, template_id: tpl.id });
              }}
              className={`glass-button rounded-lg p-4 text-left transition ${
                templateId === tpl.id ? "border-accent" : "border-glass-border"
              } border`}
            >
              <div className="text-sm font-medium text-foreground">{labelFor(tpl.id)}</div>
              <div className="mt-1 text-xs text-text-secondary">
                {tpl.font_size}px · {tpl.chars_per_line}/line
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-secondary">{t("preview")}</span>
          <span className="text-xs text-text-secondary">
            {t("cueCount", { count: cues.length })}
          </span>
        </div>

        {cues.length === 0 ? (
          <p className="glass-panel rounded-lg p-6 text-center text-sm text-text-secondary">
            {t("empty")}
          </p>
        ) : (
          <div className="custom-scrollbar max-h-96 overflow-y-auto rounded-lg">
            {cues.map((c) => (
              <div
                key={c.index}
                className="flex gap-3 border-b border-glass-border px-3 py-2 text-sm last:border-b-0"
              >
                <span className="w-8 shrink-0 text-text-secondary">{c.index}</span>
                <span className="w-28 shrink-0 font-mono text-xs text-text-secondary">
                  {fmtTime(c.start_s)} → {fmtTime(c.end_s)}
                </span>
                <span className="text-foreground">
                  {c.speaker ? <b className="mr-1 text-text-secondary">{c.speaker}:</b> : null}
                  {c.text}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <footer className="flex gap-3">
        <a
          className="glass-button flex items-center gap-2 rounded-lg px-4 py-2 text-sm"
          href={api.subtitleExportUrl(projectId, "ass")}
        >
          <Download className="h-4 w-4" /> {t("exportAss")}
        </a>
        <a
          className="glass-button flex items-center gap-2 rounded-lg px-4 py-2 text-sm"
          href={api.subtitleExportUrl(projectId, "srt")}
        >
          <Download className="h-4 w-4" /> {t("exportSrt")}
        </a>
      </footer>
    </div>
  );
}
